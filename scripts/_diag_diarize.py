"""Diagnóstico: re-diariza forzando un mínimo de voces a pyannote (para ver si PUEDE separar
más). Uso: python scripts/_diag_diarize.py <audio> <transcript_ASR> <min_speakers> <salida>"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config
from src.diarize import _patch_speechbrain_lazy_imports, merge_speakers

# carga .env (HF_TOKEN) por si el entorno no lo trae
env = Path(__file__).resolve().parent.parent / ".env"
if env.exists():
    for ln in env.read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

audio, tr_path, minsp, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
_patch_speechbrain_lazy_imports()
import torch
from pyannote.audio import Pipeline

cfg = load_config()
token = os.environ.get(getattr(cfg.diarization, "hf_token_env", "HF_TOKEN"))
pipe = Pipeline.from_pretrained(cfg.diarization.model, use_auth_token=token)
if torch.cuda.is_available():
    pipe.to(torch.device("cuda"))
dia = pipe(audio, min_speakers=minsp)
turns = [{"start": float(t.start), "end": float(t.end), "speaker": s}
         for t, _, s in dia.itertracks(yield_label=True)]
data = json.loads(Path(tr_path).read_text(encoding="utf-8"))
data["segments"] = merge_speakers(data["segments"], turns)
Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
n = len({s.get("speaker") for s in data["segments"] if s.get("speaker")})
print(f"min_speakers={minsp} -> {n} voces detectadas")
