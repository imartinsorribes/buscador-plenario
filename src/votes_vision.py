"""Puente entre la transcripción y la detección de votaciones por VISIÓN (módulo del compañero).

Para cada votación, saca las ventanas temporales PRECISAS de cada fase (¿votos a favor? ¿en
contra? ¿abstenciones?) usando timestamps POR PALABRA de Whisper sobre el tramo de la votación
(las pausas mientras la gente levanta la mano no salen en el texto, así que la interpolación por
caracteres no vale: hace falta el tiempo real de cada palabra).

Esas ventanas alimentan al detector de manos levantadas (YOLO-pose) y el recuento se coloca
luego en su punto del orden del día en el acta.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _rough_regions(segments: list[dict]) -> list[tuple[float, float]]:
    """Segmentos que contienen una llamada a votación ('a favor' y 'en contra')."""
    out = []
    for s in sorted(segments, key=lambda x: x.get("start", 0.0)):
        low = _norm(s.get("text", ""))
        if "a favor" in low and "en contra" in low:
            out.append((s.get("start", 0.0), s.get("end", 0.0)))
    return out


def vote_windows(audio_path: str, segments: list[dict], model=None) -> list[dict]:
    """Devuelve, por votación, las fases con tiempos precisos:
        {"start": t, "fases": {"a_favor": (t0,t1), "en_contra": (t0,t1), "abstencion": (t0,t1)}}
    Re-transcribe SOLO el tramo de cada votación con timestamps por palabra (rápido)."""
    regions = _rough_regions(segments)
    if not regions:
        return []
    if model is None:
        from .transcribe import _add_cuda_dll_dirs
        _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel
        model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8")

    out: list[dict] = []
    for (s, e) in regions:
        s0 = max(0.0, s - 1.0)
        clip = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        subprocess.run(["ffmpeg", "-y", "-ss", str(s0), "-to", str(e + 2.0), "-i", audio_path,
                        "-ar", "16000", "-ac", "1", clip], capture_output=True)
        words = []
        try:
            segs, _ = model.transcribe(clip, language="es", word_timestamps=True, vad_filter=False)
            for sg in segs:
                for w in (sg.words or []):
                    words.append((_norm(w.word), s0 + w.start))
        finally:
            try:
                os.unlink(clip)
            except OSError:
                pass

        def _find(key, after=-1.0):
            return next((ws for wd, ws in words if key in wd and ws >= after), None)

        tf = _find("favor")
        tc = _find("contra", tf) if tf is not None else None
        if tf is None or tc is None or tc <= tf:
            continue
        dt = tc - tf                                     # duración típica de una fase
        tb = _find("absten", tc)
        if tb is None or tb <= tc:                       # sin 'abstenciones' clara: estima por simetría
            tb = tc + dt
        tap = _find("aprob", tb)                          # 'se aprueba' marca el fin (si va después)
        end_ab = tap if (tap is not None and tap > tb) else (tb + max(1.5, dt))
        out.append({"start": round(tf, 1),
                    "fases": {"a_favor": (round(tf, 1), round(tc, 1)),
                              "en_contra": (round(tc, 1), round(tb, 1)),
                              "abstencion": (round(tb, 1), round(end_ab, 1))}})
    return out
