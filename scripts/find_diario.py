"""Encuentra el Diario de una fecha descargando un rango de DSCD y leyendo su cabecera.

Uso:  python scripts/find_diario.py "14 de octubre" 128 142
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import resolve_path  # noqa: E402
from src.diario import download_diario, extract_text, session_date  # noqa: E402

URL = "https://www.congreso.es/public_oficiales/L15/CONG/DS/PL/DSCD-15-PL-{n}.PDF"
target = sys.argv[1]
desde, hasta = int(sys.argv[2]), int(sys.argv[3])
out = resolve_path("data/diarios")

for n in range(desde, hasta + 1):
    try:
        pdf = download_diario(URL.format(n=n), out)
    except Exception:
        print(f"PL-{n}: (no disponible)")
        continue
    d = session_date(extract_text(pdf))
    hit = target.lower() in d.lower()
    print(f"PL-{n}: {d}{'   <-- MATCH' if hit else ''}")
    if hit:
        print(f"\nENCONTRADO: {pdf}")
        break
