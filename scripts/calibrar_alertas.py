"""Calibración del umbral de alertas: enseña, por pleno y tema, las mejores
similitudes tema-fragmento para elegir UMBRAL mirando datos y no a ojo.

Uso: python scripts/calibrar_alertas.py [video_id ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np

from src.alertas import TEMAS, _centroides, _chunks_pleno
from src.config import load_config

VIDS = sys.argv[1:] or ["3L4k3rCtN40", "DSCD-15-PL-89", "DSCD-15-PL-134"]


def main():
    cfg = load_config()
    cent = _centroides(cfg)
    for vid in VIDS:
        chunks = _chunks_pleno(vid, cfg)
        print(f"\n=== {vid} · {len(chunks)} fragmentos ===")
        if not chunks:
            continue
        M = np.stack([c["emb"] for c in chunks])
        filas = []
        for tema in TEMAS:
            sims = M @ cent[tema]
            i = int(np.argmax(sims))
            filas.append((float(sims[i]), tema, chunks[i]["speaker"][:22],
                          chunks[i]["text"][:70].replace("\n", " ")))
        for s, tema, who, txt in sorted(filas, reverse=True):
            marca = "  <-- saltaría" if s >= 0.55 else ""
            print(f"  {s:.3f}  {tema:24} {who:24} {txt}{marca}")


if __name__ == "__main__":
    main()
