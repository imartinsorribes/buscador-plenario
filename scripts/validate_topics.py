"""Valida assign_topics (etiquetado de temas) sobre un Diario.

Mide:
  1) Cobertura  — % de intervenciones con tema asignado.
  2) Nº de temas distintos.
  3) COHERENCIA — coseno medio de embeddings DENTRO de cada tema vs pares aleatorios.
     Si intra-tema > aleatorio, el etiquetado agrupa contenido parecido (funciona).
  4) Vistazo de los temas principales con sus oradores.

Uso:  python scripts/validate_topics.py [ruta_al_pdf]
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config  # noqa: E402
from src.diario import (assign_topics, attach_parties, extract_text,  # noqa: E402
                        parse_interventions)
from src.index import get_embedder  # noqa: E402

pdf = sys.argv[1] if len(sys.argv) > 1 else "data/diarios/DSCD-15-PL-109.pdf"
cfg = load_config()
text = extract_text(pdf)
ints = assign_topics(attach_parties(parse_interventions(text), text), text)
n = len(ints)

temas: dict[str, list[int]] = {}
for i, it in enumerate(ints):
    temas.setdefault(it.get("topic") or "—", []).append(i)
con_tema = n - len(temas.get("—", []))
distintos = [t for t in temas if t != "—"]

print(f"PDF: {Path(pdf).name}")
print(f"Intervenciones: {n}")
print(f"Con tema asignado: {con_tema} ({100 * con_tema // max(n, 1)}%)")
print(f"Temas distintos: {len(distintos)}\n")

vecs = np.array(get_embedder(cfg).encode(
    [it["text"][:500] for it in ints], normalize_embeddings=True, batch_size=4))


def intra(idxs: list[int]):
    if len(idxs) < 2:
        return None
    v = vecs[idxs]
    return float((v @ v.T)[np.triu_indices(len(idxs), 1)].mean())


grandes = sorted(((t, ix) for t, ix in temas.items() if t != "—"),
                 key=lambda x: -len(x[1]))[:6]
intra_means = [m for _, ix in grandes if (m := intra(ix)) is not None]
rng = np.random.default_rng(0)
pares = rng.integers(0, n, (300, 2))
aleatorio = float(np.mean([vecs[a] @ vecs[b] for a, b in pares]))

print(f"COHERENCIA (coseno medio):  intra-tema = {np.mean(intra_means):.3f}   "
      f"aleatorio = {aleatorio:.3f}")
print("  -> si intra-tema > aleatorio, los temas agrupan bien.\n")

print("Temas principales (nº intervenciones · tema · oradores):")
for t, ix in grandes:
    speakers = sorted({ints[i]["speaker"] for i in ix})[:5]
    print(f"  • [{len(ix):3}] {t[:62]}")
    print(f"        {', '.join(speakers)}")
