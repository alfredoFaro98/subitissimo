# Subitissimo

Django + Playwright per cercare e sorvegliare annunci su Subito.it. Due parti:

1. **Ricerca a richiesta** — scrivi cosa cerchi sul sito, lui scarica tutti i risultati e li mostra in tabella, mappa, CSV.
2. **Monitor** — un processo separato che sta acceso e controlla ogni N secondi se sono usciti annunci nuovi, salvandoli per sempre.

## Setup su una macchina nuova

```bash
pip install -r requirements.txt
python -m playwright install chromium   # serve il browser, non basta il pacchetto pip
python manage.py migrate                # crea db.sqlite3 da zero
```

**Il database NON è nel repo** (`db.sqlite3` è in `.gitignore`). Un clone fresco parte
quindi senza nessun dato: niente cronologia, niente preferiti, nessun monitor, nessun
annuncio raccolto. È voluto — il file supera i 50 MB e cresce di ~4 MB al giorno con il
monitor acceso, versionarlo gonfierebbe la repo a ogni commit.

Stessa cosa per la cartella `export/`, che contiene i registri CSV dei monitor: è dati,
non codice, e resta sulla macchina che li ha raccolti.

## Avvio

Due processi indipendenti, si accendono in qualsiasi ordine e funzionano anche da soli:

```bash
python manage.py runserver 127.0.0.1:8000   # il sito          (Avvia Subitissimo.bat)
python manage.py monitor                    # la sorveglianza  (Avvia Monitor.bat)
```

Su Windows ci sono i due `.bat` a doppio click nella cartella del progetto.

## Struttura

| File | Cosa c'è dentro |
|---|---|
| `scraper/services.py` | Il motore. `run_search()` per la ricerca a richiesta, `HadesSession` per il monitor, `ad_to_dict()` che normalizza un annuncio grezzo |
| `scraper/models.py` | `SearchQuery`/`Item` (ricerche), `Favorite`, `SavedSearch`, `Monitor`/`MonitorHit` (sorveglianza) |
| `scraper/management/commands/monitor.py` | Il processo che sta acceso |
| `scraper/csv_log.py` | Registro CSV in coda, un file per monitor |
| `scraper/categories.py` | Codici categoria dell'API (`9` = Elettronica, `10` = Informatica, ...) |
| `scraper/views.py` + `urls.py` | Le pagine. Il monitor sta su `/monitor/` |

## Come parla con Subito

Non si fa scraping dell'HTML. Playwright apre il sito solo per **farsi dare i cookie**,
poi si interroga direttamente l'API interna:

```
https://hades.subito.it/v1/search/items?q=&c=10&start=0&lim=50&sort=datedesc
```

`c` è il codice categoria, `q` può essere vuoto (allora è "tutta la categoria").

## Il monitor

Un `Monitor` è una ricerca sorvegliata (parola chiave e/o categoria, ogni quanti secondi
controllare). Si creano dalla pagina `/monitor/`.

Ogni annuncio mai visto prima diventa un `MonitorHit`. **La tabella è append-only**: una
riga non viene mai cancellata né aggiornata. È il punto centrale del progetto — quando un
annuncio sparisce da Subito perché venduto, la riga resta con prezzo, orario e link, così
si vede cosa è passato e a che prezzo.

In parallelo ogni annuncio nuovo viene accodato a `export/monitor-<id>-<nome>.csv`
(separatore `;` e BOM UTF-8, così Excel italiano lo apre con un doppio click).

Primo avvio di un monitor = **semina**: registra silenziosamente i 50 annunci già online,
li marca `is_seed=True` e li tiene fuori dal feed e dal CSV. Da lì in poi segnala solo
roba effettivamente nuova.

### Opzioni utili

```bash
python manage.py monitor --once            # un giro solo, poi esce (per provare)
python manage.py monitor --monitor 1       # solo il monitor con quell'id
python manage.py monitor --headful         # mostra il browser, per capire cosa succede
python manage.py monitor --recap -1        # ristampa TUTTI gli annunci del giorno
python manage.py monitor --recap 0         # non ristamparne nessuno (niente domanda)
python manage.py monitor --giorno 13/09    # ristampa un giorno preciso (anche "ieri")
python manage.py monitor --no-backfill     # non recuperare la giornata all'avvio
python manage.py monitor --no-links        # titoli non cliccabili (terminali vecchi)
```

All'avvio, su terminale interattivo e senza `--recap`/`--giorno`, **chiede che giorno
rivedere** mostrando gli ultimi 7 giorni presenti in archivio con i rispettivi conteggi.
Se il giorno scelto supera le 500 righe chiede anche **quale scaglione**: il numero di
scaglioni e le loro fasce orarie si calcolano sul momento, perche' dipendono da quanti
annunci ha quel giorno. Si puo' sempre rispondere `t` (tutti) o `n` (niente).

Se nessuno risponde entro 30 secondi parte da sola — un monitor fermo davanti a una domanda
non sorveglia niente, ed e' il caso tipico di chi lancia il `.bat` e si allontana. Senza
terminale interattivo la domanda si salta del tutto.

**Il selettore del giorno legge solo l'archivio locale.** Andare a ripescare un giorno
passato da Subito non e' previsto ed e' una cattiva idea: per arrivare a ieri bisognerebbe
sfogliare prima tutto oggi (~130 richieste) e tornerebbe comunque una fetta sempre piu'
falsata dalla sopravvivenza. Il ripescaggio dalla rete resta solo per oggi.

Il recap gira **dopo** il recupero della giornata: gli scaglioni vanno calcolati sui dati
veri, non su una giornata ancora a meta'.

Ogni riga porta a destra, incollato al bordo della finestra, il **numero d'ordine
dell'annuncio nella giornata** (`#1234`, verde brillante). E' la posizione nella lista
cronologica del giorno e non nel blocco stampato, cosi' lo stesso annuncio ha lo stesso
numero nel recap, dentro uno scaglione e quando arriva dal vivo — si ritrova con
Ctrl+Shift+F. L'allineamento si calcola sulla larghezza VISIBILE della riga: le sequenze
del link e dei colori non occupano colonne, contarle sballerebbe la colonna dei numeri.
La larghezza si rilegge a ogni riga, cosi' ridimensionare la finestra non rompe nulla.

Ogni riga finisce con un `>>` cliccabile che apre l'annuncio (sequenza OSC 8, Ctrl+click
su Windows Terminal). Il link sta sul segnetto e non sul titolo di proposito: il terminale
sottolinea la zona cliccabile, e sottolineare due caratteri e' meno invadente che
sottolineare l'intero titolo. Le sequenze vengono emesse solo se `sys.stdout.isatty()`,
altrimenti finirebbero dentro i file di log.

### Recupero della giornata

All'avvio, se il monitor era spento da piu' di 30 minuti, sfoglia l'archivio all'indietro
**fino a dove si era fermato** — anche attraverso la mezzanotte — e salva quello che trova (`is_backfill=True`, colonna
`Origine` = "recuperato" nel CSV). Se il buco e' piccolo non fa nulla: il controllo normale
legge comunque la prima pagina. Costo misurato su Informatica, 16 ore di giornata: **44
richieste, 26 secondi, 2.167 annunci**.

Il tetto e' 24 ore (`MAX_BACKFILL_WINDOW`). Attraversare la mezzanotte e' il punto
importante: la prima versione si fermava all'inizio del giorno corrente, quindi spegnere
alle 17:44 e riaccendere all'una di notte faceva perdere per sempre tutta la sera. Quando
il recupero viene saltato ora lo scrive a schermo con il motivo, cosi' un buco nei dati si
diagnostica dal terminale invece che a posteriori.

**Attenzione al significato.** Si recupera solo cio' che e' SOPRAVVISSUTO: un annuncio
pubblicato stamattina e gia' venduto non e' piu' nell'indice, quindi non lo vedra' mai
nessuno. La distribuzione oraria lo mostra bene — l'ora corrente rende ~8 annunci/minuto,
quella di sette ore prima ~3,7: la differenza e' roba che nel frattempo e' sparita. Quindi
e' un **inventario di cosa e' ancora comprabile**, non il registro di cosa e' passato. Solo
le righe `is_backfill=False` sono un archivio storico onesto.

I recuperati nascono `is_read=True`: sono inventario, non avvisi, e altrimenti
sommergerebbero il contatore dei non letti.

**Orari: il recap e la pagina web mostrano `date_pub_iso`, non `first_seen_at`.** I
recuperati hanno tutti lo stesso istante di cattura (il momento del ripescaggio, es.
`16:41:03` per 2.167 righe) e mostrarlo non direbbe nulla. La data di pubblicazione vera
c'e' su ogni annuncio, quindi si usa quella per ordinare e per stampare, con
`first_seen_at` come ripiego se manca. Il CSV tiene comunque entrambe le colonne.

## Trappole — leggere prima di mettere le mani

**1. L'indice di Subito si aggiorna a raffiche, non in continuo.**
Misurato interrogando l'API ogni 15-20 secondi: la lista resta congelata sullo stesso
istante per minuti, poi arriva tutto insieme (~60 annunci in una botta). Nel momento
della raffica l'indice è quasi in diretta — porta annunci pubblicati 10-15 secondi prima
— quindi il ritardo non è strutturale, è "quanto manca al prossimo aggiornamento".

Abbassare l'intervallo sotto i 30 secondi **non fa arrivare gli annunci prima**: tra una
raffica e l'altra non esiste nulla di nuovo da vedere. Moltiplica solo le richieste e il
rischio di prendersi un 429.

Verificato che non è una cache davanti all'API: una richiesta con parametro anti-cache
restituisce esattamente gli stessi annunci, e categorie diverse (9, 10, 12) si congelano
e si sbloccano nello stesso identico istante. È l'indice di ricerca globale.

**2. Niente query al database dentro un blocco Playwright, di norma.**
L'API sincrona di Playwright gira dentro un event loop e Django rifiuta le query lì
dentro (`SynchronousOnlyOperation`). Per questo `run_search()` tocca il DB solo *prima* e
*dopo* il blocco browser. Il comando `monitor` invece ha bisogno di leggere e scrivere
mentre la sessione è viva, quindi imposta `DJANGO_ALLOW_ASYNC_UNSAFE=1` — **solo in quel
processo**, il sito resta protetto. Non spostare quella riga: sta in cima al modulo perché
deve valere prima di qualsiasi import di Django.

**3. La console di Windows è cp1252 e fa morire il processo.**
Un titolo con un trattino unicode (`‑`, U+2011) o un'emoji generava `UnicodeEncodeError`
mentre veniva stampato, e l'eccezione usciva dal loop ammazzando il monitor. Il comando
ora fa `stream.reconfigure(errors='replace')` su stdout/stderr. Nel CSV e nel database i
caratteri sono corretti, è solo il terminale che mostra `?`.

**4. SQLite è in modalità WAL, e serve.**
Il monitor scrive mentre il sito legge. Senza WAL si becca "database is locked". È
configurato in `settings.py` via `OPTIONS.init_command`.

**5. Il CSV può essere bloccato da Excel, ed è previsto.**
Se il file è aperto, la scrittura fallisce con `PermissionError`: le righe restano marcate
da esportare (`exported_at=None`) e vengono recuperate al giro dopo. Non si perde niente.
Il database è la fonte di verità, il CSV è solo il registro leggibile.

**6. Gli annunci più vecchi della semina vanno scartati.**
Quando la prima pagina è tutta nuova il monitor sbircia la pagina successiva (le raffiche
da 60 non stanno in una pagina da 50). Ma lì ci sono annunci precedenti all'accensione:
vengono filtrati confrontandoli con `Monitor.seeded_at`. Togliendo quel controllo il feed
si riempie di roba vecchia spacciata per nuova.

**7. Cambiare le colonne del CSV ruota il file.**
`csv_log.rotate_if_stale()` confronta l'intestazione del file esistente con `COLUMNS`: se
non combaciano rinomina il vecchio in `...-fino-al-<data>.csv` e ne apre uno pulito.
Accodare righe con un numero di colonne diverso disallineerebbe tutto. `csv_path()` esclude
dalla ricerca i file che contengono `ARCHIVE_TAG`, altrimenti riprenderebbe a scrivere su
un registro chiuso.
