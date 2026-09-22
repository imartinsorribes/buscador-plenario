"""¿La diarización detecta que es la MISMA VOZ? (consistencia de voz, no de nombre).

El "acierto de orador" mide si el NOMBRE coincide con el Diario; pero en el producto el nombre
lo pone un humano UNA vez por voz. Lo que importa es si cada persona cae SIEMPRE en el mismo
cluster (y si cada cluster es UNA sola persona). Eso es lo que medimos aquí: alineamos nuestras
intervenciones (por su CLUSTER de voz) con las del Diario oficial (por contenido) y miramos el
mapa cluster <-> orador.

Uso:  python -m scripts.eval_voice <transcript.json> <oficial.json>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config                       # noqa: E402
from src.index import get_embedder                       # noqa: E402
from scripts.compare_diario import _align, substantive   # noqa: E402

tr = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
offi = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

# NUESTRAS intervenciones agrupadas por CLUSTER de voz (no por nombre)
ours = []
for s in sorted(tr["segments"], key=lambda x: x.get("start", 0)):
    txt = (s.get("text") or "").strip()
    if not txt:
        continue
    cl = s.get("speaker") or "?"
    if ours and ours[-1]["who"] == cl:
        ours[-1]["text"] += " " + txt
    else:
        ours.append({"who": cl, "text": txt})
O = [x for x in ours if len(x["text"]) > 120]
F = substantive(offi)

emb = get_embedder(load_config())
OV = np.asarray(emb.encode([x["text"] for x in O], normalize_embeddings=True, batch_size=8))
FV = np.asarray(emb.encode([x["text"] for x in F], normalize_embeddings=True, batch_size=8))
S = OV @ FV.T
pairs = [(a, b) for a, b in _align(S) if S[a, b] >= 0.5]
base = [(a, b) for a, b in pairs if S[a, b] >= 0.8] or pairs   # pares = MISMA intervención

name2cl, cl2name = defaultdict(set), defaultdict(set)
for a, b in base:
    name2cl[F[b]["who"]].add(O[a]["who"])
    cl2name[O[a]["who"]].add(F[b]["who"])

consistent = sum(1 for cls in name2cl.values() if len(cls) == 1)
pure = sum(1 for nms in cl2name.values() if len(nms) == 1)
print(f"Pares de contenido fiables (misma intervención): {len(base)}")
print(f"\nORADORES oficiales cubiertos: {len(name2cl)}")
print(f"  → con UNA sola voz (consistencia): {consistent}/{len(name2cl)} = {consistent/max(len(name2cl),1):.0%}")
print(f"CLUSTERS de voz usados: {len(cl2name)}")
print(f"  → con UN solo orador (pureza):     {pure}/{len(cl2name)} = {pure/max(len(cl2name),1):.0%}")
print("\n-- orador oficial -> cluster(es) de voz (>1 = voz partida) --")
for nm, cls in sorted(name2cl.items(), key=lambda kv: -len(kv[1])):
    flag = "  <-- PARTIDA" if len(cls) > 1 else ""
    print(f"  {nm:34s} {sorted(cls)}{flag}")
