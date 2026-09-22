"""¿Arregla 'hotwords' los términos locales que el initial_prompt no fuerza?
Transcribe el trozo de Chiva con hotwords y mira si 'bancomunidad' -> 'mancomunidad'.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.transcribe import _add_cuda_dll_dirs

_add_cuda_dll_dirs()
from faster_whisper import WhisperModel  # noqa: E402

AUDIO = "data/ref/chiva_5min.wav"
HOT = "mancomunidad, FEDER, PAI, senda financiera, Chiva, ratificación de la urgencia, expediente"

model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8")


def run(**kw):
    segs, _ = model.transcribe(
        AUDIO, language="es", vad_filter=True,
        vad_parameters=dict(max_speech_duration_s=20, min_silence_duration_ms=400),
        condition_on_previous_text=False, beam_size=5, **kw)
    return " ".join(s.text.strip() for s in segs)


try:
    txt = run(hotwords=HOT)
    print(">> hotwords OK")
except TypeError as e:
    print(f">> esta versión de faster-whisper NO soporta hotwords: {e}")
    sys.exit(0)

print("mancomunidad:", txt.lower().count("mancomunidad"),
      "| bancomunidad:", txt.lower().count("bancomunidad"))
# muestra el contexto del término problemático
i = txt.lower().find("comunidad")
while i != -1:
    print("   ...", txt[max(0, i - 30):i + 15], "...")
    i = txt.lower().find("comunidad", i + 1)
