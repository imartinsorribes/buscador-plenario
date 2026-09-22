"""Precisión REAL del ASR contra el Diario oficial, sin que la EDICIÓN del Diario
contamine la medida.

El Diario de Sesiones no es literal: limpia muletillas, reordena y reescribe números.
Por eso el "recall de tokens" crudo da numeros bajísimos aunque la transcripción sea buena.

Método honesto:
  1) Partimos Whisper y Diario en frases.
  2) Alineamos cada frase de Whisper con su frase MÁS PARECIDA del Diario (semántica).
  3) Nos quedamos solo con los pares CASI LITERALES (similitud >= --sim): ahí el Diario
     sí es comparable palabra a palabra.
  4) En esos pares medimos el WER real (errores / palabras) y sacamos los fallos concretos.

Así medimos el ASR donde el Diario es comparable, y los "fallos" que salen son fallos
DE VERDAD (candidatos a glosario), no ediciones.

Uso:  python scripts/eval_asr.py <whisper.json> <diario.pdf> [--sim 0.85]
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config            # noqa: E402
from src.diario import extract_text           # noqa: E402
from src.index import get_embedder            # noqa: E402
from src.verify import split_sentences        # noqa: E402


def _norm(s: str) -> list[str]:
    """Normaliza para comparar: minúsculas, sin tildes, sin puntuación, miles sin separador."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"(?<=\d)[.](?=\d{3}\b)", "", s)   # 1.200 -> 1200
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)          # 10,60 -> 10.60 (coma decimal)
    s = re.sub(r"[^0-9a-zñ\s]", " ", s)
    return s.split()


def _edit(ref: list[str], hyp: list[str]):
    """Levenshtein a nivel palabra + backtrace para listar las sustituciones (fallos)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
    # backtrace
    subs = []
    i, j = n, m
    while i > 0 and j > 0:
        if ref[i - 1] == hyp[j - 1]:
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j - 1] + 1:
            subs.append((ref[i - 1], hyp[j - 1])); i, j = i - 1, j - 1   # sustitución
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1                                                        # borrado
        else:
            j -= 1                                                        # inserción
    return d[n][m], n, subs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("whisper")
    ap.add_argument("diario")
    ap.add_argument("--sim", type=float, default=0.85, help="umbral de 'casi literal'")
    ap.add_argument("--minw", type=int, default=10, help="mín. palabras de la frase (evita muletillas)")
    a = ap.parse_args()

    cfg = load_config()
    w = json.loads(Path(a.whisper).read_text(encoding="utf-8"))
    hyp_sents = [s["text"].strip() for s in w["segments"] if s["text"].strip()]
    ref_sents = [s for s in split_sentences(extract_text(a.diario)) if len(s.split()) >= 5]

    emb = get_embedder(cfg)
    HV = np.asarray(emb.encode(hyp_sents, normalize_embeddings=True, batch_size=16))
    RV = np.asarray(emb.encode(ref_sents, normalize_embeddings=True, batch_size=16))

    err = tot = pairs = 0
    sims = []
    bag = Counter()
    for hi, hv in enumerate(HV):
        sc = RV @ hv
        ri = int(sc.argmax()); best = float(sc[ri])
        if best < a.sim:
            continue
        rw, hw = _norm(ref_sents[ri]), _norm(hyp_sents[hi])
        if len(rw) < a.minw or len(hw) < a.minw:
            continue
        e, n, subs = _edit(rw, hw)
        if n == 0:
            continue
        err += e; tot += n; pairs += 1; sims.append(best)
        for r, h in subs:
            if not r.isdigit() and not h.isdigit() and r != h:
                bag[f"{h}  →  {r}"] += 1

    if not tot:
        print("Sin pares casi-literales: baja --sim."); return
    print(f"=== ASR real: {Path(a.whisper).stem}  vs  {Path(a.diario).stem} ===")
    print(f"Frases Whisper: {len(hyp_sents)} · frases Diario: {len(ref_sents)}")
    print(f"Pares casi literales (sim>={a.sim}): {pairs}  (sim media {np.mean(sims):.3f})")
    print(f"Palabras comparadas: {tot}")
    print(f"WER real en esos tramos: {err/tot:.1%}   ->  precisión ~{1-err/tot:.1%}")
    print(f"\nFallos ASR más repetidos (whisper → diario), candidatos a GLOSARIO:")
    for k, c in bag.most_common(30):
        print(f"  {c:>2}x  {k}")


if __name__ == "__main__":
    main()
