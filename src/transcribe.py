"""Bloque A (2/2): transcribe un audio con faster-whisper.

Genera segmentos con timestamps y los guarda como JSON (estructurado, para los
siguientes bloques) y SRT (para revisar a ojo). Ajustes pensados para audio
parlamentario en castellano y para una RTX 3050 de 4 GB (int8).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _add_cuda_dll_dirs() -> None:
    """Windows: añade al path de búsqueda de DLLs las librerías CUDA (cuBLAS/cuDNN)
    instaladas por los wheels `nvidia-*-cu12`, para que CTranslate2 las encuentre
    y evitar el típico error 'Could not locate cudnn'."""
    if os.name != "nt":
        return
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if not base.exists():
        return
    for bin_dir in base.glob("*/bin"):
        try:
            os.add_dll_directory(str(bin_dir))
        except OSError:
            pass


def _hms(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def _write_srt(segments: list[dict], path: Path) -> None:
    def ts(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int(round((t - int(t)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        lines += [str(i), f"{ts(seg['start'])} --> {ts(seg['end'])}", seg["text"], ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def transcribe(audio_path, cfg, out_dir) -> dict:
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel  # import tras preparar las DLLs

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    a = cfg.asr

    device, compute_type = a.device, a.compute_type
    try:
        model = WhisperModel(a.model, device=device, compute_type=compute_type)
    except Exception as e:  # p.ej. CUDA no disponible -> caemos a CPU
        print(f"[aviso] no se pudo iniciar en {device}/{compute_type} ({e}). Uso CPU/int8.")
        device, compute_type = "cpu", "int8"
        model = WhisperModel(a.model, device=device, compute_type=compute_type)

    # language="auto" (o multilingual:true) -> detección de idioma POR FRAGMENTO. Imprescindible en
    # plenos bilingües (valencià/castellà, gallego, euskera): forzar "es" destroza lo que no es
    # castellano ("L'esmena"->"La semana"). Si no, se fuerza el idioma de config.
    lang = getattr(a, "language", "es")
    multi = bool(getattr(a, "multilingual", False)) or lang in ("auto", "", None)
    print(f"[asr] modelo={a.model} · device={device} · compute={compute_type} · "
          f"lang={'auto/multilingüe' if multi else lang}")
    segments, info = model.transcribe(
        str(audio_path),
        language=(None if multi else lang),
        multilingual=multi,
        vad_filter=getattr(a, "vad_filter", True),
        # trocear en pausas y NO formar bloques largos: evita el segmento de ~30 s que en una
        # discusión Whisper resolvía con 2 palabras (se perdía texto).
        vad_parameters=dict(max_speech_duration_s=getattr(a, "vad_max_speech_s", 20),
                            min_silence_duration_ms=getattr(a, "vad_min_silence_ms", 400)),
        condition_on_previous_text=getattr(a, "condition_on_previous_text", False),
        initial_prompt=getattr(a, "initial_prompt", None) or None,
        beam_size=5,
    )

    seg_list: list[dict] = []
    for s in segments:  # generador perezoso: se transcribe a medida que iteramos
        text = s.text.strip()
        seg_list.append({"id": s.id, "start": round(s.start, 3),
                         "end": round(s.end, 3), "text": text,
                         # confianza de Whisper -> fiabilidad del ASR SIN Diario (municipios)
                         "avg_logprob": round(float(s.avg_logprob), 3),
                         "no_speech_prob": round(float(s.no_speech_prob), 3)})
        print(f"  [{_hms(s.start)} -> {_hms(s.end)}] {text}")

    stem = Path(audio_path).stem
    transcript = {
        "audio": str(audio_path),
        "language": info.language,
        "duration": round(info.duration, 2),
        "model": a.model,
        "segments": seg_list,
    }
    json_path = out_dir / f"{stem}.json"
    srt_path = out_dir / f"{stem}.srt"
    json_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_srt(seg_list, srt_path)
    print(f"\n[ok] {len(seg_list)} segmentos · {json_path.name} + {srt_path.name}")
    return transcript
