"""Comprueba la cobertura del mapeo orador->partido sobre un Diario."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.diario import attach_parties, extract_text, parse_interventions  # noqa: E402

pdf = sys.argv[1] if len(sys.argv) > 1 else "data/diarios/DSCD-15-PL-109.pdf"
text = extract_text(pdf)
ints = attach_parties(parse_interventions(text), text)

seen = {}
for it in ints:
    seen.setdefault(it["speaker"], it["party"])
with_party = {k: v for k, v in seen.items() if v}
print(f"{len(seen)} oradores distintos · {len(with_party)} con partido asignado\n")
for k, v in sorted(with_party.items()):
    print(f"  {k:34} {v}")
sin = [k for k, v in seen.items() if not v]
print(f"\nSin partido ({len(sin)}): {sin[:20]}")
