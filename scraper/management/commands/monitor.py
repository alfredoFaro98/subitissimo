"""Sorveglia in continuo le ricerche salvate come Monitor.

Uso tipico (processo separato, lasciato acceso accanto al runserver):

    python manage.py monitor

Ogni Monitor attivo viene interrogato al suo intervallo; gli annunci mai visti
prima finiscono in MonitorHit e non vengono piu' toccati, nemmeno quando
spariscono da Subito.
"""

import os
import random
import sys
import time

# L'API sincrona di Playwright gira dentro un event loop, e Django rifiuta le
# query in quel contesto. Qui il processo e' interamente sincrono (nessun await
# tra una query e l'altra), quindi il blocco non serve: lo togliamo solo per
# questo comando, il sito continua a girare con il controllo attivo.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.core.management.base import BaseCommand
from django.db.models import Max, Min
from django.utils import timezone

from scraper.csv_log import csv_path, flush_pending
from scraper.models import Monitor, MonitorHit
from scraper.services import HadesError, HadesSession, parse_iso_datetime

# Se la prima pagina e' TUTTA nuova potremmo aver perso qualcosa nel frattempo:
# in quel caso si sbircia la pagina dopo, fino a questo limite.
MAX_PAGES_PER_CHECK = 4

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


def build_hit(monitor, item, is_seed=False):
    data = {f: item.get(f) for f in HIT_FIELDS}
    for f in ('description', 'defect_flag', 'defect_reason'):
        data[f] = data[f] or ''
    data['title'] = (data['title'] or '')[:255]
    data['shippable'] = bool(data['shippable'])
    return MonitorHit(
        monitor=monitor,
        date_pub_iso=parse_iso_datetime(item.get('date_pub_iso')),
        is_seed=is_seed,
        is_read=is_seed,
        exported_at=timezone.now() if is_seed else None,
        **data,
    )


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
        parser.add_argument('--recap', type=int, default=500,
                            help='Quanti annunci gia\' raccolti oggi ristampare all\'avvio '
                                 '(default 500, 0 per non mostrarli).')

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

    # ------------------------------------------------------------------ recap

    def print_recap(self, monitors, limit):
        """Ristampa gli annunci gia' raccolti oggi, letti dal database.

        Non tocca Subito: e' roba gia' scaricata nelle sessioni precedenti, si
        rigenerano solo le righe. Serve a ritrovare a schermo quello che si era
        perso chiudendo la finestra.
        """
        if not limit:
            return

        mezzanotte = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        oggi = MonitorHit.objects.filter(
            monitor__in=monitors, is_seed=False, first_seen_at__gte=mezzanotte,
        )
        totale = oggi.count()
        if not totale:
            return

        # i piu' recenti, poi rimessi in ordine cronologico: cosi' l'ultimo
        # raccolto sta in fondo, attaccato a quello che arrivera' dal vivo
        righe = list(oggi.select_related('monitor').order_by('-first_seen_at')[:limit])
        righe.reverse()

        # l'intervallo e' quello dell'intera giornata, non delle sole righe mostrate
        estremi = oggi.aggregate(primo=Min('first_seen_at'), ultimo=Max('first_seen_at'))
        testa = 'Oggi: {} annunci raccolti, dalle {} alle {}'.format(
            totale,
            timezone.localtime(estremi['primo']).strftime('%H:%M'),
            timezone.localtime(estremi['ultimo']).strftime('%H:%M'),
        )
        if totale > len(righe):
            testa += ' -- qui sotto gli ultimi {}'.format(len(righe))

        piu_monitor = len(monitors) > 1
        self.stdout.write('')
        self.stdout.write(testa)
        self.stdout.write('--- gia\' raccolti, non sono nuovi ---')
        for hit in righe:
            riga = '  {}  . {} | {}{}'.format(
                timezone.localtime(hit.first_seen_at).strftime('%H:%M:%S'),
                hit.price_str or '-',
                (hit.title or '')[:70],
                link_marker(hit.url, self.links),
            )
            if piu_monitor:
                riga += '  [{}]'.format(hit.monitor.label)
            self.stdout.write(riga)
        self.stdout.write('--- da qui in poi e\' roba nuova ---')
        self.stdout.write('')

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

        # prima il gia' visto (lettura locale, istantanea), poi si accende il browser
        self.print_recap(monitors, max(0, options['recap']))

        session = HadesSession(headless=not options['headful'])
        self.log('Avvio browser e raccolta cookie...')
        session.start()
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
