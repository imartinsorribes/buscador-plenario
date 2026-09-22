"""Valida el verificador de fidelidad: ¿separa lo respaldado de lo inventado?

Le da tres tipos de frase sobre el pleno y mide el grounding de cada una:
  - REALES      (sacadas del propio texto)         -> debe ser ALTO
  - PARÁFRASIS  (hechos verdaderos, reescritos)    -> debe ser ALTO (prueba que NO es regex)
  - FABRICADAS  (falsas)                            -> debe ser BAJO (debe marcarlas)
Si paráfrasis >> fabricadas, el verificador es consistente.

Uso:  python scripts/validate_verifier.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config  # noqa: E402
from src.diario import extract_text  # noqa: E402
from src.verify import faithfulness, split_sentences  # noqa: E402

cfg = load_config()
source = extract_text("data/diarios/DSCD-15-PL-109.pdf")

reales = split_sentences(source)[40:50]
parafrasis = [
    "La ministra de Hacienda rechazó las críticas del PP sobre los impuestos.",
    "Se debatió la falta de Presupuestos Generales del Estado.",
    "Hubo discusión sobre los aranceles de Estados Unidos.",
    "El Gobierno trató el problema ferroviario de cercanías en Cataluña.",
    "La oposición criticó la gestión económica del Gobierno.",
]
fabricadas = [
    "El Congreso aprobó por unanimidad subir el IVA al 25 por ciento.",
    "La diputada Gamarra anunció su dimisión durante el pleno.",
    "Se guardó un minuto de silencio por la victoria de la selección de fútbol.",
    "El ministro de Sanidad declaró el fin de la pandemia de gripe aviar.",
    "El pleno decidió trasladar el Congreso a la ciudad de Sevilla.",
]


def soportes(frases):
    r = faithfulness("\n".join(frases), source, cfg)
    return [c["support"] for c in r["claims"]]


sr, sp, sf = soportes(reales), soportes(parafrasis), soportes(fabricadas)
print(f"REALES     : media {np.mean(sr):.3f}  (min {min(sr):.3f})")
print(f"PARÁFRASIS : media {np.mean(sp):.3f}  (min {min(sp):.3f})   <- hechos verdaderos reescritos")
print(f"FABRICADAS : media {np.mean(sf):.3f}  (max {max(sf):.3f})   <- falsas")
print(f"\nSeparación  paráfrasis - fabricadas = {np.mean(sp) - np.mean(sf):+.3f}")
print("(clara y positiva => distingue verdad de invención = consistente)")
th = 0.6
print(f"\nCon umbral {th}:  paráfrasis aceptadas {sum(x >= th for x in sp)}/{len(sp)}  ·  "
      f"fabricadas marcadas {sum(x < th for x in sf)}/{len(sf)}")
print("\nDetalle fabricadas:")
for f, s in zip(fabricadas, sf):
    print(f"  {s:.3f}  {f}")
