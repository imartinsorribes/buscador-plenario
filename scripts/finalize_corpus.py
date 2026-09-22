"""Validación POR LEGISLATURA + mantenimiento del CSV de revisión + ZIP, tras regenerar.

- Métricas: % sin partido y multipartido DENTRO de cada legislatura (la incoherencia real).
- Top diputados por legislatura (lo que de verdad se va a estudiar -> deben ser correctos).
- UPSERT en data/party_overrides.csv sin pisar tus correcciones (party_correcto).
- Rehace el ZIP del corpus.
"""
import csv
import glob
import json
import os
import shutil
import unicodedata
from collections import Counter, defaultdict

JSON_DIR = "data/diarios_json"
OVR = "data/party_overrides.csv"
FIELDS = ["speaker", "legislatura", "problema", "party_actual", "party_correcto", "n"]


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", (s or "").replace("\n", " "))
                    .encode("ascii", "ignore").decode().upper().split())


def main() -> None:
    byleg = defaultdict(lambda: defaultdict(Counter))   # leg -> speaker -> Counter(party)
    roles, san, san_party, party_values = Counter(), Counter(), Counter(), Counter()
    dip = empty = 0
    vplenos = vtot = topok = topall = nplenos = 0
    for f in glob.glob(f"{JSON_DIR}/*.json"):
        data = json.load(open(f, encoding="utf-8"))
        leg = str(data.get("legislatura", "?"))
        nplenos += 1
        if data["votaciones"]:
            vplenos += 1
            vtot += len(data["votaciones"])
        for it in data["interventions"]:
            roles[it["role"]] += 1
            party_values[it["party"] or "(vacío)"] += 1
            topall += 1
            if it.get("topic"):
                topok += 1
            if "SANCHEZ PEREZ" in norm(it["speaker"]):
                san[it["role"]] += 1
                san_party[it["party"] or "(vacío)"] += 1
            if it["role"] != "diputado":
                continue
            dip += 1
            p = it["party"] or ""
            if not p:
                empty += 1
            byleg[leg][it["speaker"]][p or "(vacio)"] += 1

    # incoherencia = mismo orador con >1 partido DENTRO de una legislatura
    multi = []          # (leg, speaker, parties, n)
    miss = defaultdict(int)
    for leg, spk in byleg.items():
        for s, c in spk.items():
            parties = [p for p in c if p != "(vacio)"]
            if len(parties) > 1:
                multi.append((leg, s, parties, sum(c.values())))
            if "(vacio)" in c:
                miss[s] += c["(vacio)"]

    print(f"diputado-interv: {dip} | party vacio: {empty} ({100*empty/max(dip,1):.1f}%) | "
          f"multipartido DENTRO de legislatura: {len(multi)}")
    print("ROLES:", dict(roles.most_common()))
    print("VALORES de party (debe ser solo siglas/'(vacío)', NUNCA Gobierno/Presidencia):")
    print("   ", dict(party_values.most_common()))
    print("Sanchez Perez-Castejon -> party:", dict(san_party), "| role:", dict(san))
    print(f"VOTACIONES: {vplenos}/{nplenos} plenos ({100*vplenos//max(nplenos,1)}%) · {vtot} votaciones | "
          f"TOPIC no vacío: {100*topok//max(topall,1)}%")

    # comprobaciones puntuales por legislatura
    def check(needle: str) -> None:
        rows = []
        for leg in sorted(byleg):
            for s, c in byleg[leg].items():
                if needle in norm(s):
                    rows.append(f"L{leg}:{'/'.join(p for p in c if p!='(vacio)') or '—'}({sum(c.values())})")
        print(f"    {needle:26s} -> {'  '.join(rows) if rows else 'no aparece'}")
    print("COMPROBACIONES (coherencia por legislatura):")
    for nd in ["BALDOVI", "RUFIAN ROMERO", "RUFAAN", "RIVERA DIAZ", "GARZON ESPINOSA",
               "ORAMAS", "ESPINOSA DE LOS MONTEROS", "BELARRA"]:
        check(nd)

    # top diputados por legislatura (lo que se va a estudiar)
    for leg in sorted(byleg):
        tops = sorted(byleg[leg].items(), key=lambda x: -sum(x[1].values()))[:10]
        print(f"--- TOP diputados Legislatura {leg} ---")
        for s, c in tops:
            parties = "/".join(p for p in c if p != "(vacio)") or "—"
            print(f"   {sum(c.values()):4d}  {s[:32]:32s}  {parties}")

    # --- upsert del CSV de overrides (preserva party_correcto del usuario) ---
    existing: dict[tuple, dict] = {}
    order: list[tuple] = []
    if os.path.exists(OVR):
        with open(OVR, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                k = ((row.get("legislatura") or "").strip(), norm(row.get("speaker", "")))
                if k[1]:
                    existing[k] = row
                    order.append(k)
    todo = [(s, leg, "multipartido", "/".join(ps), n) for leg, s, ps, n in
            sorted(multi, key=lambda x: -x[3])]
    todo += [(s, "", "sin_partido", "", n) for s, n in
             sorted(miss.items(), key=lambda x: -x[1])]
    for speaker, leg, prob, act, n in todo:
        k = (str(leg), norm(speaker))
        if k in existing:
            existing[k].update({"speaker": speaker, "legislatura": str(leg),
                                "problema": prob, "party_actual": act, "n": str(n)})
        else:
            existing[k] = {"speaker": speaker, "legislatura": str(leg), "problema": prob,
                           "party_actual": act, "party_correcto": "", "n": str(n)}
            order.append(k)
    with open(OVR, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, restval="", extrasaction="ignore")
        w.writeheader()
        for k in order:
            w.writerow(existing[k])
    filled = sum(1 for r in existing.values() if (r.get("party_correcto") or "").strip())
    print(f"override -> {OVR}: {len(order)} filas ({filled} ya corregidas, {len(todo)} pendientes)")

    path = shutil.make_archive("data/diarios_congreso_2016-2026", "zip", JSON_DIR)
    print("ZIP:", round(os.path.getsize(path) / 1024 / 1024, 1), "MB")


if __name__ == "__main__":
    main()
