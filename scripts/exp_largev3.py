"""¿El modelo grande (large-v3, sin turbo) acierta los términos donde el turbo falla?
Test de una sola pasada sobre el trozo de Chiva."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.transcribe import _add_cuda_dll_dirs

_add_cuda_dll_dirs()
from faster_whisper import WhisperModel  # noqa: E402

AUDIO = "data/ref/chiva_5min.wav"
model = WhisperModel("large-v3", device="cuda", compute_type="int8")
segs, _ = model.transcribe(
    AUDIO, language="es", vad_filter=True,
    vad_parameters=dict(max_speech_duration_s=20, min_silence_duration_ms=400),
    condition_on_previous_text=False, beam_size=5)
txt = " ".join(s.text.strip() for s in segs)

print("mancomunidad:", txt.lower().count("mancomunidad"),
      "| bancomunidad:", txt.lower().count("bancomunidad"),
      "| 'humana comunidad':", txt.lower().count("humana comunidad"))
i = txt.lower().find("comunidad")
while i != -1:
    print("   ...", txt[max(0, i - 30):i + 12], "...")
    i = txt.lower().find("comunidad", i + 1)
print("\n--- primeras 600 chars ---\n", txt[:600])
