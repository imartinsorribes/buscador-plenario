"""Valida la TRANSCRIPCIÓN de Whisper contra el Diario oficial (ground truth).

Mide RECALL DE CONTENIDO (no WER crudo: el Diario no es literal):
  1) recall de tokens de contenido (palabras significativas de Whisper que están en el Diario),
  2) recall de entidades/cifras (números y nombres/siglas en mayúscula),
  3) similitud semántica media (cada frase de Whisper vs su mejor match en el Diario).

Uso:  python scripts/validate_transcription.py <whisper.json> <diario.pdf>
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config  # noqa: E402
from src.diario import extract_text  # noqa: E402
from src.index import get_embedder  # noqa: E402
from src.verify import split_sentences  # noqa: E402

STOP = set("de la que el en y a los del se las por un para con no una su al es lo como mas o "
           "pero sus le ya este esta esto muy ha han hay".split())


def content_tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-záéíóúñ]+", text.lower())
    return {t for t in toks if len(t) > 3 and t not in STOP}


def entities(text: str) -> set[str]:
    nums = re.findall(r"\b\d+(?:[.,]\d+)?\b", text)
    caps = re.findall(r"\b[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ]{2,}\b", text)
    return set(nums) | {c.lower() for c in caps}


whisper_json, diario_pdf = sys.argv[1], sys.argv[2]
cfg = load_config()
wt = json.loads(Path(whisper_json).read_text(encoding="utf-8"))
whisper_text = " ".join(s["text"] for s in wt["segments"])
diario_text = extract_text(diario_pdf)

wt_toks, dt_toks = content_tokens(whisper_text), content_tokens(diario_text)
we, de = entities(whisper_text), entities(diario_text)
recall_tok = len(wt_toks & dt_toks) / max(len(wt_toks), 1)
recall_ent = len(we & de) / max(len(we), 1)

emb = get_embedder(cfg)
ws, ds = split_sentences(whisper_text), split_sentences(diario_text)
wv = np.array(emb.encode(ws, normalize_embeddings=True, batch_size=4))
dv = np.array(emb.encode(ds, normalize_embeddings=True, batch_size=8))
sem = float((wv @ dv.T).max(axis=1).mean())

print(f"Whisper: {len(wt_toks)} tokens de contenido · {len(we)} entidades/cifras · {len(ws)} frases")
print(f"Recall de contenido (tokens en el Diario): {recall_tok:.1%}")
print(f"Recall de entidades/cifras:                {recall_ent:.1%}")
print(f"Similitud semántica media (frase→Diario):  {sem:.3f}")
print(f"\nEntidades del Whisper que NO están en el Diario (posibles fallos ASR):")
print("  " + ", ".join(sorted(we - de)[:20]))
