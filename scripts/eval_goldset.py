"""WER real contra un GOLD SET verbatim (líneas '[mm:ss] texto'), antes y después de lexfix.

Mide la única forma fiable: comparar el ASR con una transcripción humana literal del mismo
tramo. Alinea cada línea del gold con el segmento del transcript por marca de tiempo.

Uso:  python scripts/eval_goldset.py <gold.txt> <transcript.json> [terms.txt]
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.eval_asr import _edit, _norm          # noqa: E402
from src.lexfix import correct_segments, load_terms_file  # noqa: E402


def parse_gold(path):
    out = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[(\d+):(\d+)\]\s*(.*)", ln.strip())
        if m:
            sec = int(m.group(1)) * 60 + int(m.group(2))
            out.append((sec, m.group(3).strip()))
    return out


def wer(gold_text, hyp_text):
    g, h = _norm(gold_text), _norm(hyp_text)
    e, n, subs = _edit(g, h)
    return e, n, subs


gold_path, tr_path = sys.argv[1], sys.argv[2]
terms_path = sys.argv[3] if len(sys.argv) > 3 else None

gold = parse_gold(gold_path)
data = json.loads(Path(tr_path).read_text(encoding="utf-8"))
segs = sorted(data["segments"], key=lambda s: s.get("start", 0))

# Comparación por VENTANA DE TIEMPO (robusta a cambios de segmentación): todo el texto del
# gold contra todos los segmentos del ASR en ese mismo tramo. No empareja línea a línea.
import copy
maxsec = max(sec for sec, _ in gold) + 5
window = [s for s in segs if s.get("start", 0) < maxsec]
gold_text = " ".join(g for _, g in gold)
raw_text = " ".join(s.get("text", "") for s in window)
fixed_segs = copy.deepcopy(window)
terms = load_terms_file(terms_path) if terms_path else []
_, changes = correct_segments(fixed_segs, terms) if terms else (None, [])
fixed_text = " ".join(s.get("text", "") for s in fixed_segs)

e0, n0, subs0 = wer(gold_text, raw_text)
e1, n1, subs1 = wer(gold_text, fixed_text)

print(f"Gold: {len(gold)} líneas · {n0} palabras de referencia · ASR ventana {len(_norm(raw_text))} palabras")
print(f"\nWER ASR crudo     : {e0/n0:6.1%}  ({e0} errores)   -> precisión {1-e0/n0:.1%}")
print(f"WER ASR + lexfix  : {e1/n1:6.1%}  ({e1} errores)   -> precisión {1-e1/n1:.1%}")
print(f"\nlexfix aplicó {len(changes)} corrección(es): " +
      ", ".join(f'{a!r}->{b!r}' for a, b in changes))
print(f"\n--- errores que QUEDAN (hyp -> gold), top 25 ---")
from collections import Counter
bag = Counter(f"{h} → {r}" for r, h in subs1 if r != h)
for k, c in bag.most_common(25):
    print(f"  {c:>2}x  {k}")
