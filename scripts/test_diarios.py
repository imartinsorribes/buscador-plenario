"""Test anti-sesgo del parser del Diario de Sesiones.

Pasa el parser por todos los PDFs de data/diarios/ y reporta cuántas
intervenciones y oradores distintos extrae de cada uno. Sirve para comprobar
que el parser GENERALIZA entre legislaturas/años y no está sesgado a un pleno.

Uso:  python scripts/test_diarios.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.diario import extract_text, parse_interventions  # noqa: E402

diarios = sorted(Path("data/diarios").glob("*.pdf"))
print(f"{'PDF':30} {'interv.':>8} {'oradores':>9}")
print("-" * 50)
for p in diarios:
    try:
        ints = parse_interventions(extract_text(p))
        speakers = {i["speaker"] for i in ints}
        print(f"{p.name:30} {len(ints):8d} {len(speakers):9d}")
    except Exception as e:
        print(f"{p.name:30}  ERROR: {e}")

if diarios:
    last = sorted({i["speaker"] for i in parse_interventions(extract_text(diarios[-1]))})
    print(f"\nEjemplo de oradores en {diarios[-1].name}:")
    for s in last[:12]:
        print("  -", s)
