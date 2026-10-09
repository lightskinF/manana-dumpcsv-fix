# Manana: correzione dell'esportazione `dumpCsv`

> **English summary.** In Manana's CSV export (`ConnectionsRegister.dumpCsv`) the connection status was written
> *before* the status update of the same event was applied, so closed or reset connections were mostly exported as
> `Active`, and `Closed` could not tell an ordinary close from a reset. This repository contains a one-file patch
> (about +55/-14 lines), the script used to verify it against a reference server with known TCP behaviour, the data
> of two test sessions on an Android emulator, and build notes for the problems found when compiling the project.
> The patch is a derivative of GPL-3.0 code and keeps that license; the scripts and the documents are MIT.

## Il problema

In `ConnectionsRegister.connectionsUpdates` la riga del CSV veniva scritta **prima** di applicare l'aggiornamento
(`conn.processUpdate(update)`) e di aggiornare lo stato della connessione. Conseguenze:

1. lo stato esportato era quello *precedente* all'evento: una connessione chiusa o resettata risultava quasi
   sempre `Active`;
2. `Closed` e `Reset` erano esportati entrambi come `Closed` (`getStatus()` li unisce), anche se il codice nativo
   li distingue (`CONN_STATUS_CLOSED`, `CONN_STATUS_RESET`);
3. per calcolare i byte della riga si modificavano i contatori dell'oggetto connessione (alias `connForDump =
   conn`), con rischio di valori negativi sugli aggiornamenti che non portano contatori; i pacchetti erano
   esportati come totali mentre i byte erano incrementi.

Nei dati della tesi (349 connessioni di laboratorio, versione originale) lo stato risultava `Closed` solo in 34 delle
70 connessioni di RESET e TLS_RESET, e nessuna delle 301 connessioni presenti in più righe aveva uno stato diverso
da `Active`.

## La correzione

File modificato: `app/src/main/java/com/emanuelef/remote_capture/ConnectionsRegister.java`
(`patches/0001-...patch`, circa 55 righe aggiunte e 14 tolte).

- Gli incrementi di byte e pacchetti si calcolano prima di applicare l'aggiornamento, **senza modificare** la
  connessione, e solo se l'aggiornamento porta contatori (`UPDATE_STATS`).
- La riga si scrive **dopo** `processUpdate` e `processConnectionStatus`, quindi con lo stato aggiornato.
- Nuova colonna **in fondo** all'intestazione, `StatusDetail`, con lo stato nativo (`NEW`, `CONNECTING`,
  `CONNECTED`, `CLOSED`, `ERROR`, `SOCKET_ERROR`, `CLIENT_ERROR`, `RESET`, `UNREACHABLE`, `SOCKS5_ERROR`...).
  Le colonne esistenti non cambiano né di posizione né di significato, quindi i programmi che leggono il CSV per
  nome di colonna (come lo script del server Django) continuano a funzionare.
- Gli overload `dumpCsv(conn)` e `dumpConnectionsCsv(conn)` con la vecchia firma restano e delegano ai nuovi.

Applicazione: `git apply patches/0001-Fix-dumpCsv-write-status-after-the-update-is-applied.patch` dalla radice del repository di Manana.

## Verifica

`tools/verifica_dumpcsv.py <report_manana.csv> <server_log.csv>` confronta il report di Manana con il registro di
un server di riferimento che chiude ogni connessione in un modo noto (FIN, RST, silenzio, risposta parziale seguita da
RST, scenari TLS). Il server è in <https://github.com/lightskinF/Manana-tampering-nonroot> (cartella `server/`).
Lo script controlla: presenza di `StatusDetail`, assenza di byte o pacchetti negativi, riconciliazione dei byte con il
server e che lo stato **nell'ultima riga di ogni connessione** corrisponda alla chiusura osservata dal server
(RST → `RESET`; FIN o chiusura pulita → `CLOSED`). Python 3.8+, solo libreria standard.

### Risultati (emulatore Android 14, Chrome, server sullo stesso PC)

| | Sessione 1 | Sessione 2 |
|---|---|---|
| Connessioni abbinate al server | 152 | 137 |
| Stato finale corretto | **152 su 152** | **130 su 131** valutate |
| Valori negativi | 0 | 0 |
| Byte che tornano col server | 151 su 152 | 122 su 137 (vedi sotto) |
| Contenuto | scenari HTTP e TLS (senza TLS_NORMALE) | come la 1, più TLS_NORMALE e 2-3 minuti di navigazione reale |

Con la versione originale, nello stesso tipo di esperimento, `RESET` e `TLS_RESET` risultavano `Closed` solo in
34 connessioni su 70.

Dettaglio della sessione 2:

- I 10 TLS_NORMALE non possono riconciliare i byte per costruzione: il server conta i byte in chiaro, Manana
  quelli cifrati. Il caso RESET_PARZIALE (Manana non vede i dati che il server invia prima del reset) è già noto.
- Le altre connessioni che non tornano sono 4, e l'unica differenza sullo stato è una connessione che termina con
  `SOCKET_ERROR` invece di `CLOSED`. Sono tutte comprese nell'intervallo (circa due minuti) in cui l'emulatore
  rallentava e si è riavviato. I contatori di due di esse sono compatibili con la ritrasmissione di un SYN (60 byte
  in più). Non ho una prova che la causa sia solo il rallentamento: sono riportate come anomalie non spiegate.
- Nel traffico reale (58 connessioni TCP) gli stati finali sono `CLOSED` (49) e `SOCKET_ERROR` (9): plausibili, ma
  senza un riferimento con cui confrontarli.

### Limiti

Un solo ambiente (emulatore, Chrome, rete locale), nessun dispositivo fisico, nessuna rete mobile. Le prove sono
poche (2-3 per scenario nella sessione 2). Il confronto verifica lo stato esportato, non altre colonne.

## Altre anomalie osservate, **non** corrette

`numConnectionsEnc/NotEnc` incrementati a ogni aggiornamento; aggiornamenti di connessioni già uscite dall'anello
ignorati; nome dell'app e campo `Info` non racchiusi tra virgolette nel CSV; un `AppsResolver` nuovo per ogni riga.

## Compilare il progetto

Il repository di Manana su Codeberg, così com'è, non compila su un computer nuovo. Vedi `docs/NOTE_BUILD.md`.

## Contenuto

| Percorso | Contenuto |
|---|---|
| `patches/` | la correzione |
| `tools/verifica_dumpcsv.py` | script di verifica |
| `tools/filtra_dati.py` | toglie dal report le righe non dirette al server di riferimento |
| `data/sessione1`, `data/sessione2` | report di Manana (solo le righe verso il server di riferimento, `tools/filtra_dati.py`) e registro del server delle due prove; il traffico reale della sessione 2 non è pubblicato |
| `docs/NOTE_BUILD.md` | problemi di compilazione trovati e come risolverli |
| `docs/MESSAGGIO_PER_IL_PROFESSORE.md` | bozza del messaggio di accompagnamento |

## Licenza

La patch modifica codice di Manana, derivato da PCAPdroid (GPL-3.0), e segue la stessa licenza. Gli script e i
documenti di questo repository sono sotto licenza MIT (file `LICENSE`).
