"""Sonda usa-e-getta: com'e' fatto un annuncio di Vinted?

NON fa parte dell'app. Serve a rispondere a una domanda sola, prima di
scrivere qualsiasi riga di codice vero: esiste un `ad_to_dict()` pulito anche
per Vinted, o e' una palude? Si guarda l'output e si decide. Poi si cancella.

Non indovina l'endpoint: apre il catalogo e ascolta le chiamate che la pagina
fa da sola. La prima versione si fermava qui e concludeva troppo in fretta --
al primo caricamento Vinted rende la lista lato server, quindi l'XHR del
catalogo NON parte e sembra che non esista. Percio' ora si prova su tre
fronti diversi, che rispondono a domande diverse:

  A. i dati stanno gia' dentro l'HTML?      (allora si parsa quello)
  B. l'XHR parte se si interagisce?         (scroll e pagina 2)
  C. l'endpoint risponde coi soli cookie?   <- QUESTA E' QUELLA CHE CONTA

La C e' il modo in cui il monitor lavora con Subito: browser acceso una volta
per i cookie, poi una richiesta JSON per giro. Se regge, Vinted costa quanto
Subito. Se no, ogni controllo deve passare da una pagina vera, e il conto
cambia di un ordine di grandezza.

    python vinted_probe.py

Scrive l'annuncio grezzo in vinted_item.json e riassume a schermo.
"""
import json
import sys

from playwright.sync_api import sync_playwright

HOME = "https://www.vinted.it/"
CATALOGO = "https://www.vinted.it/catalog?order=newest_first"
# indirizzo storico dell'API: si PROVA, non si da' per buono
ENDPOINT = "https://www.vinted.it/api/v2/catalog/items"
HEADLESS = True          # False per vedere il browser mentre lavora
USCITA = "vinted_item.json"


def trova_lista(dato, _profondita=0):
    """Prima lista di dizionari con un 'id': la lista dei risultati.

    Si cerca per FORMA e non per nome del campo, perche' il nome e' proprio
    quello che non sappiamo.
    """
    if _profondita > 6:
        return None
    if isinstance(dato, dict):
        for chiave, valore in dato.items():
            if (isinstance(valore, list) and valore
                    and isinstance(valore[0], dict) and "id" in valore[0]):
                return chiave, valore
            trovato = trova_lista(valore, _profondita + 1)
            if trovato:
                return trovato
    elif isinstance(dato, list):
        for valore in dato[:20]:
            trovato = trova_lista(valore, _profondita + 1)
            if trovato:
                return trovato
    return None


def riassumi(item):
    """Chiavi di primo livello con tipo e un assaggio del valore."""
    for chiave, valore in item.items():
        if isinstance(valore, dict):
            print("   {:26} dict({} chiavi)".format(chiave, len(valore)))
        elif isinstance(valore, list):
            print("   {:26} list({} elementi)".format(chiave, len(valore)))
        else:
            testo = str(valore)
            if len(testo) > 46:
                testo = testo[:43] + "..."
            print("   {:26} {:8} {}".format(chiave, type(valore).__name__, testo))


def salva(annuncio, da_dove):
    with open(USCITA, "w", encoding="utf-8") as f:
        json.dump(annuncio, f, ensure_ascii=False, indent=2)
    print("\nannuncio grezzo scritto in {} (da: {})".format(USCITA, da_dove))
    print("\n--- campi di un annuncio ---")
    riassumi(annuncio)


def main():
    catturate = []   # (url, testo) di ogni risposta JSON vista passare

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=HEADLESS)
        contesto = browser.new_context(locale="it-IT")
        pagina = contesto.new_page()

        def su_risposta(risposta):
            # il corpo va letto ORA: dopo la navigazione potrebbe non esserci piu'
            tipo = (risposta.headers or {}).get("content-type", "")
            if "json" not in tipo.lower():
                return
            try:
                catturate.append((risposta.url, risposta.text()))
            except Exception:
                pass

        pagina.on("response", su_risposta)

        print("apro {} ...".format(CATALOGO))
        try:
            pagina.goto(CATALOGO, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print("la pagina non si e' caricata: {}".format(exc))
            browser.close()
            return 1

        # il banner del consenso puo' bloccare tutto il resto
        for etichetta in ("Accetta tutto", "Accetta", "Accept all"):
            try:
                bottone = pagina.get_by_role("button", name=etichetta)
                if bottone.count():
                    bottone.first.click(timeout=3000)
                    print("banner del consenso: chiuso con '{}'".format(etichetta))
                    break
            except Exception:
                pass

        # B: provoca l'XHR pigro, che al primo caricamento non parte
        try:
            pagina.mouse.wheel(0, 20000)
            pagina.wait_for_timeout(2500)
            pagina.goto(CATALOGO + "&page=2", wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_timeout(2500)
        except Exception:
            pass

        print("\nrisposte JSON viste passare: {}".format(len(catturate)))
        for url, _ in catturate:
            print("   {}".format(url[:110]))

        annuncio = None
        for url, testo in catturate:
            try:
                dato = json.loads(testo)
            except Exception:
                continue
            trovato = trova_lista(dato)
            if trovato and len(trovato[1]) >= 5:   # i banner hanno liste corte
                nome, lista = trovato
                print("\n[B] lista in '{}' ({} annunci) da:\n    {}".format(
                    nome, len(lista), url[:110]))
                annuncio = lista[0]
                break

        # A: i dati potrebbero essere gia' dentro l'HTML
        if annuncio is None:
            html = pagina.content()
            print("\n[A] HTML di {} caratteri".format(len(html)))
            for marcatore in ("__NEXT_DATA__", "__INITIAL_STATE__", "window.__data"):
                if marcatore in html:
                    print("    trovato {} nell'HTML: i dati si possono".format(marcatore))
                    print("    parsare da li', anche se e' piu' pesante.")
                    break
            else:
                print("    nessun blob JSON noto nell'HTML.")

        # C: la domanda vera
        print("\n[C] chiamata diretta a {}".format(ENDPOINT))
        try:
            diretta = contesto.request.get(
                ENDPOINT,
                params={"per_page": 20, "order": "newest_first"},
                timeout=30000)
            print("    HTTP {}".format(diretta.status))
            if diretta.ok:
                trovato = trova_lista(diretta.json())
                if trovato:
                    print("    annunci ricevuti: {}".format(len(trovato[1])))
                    print("\n    OK: si puo' fare come con Subito.")
                    if annuncio is None:
                        annuncio = trovato[1][0]
                else:
                    print("    risposta senza lista di annunci.")
            else:
                print("\n    Rifiutata: servirebbe passare da una pagina vera")
                print("    a ogni controllo. Molto piu' lento e fragile.")
        except Exception as exc:
            print("    fallita: {}".format(exc))

        if annuncio is not None:
            salva(annuncio, "catalogo")
        else:
            print("\nNessun annuncio catturato da nessuna delle tre strade.")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
