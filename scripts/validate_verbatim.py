"""Mide la PRECISIÓN REAL del ASR contra un gold VERBATIM (palabra por palabra).

A diferencia de validate_transcription.py (recall vs el Diario, que NO es literal y por
eso nunca da 100%), esto calcula WER/accuracy contra un texto transcrito a mano de un
tramo del pleno. Es la métrica honesta para afirmar "95-99%", y la única posible en
municipios sin Diario (se verifica a mano un par de minutos).

Preparar el gold:
  1) elige un tramo limpio, p.ej. 0:00–3:00, y transcríbelo EXACTO en un .txt
  2) extrae el ASR de ese mismo tramo y compáralo.

Uso:
  python scripts/validate_verbatim.py <whisper.json> <gold.txt> [inicio_seg] [fin_seg]
"""
import json
import re
import sys
import unicodedata
from pathlib import Path


def norm_words(text: str) -> list[str]:
    """minúsculas, sin acentos ni puntuación -> lista de palabras (comparación justa)."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return t.split()


def wer(ref: list[str], hyp: list[str]) -> dict:
    """Word Error Rate por distancia de edición a nivel de palabra (Levenshtein DP)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    # backtrace para contar S/D/I
    i, j, S = n, m, 0
    while i > 0 and j > 0:
        if ref[i - 1] == hyp[j - 1] and d[i][j] == d[i - 1][j - 1]:
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j - 1] + 1:
            S += 1; i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    edits = d[n][m]
    return {"wer": edits / max(n, 1), "accuracy": 1 - edits / max(n, 1),
            "ref_words": n, "hyp_words": m, "errores": edits, "sustituciones": S}


def main() -> None:
    whisper_json, gold_txt = sys.argv[1], sys.argv[2]
    ini = float(sys.argv[3]) if len(sys.argv) > 3 else None
    fin = float(sys.argv[4]) if len(sys.argv) > 4 else None

    wt = json.loads(Path(whisper_json).read_text(encoding="utf-8"))
    segs = wt["segments"]
    if ini is not None:
        segs = [s for s in segs if s["start"] >= ini and s["start"] < (fin if fin is not None else 1e9)]
    hyp = norm_words(" ".join(s["text"] for s in segs))
    ref = norm_words(Path(gold_txt).read_text(encoding="utf-8"))

    r = wer(ref, hyp)
    print(f"Gold: {r['ref_words']} palabras · ASR: {r['hyp_words']} palabras"
          + (f"  (tramo {ini}-{fin}s)" if ini is not None else ""))
    print(f"WER:       {r['wer']:.1%}")
    print(f"Precisión: {r['accuracy']:.1%}   (objetivo >= 95%)")
    print(f"Errores:   {r['errores']}  (sustituciones ~{r['sustituciones']})")


if __name__ == "__main__":
    main()
