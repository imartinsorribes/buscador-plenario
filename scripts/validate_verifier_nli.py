"""Valida el verificador NLI (entailment) con las mismas 3 categorías que el de embeddings,
para comparar. REALES/PARÁFRASIS deben dar entailment alto; FABRICADAS, bajo.

Uso:  python scripts/validate_verifier_nli.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config  # noqa: E402
from src.diario import extract_text  # noqa: E402
from src.verify import faithfulness_nli, prepare_source, split_sentences  # noqa: E402

cfg = load_config()
source_text = extract_text("data/diarios/DSCD-15-PL-109.pdf")
source = prepare_source(source_text, cfg)  # embeber la fuente UNA sola vez

reales = split_sentences(source_text)[40:50]
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


def ent(frases):
    r = faithfulness_nli("\n".join(frases), cfg=cfg, source=source)
    return [c["entail"] for c in r["claims"]]


sr, sp, sf = ent(reales), ent(parafrasis), ent(fabricadas)
print(f"REALES     : entailment medio {np.mean(sr):.3f}")
print(f"PARÁFRASIS : entailment medio {np.mean(sp):.3f}  (min {min(sp):.3f})")
print(f"FABRICADAS : entailment medio {np.mean(sf):.3f}  (max {max(sf):.3f})")
print(f"\nSeparación  paráfrasis - fabricadas = {np.mean(sp) - np.mean(sf):+.3f}")
print("(comparar con el de embeddings, que dio +0.086)")
th = 0.5
print(f"\nCon umbral {th}:  paráfrasis aceptadas {sum(x >= th for x in sp)}/{len(sp)}  ·  "
      f"fabricadas marcadas {sum(x < th for x in sf)}/{len(sf)}")
print("\nDetalle fabricadas:")
for f, s in zip(fabricadas, sf):
    print(f"  {s:.3f}  {f}")
