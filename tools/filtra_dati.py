# -*- coding: utf-8 -*-
"""
filtra_dati.py - Tiene del report di Manana solo le righe verso il server di riferimento (10.0.2.2).

Serve a pubblicare i dati della prova senza il traffico reale registrato dall'emulatore (siti visitati, DNS di
Google, ecc.). Uso:  python filtra_dati.py <report_manana.csv> <report_filtrato.csv>
"""
import csv
import sys

IP_SERVER = "10.0.2.2"

if len(sys.argv) != 3:
    raise SystemExit("Uso: python filtra_dati.py <report_manana.csv> <report_filtrato.csv>")
with open(sys.argv[1], newline="", encoding="utf-8-sig") as f:
    lettore = csv.reader(f)
    intestazione = next(lettore)
    col = intestazione.index("DstIp")
    righe = [r for r in lettore if len(r) > col and r[col] == IP_SERVER]
with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
    scrittore = csv.writer(f)
    scrittore.writerow(intestazione)
    scrittore.writerows(righe)
print(f"{len(righe)} righe verso {IP_SERVER} scritte in {sys.argv[2]}")
