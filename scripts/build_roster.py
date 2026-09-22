"""Construye un roster de diputados + Gobierno agregando los Diarios ya descargados.

Reusa src/diario.py (fuente OFICIAL): de cada DSCD saca (apellidos, sigla de grupo)
y los agrega. Sirve para que src/speakers.py enlace los nombres ruidosos del NER
(Whisper) con el nombre y partido reales -> entity linking, sin regex de nombres.

Salida: data/roster.json = [{"name","party","aliases":[norm],"n":conteo}].
Uso:  python scripts/build_roster.py
"""
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.diario import attach_parties, extract_text, parse_interventions  # noqa: E402

ROLE_WORDS = ("president", "vicepresident", "secretari")  # cargos de la Mesa (no enlazables)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def main() -> None:
    base = Path(__file__).resolve().parent.parent / "data" / "diarios"
    pdfs = sorted(set(list(base.glob("DSCD-15-PL-*.PDF")) + list(base.glob("DSCD-15-PL-*.pdf"))))
    party_of = defaultdict(Counter)   # norm_name -> Counter(party)
    disp_of = defaultdict(Counter)    # norm_name -> Counter(display)
    for i, p in enumerate(pdfs, 1):
        try:
            txt = extract_text(p)
            ivs = attach_parties(parse_interventions(txt), txt)
        except Exception as e:
            print(f"[{i}/{len(pdfs)}] skip {p.name}: {e}")
            continue
        for it in ivs:
            sp = it["speaker"].strip()
            party = it.get("party", "")
            name = sp.split(" (")[0].strip() if party == "Gobierno" else sp
            key = norm(name)
            if len(key) < 3 or any(w in key for w in ROLE_WORDS):
                continue
            party_of[key][party] += 1
            disp_of[key][name.title() if name.isupper() else name] += 1
        print(f"[{i}/{len(pdfs)}] {p.name}: {len(ivs)} intervenciones")

    roster = []
    for key, parties in party_of.items():
        party = next((p for p, _ in parties.most_common() if p), "")
        roster.append({
            "name": disp_of[key].most_common(1)[0][0],
            "party": party,
            "aliases": [key],
            "n": sum(parties.values()),
        })
    roster.sort(key=lambda r: -r["n"])
    out = base.parent / "roster.json"
    out.write_text(json.dumps(roster, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nROSTER: {len(roster)} personas -> {out}")
    for r in roster[:18]:
        print(f"   {r['name'][:34]:34s} | {r['party']:8s} | n={r['n']}")


if __name__ == "__main__":
    main()
