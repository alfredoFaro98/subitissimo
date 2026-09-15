"""Esporta in CSV gli annunci Vinted di una ricerca. Niente monitor, una botta sola.

NON fa parte dell'app: non tocca il database e non importa Django. E' uno
strumento a se' che apre Vinted, legge le schede del catalogo e scrive un CSV.

COSA HO MISURATO PRIMA DI SCRIVERLO, perche' spiega ogni scelta qui sotto:

1. Vinted NON espone un'API JSON del catalogo. Provati /api/v2/catalog/items,
   /api/v2/items, /api/v2/catalog, /api/v2/catalog/filters: tutti 404. Nell'HTML
   non c'e' nessun blob JSON (zero __NEXT_DATA__, zero ld+json) e nemmeno nei
   5,7 MB di stream RSC di Next.js compaiono i campi degli annunci. Le schede
   sono markup renderizzato: si leggono dal DOM, non c'e' alternativa.

2. Per fortuna ogni scheda porta un `aria-label` gia' strutturato:
       "Nike Jordan rosa 5Y tg 37.5, Brand: Nike, Condizioni: Ottime,
        Taglia: 37.5, 20.00 EUR, 21.70 EUR"
   Titolo, marca, condizione, taglia e i due prezzi in una stringa sola. E' da
   li' che si cava tutto, non dal testo visibile.

3. LA PAGINAZIONE SI FERMA A 10. L'undicesima pagina torna vuota, verificato.
   Sono circa mille annunci per interrogazione, punto e basta.

4. Ma i filtri di prezzo PARTIZIONANO davvero: "fino a 15" e "da 80" tornano
   insiemi con ZERO elementi in comune. Quindi la categoria si piastrella per
   fasce, e ogni fascia ha il suo budget di mille. E' la stessa idea degli
   scaglioni orari che il monitor usa per le giornate.

5. Le schede non hanno la descrizione: per averla servirebbe aprire la pagina di
   ogni annuncio, cioe' una richiesta per annuncio invece di dieci per fascia.
   Non si fa: la colonna non c'e' proprio, meglio assente che vuota e bugiarda.

   python vinted_export.py                    # cerca "nike"
   python vinted_export.py --cerca "air max"
   python vinted_export.py --cerca zaino --senza-fasce   # veloce, tetto mille
"""
import argparse
import csv
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "https://www.vinted.it/catalog"
CARTELLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export")

# l'undicesima pagina torna vuota: non e' una scelta, e' il muro di Vinted
PAGINE_MAX = 10
ATTESA_FRA_PAGINE = 1.0

# Fasce in euro, estremo destro escluso. Servono a scavalcare il tetto delle
# mille: strette dove c'e' piu' roba (il grosso dell'usato sta sotto i 30).
FASCE = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30),
         (30, 50), (50, 80), (80, 150), (150, None)]

# Colonne loro, non quelle di Subito: Comune, Provincia, Regione e Data
# pubblicazione qui non esistono, e tenerle vuote sarebbe solo rumore.
COLONNE = [
    'Titolo', 'Marca', 'Condizione', 'Taglia',
    'Prezzo', 'Prezzo totale', 'Prezzo numerico',
    'Fascia', 'ID Vinted', 'Link annuncio', 'Link immagine',
]

SCRIPT_SCHEDE = """() => {
    const raccolte = [];
    const visti = {};
    document.querySelectorAll('a[href*="/items/"]').forEach(collegamento => {
        const trovato = collegamento.getAttribute('href').match(/\\/items\\/(\\d+)/);
        if (!trovato) return;
        const codice = trovato[1];
        if (visti[codice]) return;
        visti[codice] = true;
        const etichetta = collegamento.getAttribute('aria-label')
                       || collegamento.getAttribute('title') || '';
        if (!etichetta) return;
        const contenitore = collegamento.closest('div');
        const immagine = contenitore ? contenitore.querySelector('img') : null;
        raccolte.push({
            codice: codice,
            etichetta: etichetta,
            href: collegamento.href,
            immagine: immagine ? (immagine.getAttribute('src') || '') : ''
        });
    });
    return raccolte;
}"""


def numero_da(testo):
    """Primo numero con decimali dentro `testo`, come float. None se non c'e'."""
    trovato = re.search(r"(\d+(?:[.,]\d+)?)", testo or "")
    if not trovato:
        return None
    try:
        return float(trovato.group(1).replace(",", "."))
    except ValueError:
        return None


def campo_etichettato(etichetta, nome):
    """Valore di un marcatore tipo 'Brand: Nike' dentro l'aria-label."""
    trovato = re.search(nome + r":\s*([^,]*)", etichetta)
    return trovato.group(1).strip() if trovato else ""


def leggi_scheda(scheda, fascia):
    """Dall'aria-label ai campi del CSV.

    Il titolo e' tutto cio' che precede il primo marcatore: NON si puo' spezzare
    la stringa sulle virgole, perche' i titoli ne contengono di loro.
    """
    etichetta = scheda["etichetta"]

    prezzi = re.findall(r"(\d+[.,]\d{2})\s*€", etichetta)
    prezzo = (prezzi[0] + " €") if prezzi else ""
    prezzo_totale = (prezzi[1] + " €") if len(prezzi) > 1 else ""

    taglio = len(etichetta)
    for marcatore in ("Brand:", "Condizioni:", "Taglia:"):
        posizione = etichetta.find(", " + marcatore)
        if posizione != -1:
            taglio = min(taglio, posizione)
    if taglio == len(etichetta) and prezzi:
        posizione = etichetta.find(prezzi[0])
        if posizione > 0:
            taglio = posizione
    titolo = etichetta[:taglio].rstrip(" ,")

    return [
        titolo,
        campo_etichettato(etichetta, "Brand"),
        campo_etichettato(etichetta, "Condizioni"),
        campo_etichettato(etichetta, "Taglia"),
        prezzo,
        prezzo_totale,
        numero_da(prezzo) if prezzo else "",
        fascia,
        scheda["codice"],
        scheda["href"],
        scheda["immagine"],
    ]


def indirizzo(parola, minimo, massimo, numero_pagina):
    parti = ["search_text=" + parola.replace(" ", "+"), "order=newest_first"]
    if minimo is not None:
        parti.append("price_from=" + str(minimo))
    if massimo is not None:
        parti.append("price_to=" + str(massimo))
    if numero_pagina > 1:
        parti.append("page=" + str(numero_pagina))
    return BASE + "?" + "&".join(parti)


def chiudi_consenso(pagina):
    for etichetta in ("Accetta tutto", "Accetta", "Accept all"):
        try:
            bottone = pagina.get_by_role("button", name=etichetta)
            if bottone.count():
                bottone.first.click(timeout=3000)
                pagina.wait_for_timeout(2000)
                return
        except Exception:
            pass


def sfoglia(pagina, parola, minimo, massimo, gia_visti, righe):
    """Sfoglia una fascia fino al muro o finche' non porta piu' niente di nuovo."""
    nome_fascia = "{}-{}".format(minimo if minimo is not None else "0",
                                 massimo if massimo is not None else "oltre")
    trovati_fascia = 0
    for numero_pagina in range(1, PAGINE_MAX + 1):
        try:
            pagina.goto(indirizzo(parola, minimo, massimo, numero_pagina),
                        wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_timeout(2500)
            schede = pagina.evaluate(SCRIPT_SCHEDE)
        except Exception as errore:
            print("      pagina {}: errore, salto ({})".format(
                numero_pagina, str(errore)[:50]))
            break

        nuovi = 0
        for scheda in schede:
            if scheda["codice"] in gia_visti:
                continue
            gia_visti.add(scheda["codice"])
            righe.append(leggi_scheda(scheda, nome_fascia))
            nuovi += 1
        trovati_fascia += nuovi
        print("      pagina {:2}: {:3} schede, {:3} nuove".format(
            numero_pagina, len(schede), nuovi))

        # niente di nuovo o pagina vuota: la fascia e' finita, inutile insistere
        if not schede or nuovi == 0:
            break
        time.sleep(ATTESA_FRA_PAGINE)
    return trovati_fascia


def main():
    lettore = argparse.ArgumentParser(description=__doc__)
    lettore.add_argument("--cerca", default="nike", help="parola da cercare")
    lettore.add_argument("--senza-fasce", action="store_true",
                         help="una passata sola: veloce, ma tetto di ~1000 annunci")
    lettore.add_argument("--mostra-browser", action="store_true")
    opzioni = lettore.parse_args()

    fasce = [(None, None)] if opzioni.senza_fasce else FASCE
    gia_visti = set()
    righe = []

    os.makedirs(CARTELLA, exist_ok=True)
    nome = "vinted-{}-{}.csv".format(
        re.sub(r"[^a-z0-9]+", "-", opzioni.cerca.lower()).strip("-"),
        time.strftime("%Y%m%d-%H%M"))
    percorso = os.path.join(CARTELLA, nome)

    # Si scrive fascia per fascia e non tutto alla fine: una passata completa
    # sono minuti di lavoro, e interromperla a meta' non deve buttare via quello
    # che si e' gia' raccolto. Stesso dialetto dei registri del monitor, ';' e
    # BOM, cosi' Excel italiano apre il file con un doppio click invece di
    # incolonnare tutto dentro la cella A1.
    scritte = 0
    with open(percorso, "w", newline="", encoding="utf-8-sig") as fh:
        scrittore = csv.writer(fh, delimiter=";")
        scrittore.writerow(COLONNE)
        fh.flush()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not opzioni.mostra_browser)
            contesto = browser.new_context(locale="it-IT")
            pagina = contesto.new_page()

            pagina.goto(indirizzo(opzioni.cerca, None, None, 1),
                        wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_timeout(2500)
            chiudi_consenso(pagina)

            for minimo, massimo in fasce:
                print("   fascia {} - {} EUR".format(
                    minimo if minimo is not None else "0",
                    massimo if massimo is not None else "oltre"))
                quanti = sfoglia(pagina, opzioni.cerca, minimo, massimo, gia_visti, righe)
                scrittore.writerows(righe[scritte:])
                fh.flush()
                scritte = len(righe)
                print("   -> {} nella fascia, {} in totale (gia' sul disco)".format(
                    quanti, scritte))
            browser.close()

    if not righe:
        print("Nessun annuncio raccolto.")
        os.remove(percorso)
        return 1

    print("")
    print("{} annunci scritti in {}".format(len(righe), percorso))
    return 0


if __name__ == "__main__":
    sys.exit(main())
