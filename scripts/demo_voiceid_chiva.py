"""Demo/validación del reconocimiento por voz entre sesiones en Chiva (sin Diario).

1) PRUEBA "más info = mejor": empareja cada voz del pleno 2 con su voz del pleno 1 usando
   (a) UNA huella promedio  vs  (b) VARIAS huellas (multi-vector). Muestra que multi >= single.
2) PERSISTE las huellas del pleno 1 en data/voiceprints/chiva.json (multi-vector, acumulable).
3) VALIDA end-to-end con la función real suggest_from_voiceprints sobre el pleno 2.
"""
import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
import src.voiceid as vid

W1, W2 = "data/raw_audio/e2fGiHP2XcY.wav", "data/raw_audio/TN_gTdxQXA4.wav"
tr1 = json.load(open("data/transcripts/e2fGiHP2XcY.json", encoding="utf-8"))
tr2 = json.load(open("data/transcripts/TN_gTdxQXA4.json", encoding="utf-8"))
wav1, wav2 = vid._load_audio(W1), vid._load_audio(W2)


def spans(tr):
    b = defaultdict(list)
    for s in tr["segments"]:
        if s.get("speaker") and s.get("end", 0) > s.get("start", 0):
            b[s["speaker"]].append((s["start"], s["end"]))
    return b


sp1, sp2 = spans(tr1), spans(tr2)
secs = defaultdict(float)
for s in tr2["segments"]:
    if s.get("speaker"):
        secs[s["speaker"]] += s.get("end", 0) - s.get("start", 0)

# pleno 1: una huella promedio  vs  multi-vector
single = {c: vid._embed_spans(wav1, sp) for c, sp in sp1.items()}
multi = {c: vid._embed_exemplars(wav1, sp) for c, sp in sp1.items()}
names1 = [c for c in sp1 if single[c] is not None]
Smat = np.array([single[c] for c in names1])
Mmats = [np.array(multi[c]) for c in names1]
nexe = {c: len(multi[c]) for c in names1}

# query pleno 2 (una huella por voz)
q2 = {c: vid._embed_spans(wav2, sp) for c, sp in sp2.items()}

print("=== 1) MAS INFO = MEJOR: sim de cada voz del pleno 2 a su mejor voz del pleno 1 ===")
print("    (single = 1 huella promedio · multi = varias huellas, empareja por la mejor)")
for c in sorted(q2, key=lambda x: -secs[x]):
    v = q2[c]
    if v is None:
        continue
    ss = float((Smat @ v).max())
    ms = max(float((M @ v).max()) for M in Mmats)
    print(f"  {c:11s} {secs[c]:5.0f}s  single={ss:.2f}  multi={ms:.2f}  Δ={ms - ss:+.2f}")

# 2) persistir pleno 1 (etiquetas provisionales = id de voz; en producción el humano las renombra)
labels = {c: {"name": "Voz " + c.replace("SPEAKER_", "")} for c in sp1}
n = vid.enroll_clusters(W1, tr1["segments"], labels, "chiva")
print(f"\n=== 2) PERSISTIDAS {n} huellas en data/voiceprints/chiva.json (multi-vector) ===")

# 3) validar end-to-end con la funcion real
res = vid.suggest_from_voiceprints(W2, tr2["segments"], "chiva")
total = len([c for c in sp2 if q2.get(c) is not None])
print(f"=== 3) suggest_from_voiceprints (funcion real) sobre el pleno 2 -> {len(res)}/{total} ===")
for c, d in sorted(res.items(), key=lambda x: -x[1]["sim"]):
    print(f"  {c:11s} -> {d['name']:9s} sim={d['sim']:.2f} n={d['n']}")
