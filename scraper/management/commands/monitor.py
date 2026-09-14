"""Sorveglia in continuo le ricerche salvate come Monitor.

Uso tipico (processo separato, lasciato acceso accanto al runserver):

    python manage.py monitor

Ogni Monitor attivo viene interrogato al suo intervallo; gli annunci mai visti
prima finiscono in MonitorHit e non vengono piu' toccati, nemmeno quando
spariscono da Subito.
"""

import os
import queue
import random
import sys
import threading
import time
from datetime import datetime, timedelta
from datetime import time as dt_time

# L'API sincrona di Playwright gira dentro un event loop, e Django rifiuta le
# query in quel contesto. Qui il processo e' interamente sincrono (nessun await
# tra una query e l'altra), quindi il blocco non serve: lo togliamo solo per
# questo comando, il sito continua a girare con il controllo attivo.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from scraper.csv_log import csv_path, flush_pending
from scraper.models import Monitor, MonitorHit
from scraper.services import HadesError, HadesSession, parse_iso_datetime

# Se la prima pagina e' TUTTA nuova potremmo aver perso qualcosa nel frattempo:
# in quel caso si sbircia la pagina dopo, fino a questo limite.
MAX_PAGES_PER_CHECK = 4

# Recupero della giornata: si sfoglia all'indietro finche' non si supera
# l'istante di partenza. Tetto di sicurezza, una giornata intera di Informatica
# sta in ~60 pagine, una di Elettronica in ~180.
MAX_BACKFILL_PAGES = 150

# Sotto questo buco il recupero non serve: il controllo normale legge comunque
# la prima pagina, che copre gli ultimi minuti.
BACKFILL_MIN_GAP_SECONDS = 30 * 60

# Campi di MonitorHit copiati pari pari dal dict normalizzato dell'annuncio.
HIT_FIELDS = (
    'subito_id', 'title', 'price_str', 'price_num', 'date_pub', 'category',
    'region', 'province', 'town', 'condition', 'shipping_type', 'shipping_cost',
    'shippable', 'image_url', 'url', 'description', 'defect_flag', 'defect_reason',
)


def hyperlink(text, url, enabled=True):
    """Rende `text` cliccabile nel terminale, nascondendo l'url dietro di esso.

    Usa la sequenza OSC 8, la stessa cosa dei colori ma per i collegamenti. I
    terminali che non la conoscono la ignorano e mostrano il testo normale;
    Windows Terminal la apre con Ctrl+click. Va disattivata quando l'output
    finisce in un file, altrimenti ci si ritrovano dentro i codici di escape.
    """
    if not enabled or not url or not text:
        return text
    return '\033]8;;{}\033\\{}\033]8;;\033\\'.format(url, text)


def link_marker(url, enabled=True):
    """Segnetto cliccabile da appendere in fondo alla riga.

    Il link sta qui e non sul titolo di proposito: il terminale sottolinea la
    zona cliccabile, e sottolineare due caratteri e' molto meno invadente che
    sottolineare l'intero titolo. Se i link sono spenti non si stampa nulla,
    un ">>" morto sarebbe solo rumore.
    """
    if not enabled or not url:
        return ''
    return '  ' + hyperlink('>>', url, True)


def published_before(item, cutoff):
    """True se l'annuncio e' stato pubblicato prima di `cutoff`.

    Serve quando si sbircia oltre la prima pagina: li' ci sono annunci che
    esistevano gia' prima che il monitor partisse, e non sono "nuovi".
    """
    if cutoff is None:
        return False
    published = parse_iso_datetime(item.get('date_pub_iso'))
    return published is not None and published < cutoff


def build_hit(monitor, item, is_seed=False, is_backfill=False):
    data = {f: item.get(f) for f in HIT_FIELDS}
    for f in ('description', 'defect_flag', 'defect_reason'):
        data[f] = data[f] or ''
    data['title'] = (data['title'] or '')[:255]
    data['shippable'] = bool(data['shippable'])
    return MonitorHit(
        monitor=monitor,
        date_pub_iso=parse_iso_datetime(item.get('date_pub_iso')),
        is_seed=is_seed,
        is_backfill=is_backfill,
        # i recuperati non sono avvisi da leggere, sono inventario
        is_read=is_seed or is_backfill,
        exported_at=timezone.now() if is_seed else None,
        **data,
    )


def unknown_items(monitor, items):
    """Toglie dalla lista quelli gia' presenti a database.

    Gli id si confrontano a blocchi: SQLite ha un tetto sul numero di parametri
    di una singola query, e un recupero di giornata ne porta qualche migliaio.
    """
    visti = set()
    ids = [i['subito_id'] for i in items]
    for k in range(0, len(ids), 900):
        visti.update(
            MonitorHit.objects
            .filter(monitor=monitor, subito_id__in=ids[k:k + 900])
            .values_list('subito_id', flat=True)
        )
    fuori = set()
    risultato = []
    for i in items:
        sid = i['subito_id']
        if sid in visti or sid in fuori:
            continue
        fuori.add(sid)
        risultato.append(i)
    return risultato


RECAP_TUTTI = -1
RECAP_DEFAULT = 500
# Se nessuno risponde si parte lo stesso: il monitor serve acceso, non fermo
# davanti a una domanda mentre chi l'ha lanciato e' andato a farsi un caffe'.
SCELTA_TIMEOUT = 30


def chiedi_riga(prompt):
    """Legge una riga, ma senza restare appesa: dopo SCELTA_TIMEOUT si arrende.

    Un monitor fermo davanti a una domanda non sorveglia niente, ed e' il caso
    tipico di chi lancia il .bat e poi si allontana.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    risposta = queue.Queue()

    def leggi():
        try:
            risposta.put(sys.stdin.readline())
        except Exception:
            risposta.put(None)

    threading.Thread(target=leggi, daemon=True).start()
    try:
        return (risposta.get(timeout=SCELTA_TIMEOUT) or '').strip().lower()
    except queue.Empty:
        sys.stdout.write('\n')
        sys.stdout.flush()
        return ''


def giorno_da_testo(testo):
    """"14/09", "14/09/2026", "ieri", "oggi" o vuoto -> una data. None se non si capisce."""
    testo = (testo or '').strip().lower()
    oggi = timezone.localtime().date()
    if not testo or testo in ('oggi', 'o'):
        return oggi
    if testo in ('ieri', 'i'):
        return oggi - timedelta(days=1)
    for fmt in ('%d/%m/%Y', '%d/%m', '%d-%m-%Y', '%d-%m'):
        try:
            data = datetime.strptime(testo, fmt).date()
        except ValueError:
            continue
        # senza anno si intende quello corrente
        return data if '%Y' in fmt else data.replace(year=oggi.year)
    return None


def backfill_since(monitor):
    """Da che ora recuperare, oppure None se non ne vale la pena.

    Mai prima della mezzanotte di oggi: il senso e' "la giornata di oggi", non
    tutto l'archivio. Se il monitor era acceso poco fa non si recupera nulla.
    """
    mezzanotte = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    ultimo = monitor.last_checked_at
    if ultimo is None:
        return mezzanotte
    if (timezone.now() - ultimo).total_seconds() < BACKFILL_MIN_GAP_SECONDS:
        return None
    return max(ultimo, mezzanotte)


class Command(BaseCommand):
    help = "Tiene d'occhio i Monitor attivi e salva gli annunci nuovi."

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true',
                            help='Fa un solo giro su tutti i monitor attivi ed esce.')
        parser.add_argument('--monitor', type=int, default=None,
                            help='Controlla solo il monitor con questo id.')
        parser.add_argument('--jitter', type=float, default=0.2,
                            help="Variazione casuale dell'intervallo, 0.2 = +/-20%% (default 0.2).")
        parser.add_argument('--recycle', type=int, default=3600,
                            help='Ogni quanti secondi rifare il browser headless (default 3600).')
        parser.add_argument('--headful', action='store_true',
                            help='Mostra il browser, utile solo per capire cosa succede.')
        parser.add_argument('--no-links', action='store_true',
                            help='Non rendere cliccabili i titoli (se il terminale mostra caratteri strani).')
        parser.add_argument('--giorno', default=None,
                            help="Giorno da ristampare all'avvio: gg/mm, ieri oppure oggi. "
                                 "Se non lo passi, all'avvio te lo chiede.")
        parser.add_argument('--no-backfill', action='store_true',
                            help='Non recuperare la giornata di oggi all\'avvio.')
        parser.add_argument('--recap', type=int, default=None,
                            help='Quanti annunci di oggi ristampare all\'avvio: 0 nessuno, '
                                 '-1 tutti. Se non lo passi, all\'avvio te lo chiede.')

    # ------------------------------------------------------------------ utils

    def log(self, msg, style=None):
        stamp = timezone.localtime().strftime('%H:%M:%S')
        line = '[{}] {}'.format(stamp, msg)
        self.stdout.write(style(line) if style else line)

    def monitors(self, only_id):
        qs = Monitor.objects.filter(is_active=True)
        if only_id is not None:
            qs = qs.filter(pk=only_id)
        return list(qs)

    # ------------------------------------------------------------------ check

    def check_monitor(self, session, monitor):
        """Interroga un monitor e salva i nuovi annunci. Ritorna quanti ne ha trovati."""
        seeding = not monitor.is_seeded
        cutoff = None if seeding else monitor.seeded_at
        collected = []
        start = 0

        for _page in range(MAX_PAGES_PER_CHECK):
            items, _count_all = session.fetch_items(
                query=monitor.query,
                category=monitor.category,
                limit=monitor.page_size,
                start=start,
                title_only=monitor.title_only,
                shippable_only=monitor.shippable_only,
            )
            items = [i for i in items if i.get('subito_id')]
            if not items:
                break

            known = set(
                MonitorHit.objects
                .filter(monitor=monitor, subito_id__in=[i['subito_id'] for i in items])
                .values_list('subito_id', flat=True)
            )
            already = {i['subito_id'] for i in collected}
            fresh = [
                i for i in items
                if i['subito_id'] not in known
                and i['subito_id'] not in already
                and not published_before(i, cutoff)
            ]
            collected.extend(fresh)

            # Pagina interamente nuova: l'ondata potrebbe continuare oltre.
            # In semina invece basta la prima pagina, non serve archiviare il passato.
            if seeding or len(fresh) < len(items):
                break
            start += monitor.page_size
            time.sleep(0.3)

        now = timezone.now()
        if collected:
            # dal piu' vecchio al piu' recente, cosi' l'ordine di inserimento
            # rispecchia l'ordine di pubblicazione
            rows = [build_hit(monitor, i, is_seed=seeding) for i in reversed(collected)]
            MonitorHit.objects.bulk_create(rows, ignore_conflicts=True)

        monitor.last_checked_at = now
        monitor.checks_count += 1
        monitor.last_error = ''
        if collected and not seeding:
            monitor.last_hit_at = now
        if seeding:
            monitor.is_seeded = True
            monitor.seeded_at = now
        monitor.save(update_fields=[
            'last_checked_at', 'checks_count', 'last_error', 'last_hit_at',
            'is_seeded', 'seeded_at',
        ])

        if seeding:
            self.log('{}: semina iniziale, {} annunci archiviati in silenzio'.format(monitor.label, len(collected)))
            return 0

        scritte, errore = flush_pending(monitor)
        if errore:
            self.log(
                'CSV non scrivibile ({}): le righe restano in coda, riprovo al prossimo giro'.format(errore),
                self.style.WARNING,
            )

        for item in collected:
            prezzo = item.get('price_str') or '-'
            titolo = (item.get('title') or '')[:70]
            self.log('  + {} | {}{}'.format(prezzo, titolo, link_marker(item.get('url'), self.links)),
                     self.style.SUCCESS)
        if collected:
            self.log('{}: {} nuovi ({} nel CSV)'.format(monitor.label, len(collected), scritte),
                     self.style.SUCCESS)
        elif monitor.checks_count % 20 == 0:
            # segno di vita ogni tanto, per non lasciare la finestra muta
            self.log('{}: niente di nuovo ({} giri)'.format(monitor.label, monitor.checks_count))
        return len(collected)

    def record_error(self, monitor, message):
        monitor.last_checked_at = timezone.now()
        monitor.last_error = message[:500]
        monitor.save(update_fields=['last_checked_at', 'last_error'])

    # --------------------------------------------------------------- recupero

    def backfill_monitor(self, session, monitor):
        """Ripesca gli annunci della giornata ancora online, sfogliando all'indietro.

        Attenzione al significato: si recupera solo cio' che e' SOPRAVVISSUTO.
        Un annuncio pubblicato stamattina e gia' venduto non e' piu' nell'indice
        di Subito, quindi nessuno puo' piu' vederlo. E' un inventario di cosa e'
        ancora comprabile, non il registro di cosa e' passato.
        """
        since = backfill_since(monitor)
        if since is None:
            return 0

        self.log('{}: recupero la giornata dalle {}...'.format(
            monitor.label, timezone.localtime(since).strftime('%H:%M')))

        raccolti = []
        pagine = 0
        for p in range(MAX_BACKFILL_PAGES):
            items, _count_all = session.fetch_items(
                query=monitor.query,
                category=monitor.category,
                limit=monitor.page_size,
                start=p * monitor.page_size,
                title_only=monitor.title_only,
                shippable_only=monitor.shippable_only,
            )
            pagine += 1
            if not items:
                break

            oltre = False
            for it in items:
                pub = parse_iso_datetime(it.get('date_pub_iso'))
                if pub is not None and pub < since:
                    oltre = True
                    break
                if it.get('subito_id'):
                    raccolti.append(it)
            if oltre:
                break
            time.sleep(0.3)

        if pagine >= MAX_BACKFILL_PAGES:
            self.log('{}: fermato al tetto di {} pagine, la giornata e\' piu\' lunga'.format(
                monitor.label, MAX_BACKFILL_PAGES), self.style.WARNING)

        nuovi = unknown_items(monitor, raccolti)
        if not nuovi:
            self.log('{}: niente da recuperare, {} annunci gia\' in archivio'.format(
                monitor.label, len(raccolti)))
            return 0

        # dal piu' vecchio al piu' recente: l'ordine di inserimento e quello nel
        # CSV seguono la pubblicazione, non l'ordine in cui li ha restituiti l'API
        nuovi.sort(key=lambda i: parse_iso_datetime(i.get('date_pub_iso')) or since)
        MonitorHit.objects.bulk_create(
            [build_hit(monitor, i, is_backfill=True) for i in nuovi],
            batch_size=200, ignore_conflicts=True,
        )

        scritte, errore = flush_pending(monitor)
        if errore:
            self.log('CSV non scrivibile ({}): le righe restano in coda'.format(errore),
                     self.style.WARNING)

        self.log('{}: recuperati {} annunci di oggi ({} pagine, {} nel CSV)'.format(
            monitor.label, len(nuovi), pagine, scritte), self.style.SUCCESS)
        self.log('   sono quelli ancora online: chi ha gia\' venduto non e\' piu\' nell\'indice')
        return len(nuovi)

    # ------------------------------------------------------------------ recap

    def hits_del_giorno(self, monitors, giorno):
        """Gli annunci PUBBLICATI in quel giorno, dal piu' vecchio al piu' recente.

        Il filtro e' sulla data di pubblicazione e non su quando li ha visti il
        monitor: e' quella che risponde alla domanda "cosa e' uscito quel giorno".
        """
        inizio = timezone.make_aware(datetime.combine(giorno, dt_time.min))
        return (
            MonitorHit.objects
            .filter(monitor__in=monitors, is_seed=False,
                    date_pub_iso__gte=inizio, date_pub_iso__lt=inizio + timedelta(days=1))
            .select_related('monitor')
            .order_by('date_pub_iso', 'pk')
        )

    def scegli_scaglione(self, hits, totale, giorno):
        """Se il giorno non sta in una schermata, chiede quale fetta mostrare.

        Il numero di scaglioni si calcola sul momento: dipende da quanti annunci
        ha quel giorno, che cambia di continuo.
        """
        if totale <= RECAP_DEFAULT:
            return list(hits)

        scaglioni = (totale + RECAP_DEFAULT - 1) // RECAP_DEFAULT
        # un estremo per scaglione, per far vedere che fascia oraria si prende
        orari = list(hits.values_list('date_pub_iso', flat=True))

        self.stdout.write('')
        self.stdout.write('Il {} ha {} annunci: troppi per una schermata.'.format(
            giorno.strftime('%d/%m'), totale))
        self.stdout.write('Sono {} scaglioni da {}:'.format(scaglioni, RECAP_DEFAULT))
        for k in range(scaglioni):
            a = k * RECAP_DEFAULT
            b = min(a + RECAP_DEFAULT, totale) - 1
            self.stdout.write('  {}) {} - {}   ({} annunci)'.format(
                k + 1,
                timezone.localtime(orari[a]).strftime('%H:%M'),
                timezone.localtime(orari[b]).strftime('%H:%M'),
                b - a + 1,
            ))
        self.stdout.write('  t) tutti quanti')
        self.stdout.write('  n) niente, vai ai nuovi')

        scelta = chiedi_riga('Scelta (invio = ultimo scaglione): ')
        if scelta == 'n':
            return []
        if scelta == 't':
            return list(hits)
        if scelta.isdigit() and 1 <= int(scelta) <= scaglioni:
            k = int(scelta) - 1
            return list(hits[k * RECAP_DEFAULT:(k + 1) * RECAP_DEFAULT])
        return list(hits[(scaglioni - 1) * RECAP_DEFAULT:])

    def scegli_recap(self, monitors, recap_forzato, giorno_forzato):
        """Decide cosa ristampare all'avvio. Ritorna (righe, giorno, totale)."""
        interattivo = (sys.stdin is not None and sys.stdin.isatty()
                       and sys.stdout.isatty() and recap_forzato is None
                       and giorno_forzato is None)
        oggi = timezone.localtime().date()

        if not interattivo:
            giorno = giorno_forzato or oggi
            hits = self.hits_del_giorno(monitors, giorno)
            totale = hits.count()
            limite = RECAP_DEFAULT if recap_forzato is None else recap_forzato
            if limite == 0:
                return [], giorno, totale
            righe = list(hits) if limite < 0 else list(hits[max(0, totale - limite):])
            return righe, giorno, totale

        giorni = self.giorni_disponibili(monitors)
        self.stdout.write('')
        self.stdout.write('Che giorno vuoi rivedere?')
        for g, n in giorni:
            self.stdout.write('   {}  {} annunci{}'.format(
                g.strftime('%d/%m'), n, '   (oggi)' if g == oggi else ''))
        scelta = chiedi_riga('Giorno (invio = oggi, oppure gg/mm, "n" per saltare): ')

        if scelta == 'n':
            return [], oggi, 0
        giorno = giorno_da_testo(scelta) or oggi

        hits = self.hits_del_giorno(monitors, giorno)
        totale = hits.count()
        if not totale:
            self.stdout.write('Il {} non ha annunci in archivio.'.format(giorno.strftime('%d/%m')))
            return [], giorno, 0

        return self.scegli_scaglione(hits, totale, giorno), giorno, totale

    def giorni_disponibili(self, monitors):
        righe = (
            MonitorHit.objects
            .filter(monitor__in=monitors, is_seed=False, date_pub_iso__isnull=False)
            .annotate(g=TruncDate('date_pub_iso'))
            .values('g').annotate(n=Count('id')).order_by('-g')[:7]
        )
        return [(r['g'], r['n']) for r in righe]

    def print_recap(self, righe, giorno, totale):
        """Ristampa annunci gia' in archivio, letti dal database.

        Non tocca Subito: si rigenerano solo le righe a partire dai dati salvati.
        """
        if not righe:
            return

        primo = timezone.localtime(righe[0].date_pub_iso or righe[0].first_seen_at)
        ultimo = timezone.localtime(righe[-1].date_pub_iso or righe[-1].first_seen_at)
        ripescati = sum(1 for h in righe if h.is_backfill)

        testa = '{}: {} annunci, pubblicati dalle {} alle {}'.format(
            giorno.strftime('%d/%m'), len(righe),
            primo.strftime('%H:%M'), ultimo.strftime('%H:%M'))
        if ripescati:
            testa += ' ({} ripescati, {} visti dal vivo)'.format(ripescati, len(righe) - ripescati)
        if totale > len(righe):
            testa += ' -- {} su {} della giornata'.format(len(righe), totale)

        piu_monitor = len({h.monitor_id for h in righe}) > 1
        self.stdout.write('')
        self.stdout.write(testa)
        self.stdout.write('--- gia\' raccolti, non sono nuovi ---')
        for hit in righe:
            quando = hit.date_pub_iso or hit.first_seen_at
            riga = '  {}  . {} | {}{}'.format(
                timezone.localtime(quando).strftime('%H:%M:%S'),
                hit.price_str or '-',
                (hit.title or '')[:70],
                link_marker(hit.url, self.links),
            )
            if piu_monitor:
                riga += '  [{}]'.format(hit.monitor.label)
            self.stdout.write(riga)
        self.stdout.write('--- da qui in poi e\' roba nuova ---')
        self.stdout.write('')

    def record_error(self, monitor, message):
        monitor.last_checked_at = timezone.now()
        monitor.last_error = message[:500]
        monitor.save(update_fields=['last_checked_at', 'last_error'])

    # --------------------------------------------------------------- recupero

    def backfill_monitor(self, session, monitor):
        """Ripesca gli annunci della giornata ancora online, sfogliando all'indietro.

        Attenzione al significato: si recupera solo cio' che e' SOPRAVVISSUTO.
        Un annuncio pubblicato stamattina e gia' venduto non e' piu' nell'indice
        di Subito, quindi nessuno puo' piu' vederlo. E' un inventario di cosa e'
        ancora comprabile, non il registro di cosa e' passato.
        """
        since = backfill_since(monitor)
        if since is None:
            return 0

        self.log('{}: recupero la giornata dalle {}...'.format(
            monitor.label, timezone.localtime(since).strftime('%H:%M')))

        raccolti = []
        pagine = 0
        for p in range(MAX_BACKFILL_PAGES):
            items, _count_all = session.fetch_items(
                query=monitor.query,
                category=monitor.category,
                limit=monitor.page_size,
                start=p * monitor.page_size,
                title_only=monitor.title_only,
                shippable_only=monitor.shippable_only,
            )
            pagine += 1
            if not items:
                break

            oltre = False
            for it in items:
                pub = parse_iso_datetime(it.get('date_pub_iso'))
                if pub is not None and pub < since:
                    oltre = True
                    break
                if it.get('subito_id'):
                    raccolti.append(it)
            if oltre:
                break
            time.sleep(0.3)

        if pagine >= MAX_BACKFILL_PAGES:
            self.log('{}: fermato al tetto di {} pagine, la giornata e\' piu\' lunga'.format(
                monitor.label, MAX_BACKFILL_PAGES), self.style.WARNING)

        nuovi = unknown_items(monitor, raccolti)
        if not nuovi:
            self.log('{}: niente da recuperare, {} annunci gia\' in archivio'.format(
                monitor.label, len(raccolti)))
            return 0

        # dal piu' vecchio al piu' recente: l'ordine di inserimento e quello nel
        # CSV seguono la pubblicazione, non l'ordine in cui li ha restituiti l'API
        nuovi.sort(key=lambda i: parse_iso_datetime(i.get('date_pub_iso')) or since)
        MonitorHit.objects.bulk_create(
            [build_hit(monitor, i, is_backfill=True) for i in nuovi],
            batch_size=200, ignore_conflicts=True,
        )

        scritte, errore = flush_pending(monitor)
        if errore:
            self.log('CSV non scrivibile ({}): le righe restano in coda'.format(errore),
                     self.style.WARNING)

        self.log('{}: recuperati {} annunci di oggi ({} pagine, {} nel CSV)'.format(
            monitor.label, len(nuovi), pagine, scritte), self.style.SUCCESS)
        self.log('   sono quelli ancora online: chi ha gia\' venduto non e\' piu\' nell\'indice')
        return len(nuovi)

    # ------------------------------------------------------------------- loop

    def handle(self, *args, **options):
        # La console di Windows parla cp1252: un titolo con un trattino unicode
        # o un'emoji farebbe morire il processo a meta' notte mentre lo stampa.
        # I caratteri fuori tabella diventano "?" e il monitor tira dritto.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors='replace')
            except (AttributeError, ValueError):
                pass

        # I link si mettono solo se si sta scrivendo su un terminale vero:
        # rediretto su file sporcherebbe il file con i codici di escape.
        self.links = sys.stdout.isatty() and not options['no_links']

        only_id = options['monitor']
        jitter = max(0.0, options['jitter'])
        recycle = options['recycle']

        monitors = self.monitors(only_id)
        if not monitors:
            self.stdout.write(self.style.WARNING(
                'Nessun monitor attivo. Creane uno dalla pagina /monitor/ e rilancia.'
            ))
            return

        session = HadesSession(headless=not options['headful'])
        self.log('Avvio browser e raccolta cookie...')
        session.start()
        if not options['no_backfill']:
            for monitor in monitors:
                try:
                    self.backfill_monitor(session, monitor)
                except HadesError as exc:
                    self.log('{}: recupero fallito ({}), tiro dritto'.format(monitor.label, exc),
                             self.style.WARNING)

        # la scelta e la stampa vengono dopo il recupero: gli scaglioni vanno
        # calcolati sui dati veri, non su una giornata ancora a meta'
        giorno_forzato = giorno_da_testo(options['giorno']) if options['giorno'] else None
        righe, giorno, totale = self.scegli_recap(monitors, options['recap'], giorno_forzato)
        if giorno_forzato and not totale:
            self.log('Il {} non ha annunci in archivio.'.format(giorno.strftime('%d/%m')))
        self.print_recap(righe, giorno, totale)

        self.log('Pronto. {} monitor attivi. Ctrl+C per fermare.'.format(len(monitors)))
        for m in monitors:
            self.log('  registro di "{}": {}'.format(m.label, csv_path(m)))

        next_check = {}
        errors_in_a_row = 0

        try:
            while True:
                monitors = self.monitors(only_id)
                if not monitors:
                    self.log('Nessun monitor attivo, attendo...')
                    time.sleep(10)
                    continue

                if recycle and session.age_seconds > recycle:
                    self.log('Rinnovo la sessione del browser')
                    session.restart()

                now = time.monotonic()
                due = [m for m in monitors if next_check.get(m.pk, 0) <= now]

                for monitor in due:
                    try:
                        self.check_monitor(session, monitor)
                        errors_in_a_row = 0
                    except HadesError as exc:
                        errors_in_a_row += 1
                        self.log('{}: {}'.format(monitor.label, exc), self.style.ERROR)
                        self.record_error(monitor, str(exc))
                        # 401/403/429 = cookie bruciati o troppe richieste:
                        # si rifa' la sessione e si rallenta un po'.
                        if exc.status in (401, 403, 429) or errors_in_a_row >= 3:
                            pausa = min(300, 10 * (2 ** min(errors_in_a_row, 5)))
                            self.log('Rifaccio la sessione e aspetto {}s'.format(pausa), self.style.WARNING)
                            try:
                                session.restart()
                            except Exception as restart_exc:
                                self.log('Riavvio fallito: {}'.format(restart_exc), self.style.ERROR)
                            time.sleep(pausa)
                    except Exception as exc:  # imprevisti: si annota e si tira avanti
                        errors_in_a_row += 1
                        self.log('{}: errore inatteso {!r}'.format(monitor.label, exc), self.style.ERROR)
                        self.record_error(monitor, repr(exc))

                    interval = max(5, monitor.interval_seconds)
                    if jitter:
                        interval *= random.uniform(1 - jitter, 1 + jitter)
                    next_check[monitor.pk] = time.monotonic() + interval

                if options['once']:
                    break
                time.sleep(1)

        except KeyboardInterrupt:
            self.stdout.write('\nFermato.')
        finally:
            session.stop()
