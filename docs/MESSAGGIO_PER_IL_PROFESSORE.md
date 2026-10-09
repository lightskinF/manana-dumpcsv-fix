# Bozza del messaggio

**Oggetto:** Manana: correzione dell'esportazione CSV (`dumpCsv`) e due problemi di compilazione

Buonasera Professore,

nel lavoro di tesi avevo osservato che l'esportazione CSV di Manana scrive lo stato della connessione prima che
l'aggiornamento di stato venga applicato: le connessioni chiuse o resettate risultano quasi sempre `Active`, e
`Closed` e `Reset` sono esportati con la stessa etichetta. A tesi conclusa ho provato a correggerlo.

La correzione riguarda il solo file `ConnectionsRegister.java` (circa 55 righe aggiunte e 14 tolte):
- la riga si scrive dopo l'applicazione dell'aggiornamento;
- gli incrementi di byte e pacchetti si calcolano senza modificare la connessione;
- in fondo all'intestazione c'è una nuova colonna `StatusDetail` con lo stato nativo (`CLOSED`, `RESET`, ...); le
  colonne esistenti non cambiano, quindi gli strumenti che leggono il CSV per nome (come `generate_manana_stats.py`)
  non ne risentono.

L'ho verificata con il server di riferimento della tesi (comportamento TCP noto per ogni porta) su emulatore Android.
Nella prima sessione lo stato finale è corretto in 152 connessioni su 152 (con la versione originale `Closed` compariva
solo in 34 connessioni di reset su 70). Nella seconda, che includeva TLS e navigazione reale ma con l'emulatore
instabile, è corretto in 130 su 131, e la connessione residua è descritta nel README. È un solo ambiente
(emulatore, Chrome, rete locale), non ho provato su dispositivo fisico.

Compilando il progetto da Codeberg ho trovato due problemi che impediscono di compilarlo su un computer nuovo:
- manca `submodules/libpcap/bpf_filter.c` (la copia di libpcap è la 1.10.1 senza quel file);
- la cartella `app/.cxx` (cache di compilazione con percorsi di un altro computer) è finita nel repository.
Le note per ripristinarli sono in `docs/NOTE_BUILD.md`.

Patch, script di verifica, dati e note sono qui: <LINK DELLA REPOSITORY GITHUB>

Se le sembra utile posso preparare una pull request su Codeberg.

Cordiali saluti,
Fabio Greco
