# -*- coding: utf-8 -*-
"""
verifica_dumpcsv.py - Controlla un report CSV di Manana contro il registro del server di riferimento.

Uso:
    python verifica_dumpcsv.py <report_manana.csv> <server_log.csv>

Serve a verificare la correzione di dumpCsv (ConnectionsRegister.java):
  1. il report ha la colonna StatusDetail (cioe' viene dalla versione corretta);
  2. nessuna riga ha byte o pacchetti negativi;
  3. i byte, sommati per connessione, riconciliano ancora con il server:
         inviati Manana  = ricevuti dal server + 60 + 40k
         ricevuti Manana = inviati dal server  + 48 + 40k'     (k, k' interi >= 0)
  4. lo stato nell'ULTIMA riga di ogni connessione corrisponde a come il server l'ha chiusa:
         server "RST..."                  -> StatusDetail RESET
         server "FIN..." o chiusura pulita -> StatusDetail CLOSED

Funziona anche su un report della versione vecchia (senza StatusDetail): in quel caso usa la colonna
Status e mostra il comportamento da correggere (ultima riga quasi sempre "Active").
Solo libreria standard (Python 3.8+).
"""

import bisect
import collections
import csv
import datetime
import statistics
import sys

IP_SERVER = "10.0.2.2"
TOLLERANZA_S = 3.0      # scarto massimo (s) tra aperture abbinate, dopo la correzione dello sfasamento


def leggi_orario(testo):
    testo = testo.strip().replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(testo)
    except ValueError:
        return datetime.datetime.strptime(testo[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)


def leggi_manana(percorso):
    with open(percorso, newline="", encoding="utf-8-sig") as f:
        prima = f.readline()
        f.seek(0)
        sep = ";" if prima.count(";") > prima.count(",") else ","
        lettore = csv.DictReader(f, delimiter=sep)
        colonne = lettore.fieldnames or []
        righe = list(lettore)
    connessioni, negative, altri = {}, [], {}
    for n, r in enumerate(righe, start=2):
        valori = {}
        for campo in ("BytesSent", "BytesRcvd", "PktsSent", "PktsRcvd"):
            try:
                valori[campo] = int(r.get(campo) or 0)
            except ValueError:
                valori[campo] = 0
            if valori[campo] < 0:
                negative.append((n, campo, valori[campo]))
        if (r.get("IPProto") or "").strip() != "6" or r.get("DstIp") != IP_SERVER:
            if (r.get("IPProto") or "").strip() == "6":     # traffico reale (non del server di riferimento)
                altri[(r.get("SrcPort"), r.get("DstIp"), r.get("DstPort"))] = (r.get("Status", ""), r.get("StatusDetail", ""))
            continue
        chiave = (r["SrcPort"], r["DstIp"], r["DstPort"])
        c = connessioni.get(chiave)
        if c is None:
            c = connessioni[chiave] = {"srcport": r["SrcPort"], "dstport": int(r["DstPort"]),
                                       "inviati": 0, "ricevuti": 0, "pkt_inv": 0, "pkt_ric": 0,
                                       "inizio": leggi_orario(r["FirstSeen"]), "righe": 0}
        c["inviati"] += valori["BytesSent"]
        c["ricevuti"] += valori["BytesRcvd"]
        c["pkt_inv"] += valori["PktsSent"]
        c["pkt_ric"] += valori["PktsRcvd"]
        c["righe"] += 1
        c["ultimo_status"] = r.get("Status", "")
        c["ultimo_dettaglio"] = r.get("StatusDetail", "")
    return colonne, len(righe), list(connessioni.values()), negative, altri


def leggi_server(percorso):
    with open(percorso, newline="", encoding="utf-8-sig") as f:
        return [{"apertura": leggi_orario(r["ora_apertura"]), "scenario": r["scenario"],
                 "chiusura": r["chiusura"], "rx": int(r["byte_ricevuti"]), "tx": int(r["byte_inviati"]),
                 "porta": int(r["porta_server"])} for r in csv.DictReader(f)]


def byte_ok(c, s):
    a, b = c["inviati"] - s["rx"] - 60, c["ricevuti"] - s["tx"] - 48
    return a >= 0 and b >= 0 and a % 40 == 0 and b % 40 == 0


def abbina(conn, server):
    per_m, per_s = collections.defaultdict(list), collections.defaultdict(list)
    for c in conn:
        per_m[c["dstport"]].append(c)
    for s in server:
        per_s[s["porta"]].append(s)
    porte = [p for p in per_m if per_s.get(p)]
    if not porte:
        raise SystemExit("Nessuna porta in comune tra report e registro del server: sono della stessa sessione?")
    # 1) stima grossolana dello sfasamento tra l'orologio dell'emulatore e quello del PC: il valore piu'
    #    frequente tra le differenze (apertura server - apertura Manana) sulla stessa porta
    diffs = sorted((s["apertura"] - c["inizio"]).total_seconds()
                   for p in porte for c in per_m[p] for s in per_s[p])
    centro, n_max = diffs[0], -1
    for d in diffs:
        n = bisect.bisect_right(diffs, d + TOLLERANZA_S) - bisect.bisect_left(diffs, d - TOLLERANZA_S)
        if n > n_max:
            centro, n_max = d, n
    grossolano = statistics.median([d for d in diffs if abs(d - centro) <= TOLLERANZA_S])
    # 2) si tengono solo le righe del server cadute durante la cattura di Manana: le righe di una prova
    #    precedente (registro non azzerato) non devono falsare il confronto
    t0 = min(c["inizio"] for c in conn) + datetime.timedelta(seconds=grossolano - 30)
    t1 = max(c["inizio"] for c in conn) + datetime.timedelta(seconds=grossolano + 30)
    for p in list(per_s):
        per_s[p] = [s for s in per_s[p] if t0 <= s["apertura"] <= t1]
    porte = [p for p in per_m if per_s.get(p)]
    # 3) sfasamento definitivo: mediana, sulle porte, tra la prima apertura del server e la prima di Manana
    offset = statistics.median((min(s["apertura"] for s in per_s[p]) - min(c["inizio"] for c in per_m[p]))
                               .total_seconds() for p in porte)
    coppie, senza = [], 0
    for p in porte:
        liberi = sorted(per_s[p], key=lambda s: s["apertura"])
        for c in sorted(per_m[p], key=lambda c: c["inizio"]):
            # Piu' connessioni aperte quasi insieme sulla stessa porta (es. quella con la richiesta e quella
            # "di riserva" che Chrome apre in anticipo) possono arrivare al server in ordine diverso da quello
            # in cui Manana le vede. A parita' di vicinanza nel tempo si preferisce quindi l'abbinamento
            # i cui byte tornano; se nessuno torna, il piu' vicino nel tempo.
            migliore, chiave_min = None, None
            for s in liberi:
                scarto = abs((s["apertura"] - c["inizio"]).total_seconds() - offset)
                if scarto > TOLLERANZA_S:
                    continue
                chiave = (0 if byte_ok(c, s) else 1, scarto)
                if chiave_min is None or chiave < chiave_min:
                    migliore, chiave_min = s, chiave
            if migliore is None:
                senza += 1
                continue
            liberi.remove(migliore)
            coppie.append((c, migliore))
    return coppie, offset, senza


def atteso(chiusura):
    testo = chiusura.upper()
    if "RST" in testo:
        return "RESET"
    if testo.startswith("FIN") or "(FIN)" in testo or "SENZA RISPOSTA" in testo:
        return "CLOSED"
    return None     # es. handshake TLS non completato: chiusura decisa dal client, non valutata


def main(file_manana, file_server):
    colonne, n_righe, conn, negative, altri = leggi_manana(file_manana)
    nuova = "StatusDetail" in colonne
    print(f"Report: {n_righe} righe, {len(conn)} connessioni TCP verso {IP_SERVER}")
    print(f"[{'OK  ' if nuova else 'NO  '}] colonna StatusDetail presente"
          + ("" if nuova else "  -> report della versione VECCHIA: confronto fatto sulla colonna Status"))
    print(f"[{'OK  ' if not negative else 'ERR '}] valori negativi in byte/pacchetti: {len(negative)}")
    for n, campo, v in negative[:5]:
        print(f"         riga {n}: {campo} = {v}")

    coppie, offset, senza = abbina(conn, leggi_server(file_server))
    print(f"Abbinate al server: {len(coppie)} connessioni (sfasamento stimato {offset:.1f} s; non abbinate: {senza})")

    ok_byte = 0
    per_scenario = collections.defaultdict(lambda: [0, 0])
    non_riconciliate = []
    for c, s in coppie:
        a, b = c["inviati"] - s["rx"] - 60, c["ricevuti"] - s["tx"] - 48
        ok = byte_ok(c, s)
        ok_byte += ok
        if not ok and s["scenario"] != "TLS_NORMALE":
            non_riconciliate.append((s["scenario"], c["srcport"], c["righe"], c["inviati"], s["rx"], a, c["ricevuti"], s["tx"], b))
        per_scenario[s["scenario"]][0] += ok
        per_scenario[s["scenario"]][1] += 1
    print(f"[info] riconciliazione dei byte: {ok_byte} su {len(coppie)} (nella tesi: 311 su 349 con la versione vecchia)")
    print("       per scenario: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(per_scenario.items())))
    print("       (TLS_NORMALE non puo' riconciliare: il server conta i byte in chiaro, Manana quelli cifrati)")
    for sc, sp, nr, inv, rx, a, ric, tx, b in non_riconciliate[:20]:
        print(f"       non riconcilia: {sc:<15} porta client {sp:<6} righe {nr}  inviati {inv} (server {rx}, scarto {a})  "
              f"ricevuti {ric} (server {tx}, scarto {b})")

    print("\nStato nell'ultima riga di ogni connessione, per scenario del server:")
    tabella = collections.defaultdict(collections.Counter)
    giusti = valutati = 0
    errori = []
    for c, s in coppie:
        trovato = (c["ultimo_dettaglio"] if nuova else c["ultimo_status"]) or "(vuoto)"
        tabella[(s["scenario"], s["chiusura"])][trovato] += 1
        e = atteso(s["chiusura"])
        if e is None or not nuova:
            continue
        valutati += 1
        if trovato == e:
            giusti += 1
        else:
            errori.append((s["scenario"], s["chiusura"], e, trovato, c["srcport"]))
    for (scenario, chiusura), conteggi in sorted(tabella.items()):
        e = atteso(chiusura) or "-"
        print(f"  {scenario:<18} server: {chiusura[:38]:<38} atteso {e:<7} trovato {dict(conteggi)}")

    if not nuova:
        print("\nReport della versione vecchia: nessun esito, serve un report prodotto dall'app corretta.")
        return 1
    print(f"\n[{'OK  ' if valutati and giusti == valutati else 'DIFF'}] stato finale corretto in "
          f"{giusti} connessioni su {valutati} valutate")
    for scenario, chiusura, e, trovato, porta in errori[:15]:
        print(f"         {scenario} (porta client {porta}): server '{chiusura}', atteso {e}, trovato {trovato}")
    if any(t in ("CONNECTED", "CONNECTING", "NEW") for *_, t, _ in errori):
        print("  Nota: CONNECTED/CONNECTING nell'ultima riga = connessione ancora aperta quando hai fermato la\n"
              "  cattura. Aspetta almeno 30 s dopo l'ultima navigazione prima di fermarla.")
    if altri:
        stati = collections.Counter((d if nuova else st) or "(vuoto)" for st, d in altri.values())
        print(f"\nTraffico reale (non del server di riferimento): {len(altri)} connessioni TCP, "
              f"stato nell'ultima riga: {dict(stati)}")
        print("  (nessun riferimento per confronto: serve solo a vedere che gli stati siano plausibili)")
    return 0 if valutati and giusti == valutati and not negative else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python verifica_dumpcsv.py <report_manana.csv> <server_log.csv>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
