"""Registro CSV degli annunci intercettati dai monitor.

Un file per monitor, in coda: ogni annuncio nuovo viene aggiunto in fondo e non
viene piu' toccato. Il file cresce dalla prima accensione in avanti, quindi si
puo' aprire quando si vuole per vedere tutto quello che e' passato.

Il database resta la fonte di verita': se la scrittura fallisce (tipico su
Windows quando il file e' aperto in Excel) le righe restano marcate da scrivere
e vengono recuperate al giro successivo.
"""

import csv
import glob
import os

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

EXPORT_DIR = getattr(settings, 'MONITOR_CSV_DIR', os.path.join(settings.BASE_DIR, 'export'))

# marcatore nel nome dei registri chiusi da una rotazione
ARCHIVE_TAG = '-fino-al-'

COLUMNS = [
    'Visto il',
    'Origine',
    'Prezzo',
    'Prezzo numerico',
    'Titolo',
    'Data pubblicazione',
    'Categoria',
    'Comune',
    'Provincia',
    'Regione',
    'Condizione',
    'Spedibile',
    'Tipo spedizione',
    'Costo spedizione',
    'Stato',
    'Motivo stato',
    'Descrizione',
    'Link annuncio',
    'Link immagine',
    'ID Subito',
    'Monitor',
]


def csv_path(monitor):
    """Percorso del file di un monitor.

    Il nome porta l'id, cosi' se rinomini il monitor il registro non si spezza
    in due file: si continua a scrivere su quello che c'e' gia'.
    """
    esistenti = sorted(
        f for f in glob.glob(os.path.join(EXPORT_DIR, 'monitor-{}-*.csv'.format(monitor.pk)))
        # i registri chiusi da una rotazione non sono piu' quello attivo
        if ARCHIVE_TAG not in os.path.basename(f)
    )
    if esistenti:
        return esistenti[0]
    nome = slugify(monitor.label) or 'monitor'
    return os.path.join(EXPORT_DIR, 'monitor-{}-{}.csv'.format(monitor.pk, nome))


def rotate_if_stale(percorso):
    """Se il file esistente ha colonne diverse da quelle attuali, lo mette da parte.

    Aggiungere una colonna a un file gia' avviato disallineerebbe tutte le righe
    nuove rispetto all'intestazione. Meglio chiudere il vecchio registro con la
    data e ricominciarne uno pulito: non si perde niente e restano entrambi
    leggibili.
    """
    if not os.path.exists(percorso) or os.path.getsize(percorso) == 0:
        return None
    with open(percorso, 'r', newline='', encoding='utf-8-sig') as fh:
        prima = fh.readline().rstrip('\r\n')
    if prima.split(';') == COLUMNS:
        return None
    base, est = os.path.splitext(percorso)
    archivio = '{}{}{}{}'.format(base, ARCHIVE_TAG, timezone.localtime().strftime('%Y%m%d-%H%M'), est)
    os.rename(percorso, archivio)
    return archivio


def hit_row(hit):
    visto = timezone.localtime(hit.first_seen_at).strftime('%d/%m/%Y %H:%M:%S')
    pubblicato = hit.date_pub or ''
    if not pubblicato and hit.date_pub_iso:
        pubblicato = timezone.localtime(hit.date_pub_iso).strftime('%d/%m/%Y %H:%M')
    return [
        visto,
        'recuperato' if hit.is_backfill else 'dal vivo',
        hit.price_str or '',
        hit.price_num if hit.price_num is not None else '',
        hit.title or '',
        pubblicato,
        hit.category or '',
        hit.town or '',
        hit.province or '',
        hit.region or '',
        hit.condition or '',
        'Si' if hit.shippable else 'No',
        hit.shipping_type or '',
        hit.shipping_cost if hit.shipping_cost is not None else '',
        hit.defect_flag or '',
        hit.defect_reason or '',
        (hit.description or '').replace('\r', ' ').replace('\n', ' '),
        hit.url or '',
        hit.image_url or '',
        hit.subito_id or '',
        hit.monitor.label,
    ]


def append_hits(monitor, hits):
    """Aggiunge le righe in fondo al CSV del monitor. Ritorna quante ne ha scritte.

    Solleva OSError se il file non e' scrivibile: chi chiama decide cosa fare
    (le righe restano da esportare e si riprova dopo).
    """
    hits = list(hits)
    if not hits:
        return 0

    percorso = csv_path(monitor)
    os.makedirs(os.path.dirname(percorso), exist_ok=True)
    rotate_if_stale(percorso)
    intestazione = not os.path.exists(percorso) or os.path.getsize(percorso) == 0

    # utf-8-sig e ";" perche' Excel italiano apra il file senza doverlo importare
    with open(percorso, 'a', newline='', encoding='utf-8-sig') as fh:
        writer = csv.writer(fh, delimiter=';')
        if intestazione:
            writer.writerow(COLUMNS)
        for hit in hits:
            writer.writerow(hit_row(hit))

    return len(hits)


def flush_pending(monitor):
    """Scrive nel CSV tutti gli annunci del monitor non ancora esportati.

    Ritorna (quanti_scritti, errore_oppure_None).
    """
    from .models import MonitorHit

    pending = list(
        monitor.hits.filter(exported_at__isnull=True, is_seed=False).order_by('first_seen_at', 'pk')
    )
    if not pending:
        return 0, None

    try:
        scritte = append_hits(monitor, pending)
    except OSError as exc:
        return 0, exc

    MonitorHit.objects.filter(pk__in=[h.pk for h in pending]).update(exported_at=timezone.now())
    return scritte, None
