"""Bake-off de modelos ASR: compara varios Whisper sobre los MISMOS plenos con Diario oficial.

Para cada (modelo × pleno) mide:
  - parecido  : similitud semántica media de nuestro texto vs el Diario (BGE-M3, mejor match).
  - literal   : % de palabras nuestras que aparecen LITERAL en el Diario (en orden).
  - velocidad : factor sobre tiempo real (xRT) y segundos.
Hace la transcripción de TODOS los modelos primero (uno a uno, liberando) y luego compara, para
no tener Whisper-large + BGE-M3 a la vez en la GPU de 4 GB.

Uso:  python scripts/bakeoff_asr.py
"""
import difflib
import gc
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config, resolve_path  # noqa: E402

MODELS = ["large-v3-turbo", "large-v3"]
PAIRS = [   # (etiqueta, wav, diario_json)
    ("Congreso PL-109", "data/raw_audio/GXmB5P4uMEw.wav", "data/diarios_json/DSCD-15-PL-109.json"),
    ("Congreso PL-106", "data/raw_audio/hmN5E2ZSe2Q.wav", "data/diarios_json/DSCD-15-PL-106.json"),
    ("Madrid 25-03", "data/raw_audio/madrid2432.wav", "data/diarios_json/DS_2432_PO_25_03_25.json"),
]
VRAM = {"large-v3-turbo": "~1,5 GB", "large-v3": "~3 GB"}


def _norm(s):
    return " ".join(unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().split())


def _transcribe(wav, model_name, cfg):
    from src.transcribe import transcribe
    cfg.asr.model = model_name
    cfg.asr.language = "auto"                       # multilingüe (Congreso castellano, Madrid castellano)
    t0 = time.time()
    tr = transcribe(wav, cfg, resolve_path("data/processed/_bakeoff"))
    return tr, time.time() - t0


def _scores(segs_text, off_text, emb):
    chunks, cur = [], ""
    for t in segs_text:
        cur = (cur + " " + t).strip()
        if len(cur) >= 400:
            chunks.append(cur); cur = ""
    if cur:
        chunks.append(cur)
    off = [t for t in off_text if len(t) > 40]
    E = emb.encode(chunks, normalize_embeddings=True)
    O = emb.encode(off, normalize_embeddings=True)
    parecido = float((E @ O.T).max(axis=1).mean())
    ours = _norm(" ".join(segs_text)); offall = _norm(" ".join(off))
    sm = difflib.SequenceMatcher(None, ours.split(), offall.split(), autojunk=False)
    literal = sum(b.size for b in sm.get_matching_blocks()) / max(len(ours.split()), 1)
    return parecido, literal


def main():
    import json
    cfg = load_config()
    pairs = [(lbl, w, d) for (lbl, w, d) in PAIRS if Path(w).exists() and Path(d).exists()]
    if not pairs:
        sys.exit("No hay pares (wav + diario) disponibles todavía.")
    print(f"Bake-off sobre {len(pairs)} pleno(s): {[p[0] for p in pairs]}\n")

    # --- FASE A: transcribir todo (modelo a modelo, liberando) ---
    res = {}     # (model, lbl) -> (texts, dur_audio, secs)
    for m in MODELS:
        print(f"=== modelo {m} ===", flush=True)
        for lbl, wav, _ in pairs:
            tr, secs = _transcribe(wav, m, cfg)
            texts = [s["text"].strip() for s in tr["segments"] if s.get("text", "").strip()]
            res[(m, lbl)] = (texts, tr.get("duration", 0.0), secs)
            print(f"  {lbl}: {len(texts)} seg · {secs:.0f}s (audio {tr.get('duration',0):.0f}s)", flush=True)
        gc.collect()

    # --- FASE B: comparar (ahora sí cargamos el embedder) ---
    from src.index import get_embedder
    emb = get_embedder(cfg)
    offcache = {lbl: [it["text"].strip() for it in json.loads(Path(d).read_text(encoding="utf-8"))["interventions"]]
                for lbl, _, d in pairs}

    rows = {}
    for m in MODELS:
        ps, ls, xrt = [], [], []
        for lbl, _, _ in pairs:
            texts, dur, secs = res[(m, lbl)]
            par, lit = _scores(texts, offcache[lbl], emb)
            ps.append(par); ls.append(lit); xrt.append(dur / secs if secs else 0)
            print(f"  [{m}] {lbl}: parecido {par*100:.1f}% · literal {lit*100:.1f}% · {dur/secs:.1f}xRT")
        rows[m] = (np.mean(ps), np.mean(ls), np.mean(xrt))

    print("\n================ RESULTADO BAKE-OFF ================")
    print(f"{'modelo':18} {'parecido':>9} {'literal':>8} {'velocidad':>10} {'VRAM':>8}")
    for m in MODELS:
        p, l, x = rows[m]
        print(f"{m:18} {p*100:8.1f}% {l*100:7.1f}% {x:8.1f}xRT {VRAM.get(m,''):>8}")
    print("(parecido = similitud semántica al Diario; literal = palabras idénticas; xRT = veces más rápido que el audio)")


if __name__ == "__main__":
    main()
