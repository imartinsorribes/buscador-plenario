"""Banco de pruebas de identificación por VOZ: simula el registro (consentido) de cada
orador con sus primeros ~15 s y mide qué % del pleno se identifica SOLO por voz.

(Optimista: registro y prueba salen de la misma sesión/micro; sirve para probar el concepto
de identificación de conjunto cerrado, no la robustez entre sesiones distintas.)
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.speakers import _name_sim
from src.voiceid import _embed_spans, _load_audio

SKIP = {"Presidencia", "(sin identificar)", "(miembro del Gobierno)", ""}
ENROLL = 15.0

d = json.loads(Path("data/transcripts/kO3eztYBvDo_b.json").read_text(encoding="utf-8"))
segs = sorted(d["segments"], key=lambda s: s.get("start", 0.0))
spans, namec = defaultdict(list), defaultdict(Counter)
for s in segs:
    spk = s.get("speaker")
    if not spk or s.get("end", 0) <= s.get("start", 0):
        continue
    spans[spk].append((s["start"], s["end"]))
    nm = (s.get("name") or "").strip()
    if nm not in SKIP:
        namec[spk][nm] += 1
truename = {spk: (namec[spk].most_common(1)[0][0] if namec[spk] else None) for spk in spans}

wav = _load_audio("data/raw_audio/kO3eztYBvDo.wav")
enrolled, tests = {}, []
for spk, sp in spans.items():
    tn = truename[spk]
    if not tn:
        continue
    en, acc, rest = [], 0.0, []
    for st, e in sorted(sp):                       # primeros ENROLL s = registro; resto = prueba
        if acc < ENROLL:
            cut = min(e, st + (ENROLL - acc)); en.append((st, cut)); acc += cut - st
            if e > cut:
                rest.append((cut, e))
        else:
            rest.append((st, e))
    if tn not in enrolled:
        ev = _embed_spans(wav, en, ENROLL)
        if ev is not None:
            enrolled[tn] = ev
    if rest:
        tests.append((spk, tn, rest))

names = list(enrolled)
E = np.array([enrolled[n] for n in names])
print(f"registrados: {len(names)} personas · clusters a identificar: {len(tests)}")
ok, rows = 0, []
for spk, tn, rest in tests:
    v = _embed_spans(wav, rest, 30)
    if v is None:
        continue
    sims = E @ v
    j = int(np.argmax(sims))
    pred = names[j]
    hit = _name_sim(pred, tn) >= 0.6
    ok += hit
    dur = sum(e - st for st, e in rest)
    rows.append((hit, spk, tn, pred, float(sims[j]), dur))
print(f"ACIERTO crudo (forzando match): {ok}/{len(rows)} = {100*ok//max(len(rows),1)}%")

# --- con UMBRAL: marca '(por revisar)' lo de baja confianza en vez de adivinar ---
THR = 0.65
ttime = sum(r[5] for r in rows)
ok_t = sum(r[5] for r in rows if r[4] >= THR and r[0])
wrong_t = sum(r[5] for r in rows if r[4] >= THR and not r[0])
unk_t = sum(r[5] for r in rows if r[4] < THR)
conf = [r for r in rows if r[4] >= THR]
people = {r[2] for r in rows}
covered = {r[2] for r in rows if r[4] >= THR and r[0]}
print(f"\n--- con umbral {THR} (no adivinar; marcar '(por revisar)') ---")
print(f"  PRECISIÓN cuando da nombre: {sum(1 for r in conf if r[0])}/{len(conf)} clusters "
      f"= {100*sum(1 for r in conf if r[0])//max(len(conf),1)}%")
print(f"  Por TIEMPO de palabra: identificado bien {100*ok_t/ttime:.0f}% · "
      f"por revisar {100*unk_t/ttime:.0f}% · erróneo {100*wrong_t/ttime:.0f}%")
print(f"  PERSONAS cubiertas (≥1 cluster con su nombre): {len(covered)}/{len(people)}\n")
for hit, spk, tn, pred, sc, dur in sorted(rows, key=lambda r: r[4]):
    tag = "OK" if hit else "XX"
    conf_tag = "" if sc >= THR else "  (por revisar)"
    print(f"  {tag} {spk:11s} {dur:5.0f}s real={tn[:20]:20s} pred={pred[:20]:20s} sim={sc:.2f}{conf_tag}")
