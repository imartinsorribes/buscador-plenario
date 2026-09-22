"""Experimento: ¿mejora la transcripción un GLOSARIO local frente al prompt del Congreso?
Transcribe el mismo trozo de Chiva con dos initial_prompt distintos y compara.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.transcribe import _add_cuda_dll_dirs

_add_cuda_dll_dirs()
from faster_whisper import WhisperModel  # noqa: E402

AUDIO = "data/ref/chiva_5min.wav"

P_CONGRESO = ("Sesión plenaria del Congreso de los Diputados. Intervienen la Presidencia, "
              "ministros del Gobierno y diputados de los grupos parlamentarios Socialista, "
              "Popular, Vox, Sumar, Republicano, Junts, EH Bildu, Vasco (PNV) y Mixto. "
              "Real decreto-ley, convalidación, escudo social, revalorización de las pensiones, "
              "desahucios, vulnerabilidad.")

P_CHIVA = ("Pleno del Ayuntamiento de Chiva (Valencia). Intervienen la Alcaldía y los concejales "
           "Fort, Castillo, Sancho, Olmo, De Lamo, Celda, Casanova y Lemos, de los grupos "
           "Partido Popular, Vox y Vinchi. Se tratan: ratificación de la urgencia de la sesión, "
           "ayudas FEDER, PAI, mancomunidad, senda financiera, modificación de presupuesto, "
           "expediente, convocatoria.")

model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8")


def run(prompt):
    segs, _ = model.transcribe(
        AUDIO, language="es", vad_filter=True,
        vad_parameters=dict(max_speech_duration_s=20, min_silence_duration_ms=400),
        condition_on_previous_text=False, initial_prompt=prompt or None, beam_size=5)
    return " ".join(s.text.strip() for s in segs)


print(">> transcribiendo con prompt CONGRESO..."); a = run(P_CONGRESO)
print(">> transcribiendo con glosario CHIVA...");  b = run(P_CHIVA)

print("\n=================== PROMPT CONGRESO ===================\n" + a)
print("\n=================== GLOSARIO CHIVA ====================\n" + b)

print("\n--- recuento de términos clave (congreso | chiva) ---")
for t in ["mancomunidad", "FEDER", "PAI", "senda financiera", "Chiva", "expediente",
          "urgencia", "Fort", "Celda", "Casanova"]:
    print(f"  {t:18s}  {a.lower().count(t.lower())}  |  {b.lower().count(t.lower())}")
