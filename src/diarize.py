"""Bloque B — Diarización (quién habla) con pyannote, fusionada con la transcripción Whisper.

Requiere:
  - HF_TOKEN en .env (token de HuggingFace).
  - Aceptar las condiciones de  pyannote/speaker-diarization-3.1  y  pyannote/segmentation-3.0.

Asigna a cada segmento de Whisper el orador (SPEAKER_00, 01...) por mayor solape temporal.
El mapeo SPEAKER_xx -> nombre/partido real se hará luego (vía Diario o fórmulas de turno).

Uso:  python -m src.diarize data/transcripts/<id>.json data/raw_audio/<id>.wav
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_config


def _patch_speechbrain_lazy_imports() -> None:
    """Arregla un bug de speechbrain 1.x en Windows.

    speechbrain protege sus 'lazy modules' para que inspect no dispare imports
    reales, pero comprueba  filename.endswith('/inspect.py')  y en Windows la ruta
    usa '\\' -> el guard nunca salta. Entonces, cuando pytorch_lightning / torch
    llaman a inspect (que hace hasattr(modulo, '__file__')), se intenta importar
    speechbrain.integrations.k2_fsa -> import k2 (no instalable en Windows) ->
    ImportError que tumba la diarizacion.

    Solucion: que el acceso a 'dunders' de un LazyModule devuelva AttributeError
    (justo lo que inspect espera) sin disparar el import perezoso. El uso real
    (acceso a atributos no-dunder) sigue funcionando igual.
    """
    try:
        import speechbrain.utils.importutils as iu
    except Exception:
        return
    LM = getattr(iu, "LazyModule", None)
    if LM is None or getattr(LM, "_pleno_patched", False):
        return
    _orig_getattr = LM.__getattr__

    def _safe_getattr(self, attr):
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        return _orig_getattr(self, attr)

    LM.__getattr__ = _safe_getattr
    LM._pleno_patched = True


def diarize(audio_path, cfg=None) -> list[dict]:
    _patch_speechbrain_lazy_imports()  # debe ir ANTES de importar pyannote/lightning
    import torch
    from pyannote.audio import Pipeline

    cfg = cfg or load_config()
    token = os.environ.get(getattr(cfg.diarization, "hf_token_env", "HF_TOKEN"))
    if not token:
        raise RuntimeError(
            "Falta HF_TOKEN (.env) y/o aceptar las condiciones de "
            "pyannote/speaker-diarization-3.1 y pyannote/segmentation-3.0."
        )
    pipe = Pipeline.from_pretrained(cfg.diarization.model, use_auth_token=token)
    if pipe is None:
        raise RuntimeError(
            "pyannote devolvió None (403 gated): la cuenta del HF_TOKEN no ha ACEPTADO las "
            "condiciones de los modelos. Inicia sesión en HuggingFace con la MISMA cuenta del "
            "token y pulsa 'Agree and access repository' en:\n"
            "  - https://hf.co/pyannote/speaker-diarization-3.1\n"
            "  - https://hf.co/pyannote/segmentation-3.0\n"
            "La aprobación es automática (inmediata). Después reintenta."
        )
    if torch.cuda.is_available():
        pipe.to(torch.device("cuda"))
    dia = pipe(str(audio_path))
    return [{"start": float(t.start), "end": float(t.end), "speaker": s}
            for t, _, s in dia.itertracks(yield_label=True)]


def merge_speakers(segments: list[dict], turns: list[dict]) -> list[dict]:
    """A cada segmento le asigna el orador con el que más solapa en el tiempo y marca
    `overlap=True` si un SEGUNDO orador también está activo buena parte del segmento
    (cruce de intervenciones / 'discuten a la vez'). Ese cruce se excluye luego al
    construir las huellas de voz, para no contaminarlas."""
    for seg in segments:
        dur = max(seg["end"] - seg["start"], 1e-6)
        ov_by: dict[str, float] = {}
        for t in turns:
            ov = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if ov > 0:
                ov_by[t["speaker"]] = ov_by.get(t["speaker"], 0.0) + ov
        if not ov_by:
            continue
        ranked = sorted(ov_by.items(), key=lambda kv: -kv[1])
        seg["speaker"] = ranked[0][0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        seg["overlap"] = bool(second >= 0.6 and second >= 0.30 * dur)
    return segments


def _merge_similar_voices(segments, audio_path, thr=0.82) -> int:
    """Une los clusters que son la MISMA persona (la diarización a veces parte una voz en dos,
    sobre todo en discusiones). Compara la huella ECAPA de cada cluster y fusiona si el coseno
    supera `thr` (conservador: solo duplicados claros)."""
    import numpy as np

    from . import voiceid
    vps = voiceid.cluster_voiceprints(audio_path, segments)
    names = [k for k, v in vps.items() if v is not None]
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if float(np.dot(vps[names[i]], vps[names[j]])) >= thr:
                parent[find(names[i])] = find(names[j])
    remap = {n: find(n) for n in names}
    merged = len(names) - len(set(remap.values()))
    if merged:
        for s in segments:
            sp = s.get("speaker")
            if sp in remap:
                s["speaker"] = remap[sp]
    return merged


def _absorb_tiny_clusters(segments, audio_path, max_segs=2, thr=0.45, margin=0.12) -> int:
    """Absorbe clusters DIMINUTOS (≤max_segs segmentos) dentro del cluster grande con el que
    casa su voz. Son los clusters fantasma que nacen del CRUCE de voces (no llegan a formar
    huella, por eso `_merge_similar_voices` ni los mira). Embebe sus segmentos uno a uno y, si
    el mejor coseno supera `thr` con `margin` sobre el 2º, reasigna TODOS sus segmentos
    (también los inembebibles, que siguen al cluster). Arregla el 'Voz 4 que es Voz 3'."""
    import numpy as np

    from . import voiceid
    by_sp: dict[str, list] = {}
    for s in segments:
        by_sp.setdefault(s.get("speaker"), []).append(s)
    tiny = [sp for sp, ss in by_sp.items() if sp and len(ss) <= max_segs]
    big = [sp for sp in by_sp if sp and sp not in tiny]
    if not tiny or not big:
        return 0
    vps = voiceid.cluster_voiceprints(audio_path, [s for s in segments if s.get("speaker") in big])
    bigv = {k: np.asarray(v) for k, v in vps.items() if v is not None}
    if not bigv:
        return 0
    wav = voiceid._load_audio(audio_path)

    def cos(a, b):
        return float(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b)))

    absorbed = 0
    for sp in tiny:
        embs = [np.asarray(e) for s in by_sp[sp]
                if (e := voiceid._embed_spans(wav, [(s["start"], s["end"])])) is not None]
        if not embs:
            continue
        v = np.mean(embs, axis=0)
        ranked = sorted(((cos(v, bv), k) for k, bv in bigv.items()), reverse=True)
        if ranked[0][0] >= thr and (len(ranked) < 2 or ranked[0][0] - ranked[1][0] >= margin):
            for s in by_sp[sp]:
                s["speaker"] = ranked[0][1]
            absorbed += 1
    return absorbed


def diarize_transcript(transcript_path, audio_path, cfg=None, entidad: str | None = None) -> dict:
    cfg = cfg or load_config()
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    turns = diarize(audio_path, cfg)
    data["segments"] = merge_speakers(data["segments"], turns)
    try:
        merged = _merge_similar_voices(data["segments"], audio_path)
        merged += _absorb_tiny_clusters(data["segments"], audio_path)
    except Exception as e:                                  # noqa: BLE001
        merged = 0
        print(f"[diar] (fusión por voz omitida: {e})")
    # asignación SUPERVISADA: si el municipio tiene voces registradas, corrigen el clustering
    # (tramo limpio+largo que casa con una huella -> esa persona; lo dudoso se queda como está)
    if entidad:
        try:
            from . import voiceid
            n = voiceid.supervised_assign(str(audio_path), data["segments"], entidad)
            if n:
                print(f"[diar] {n} tramos asignados por huella registrada ({entidad})")
        except Exception as e:                              # noqa: BLE001
            print(f"[diar] (asignación por huella omitida: {e})")
    Path(transcript_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n_spk = len({s.get("speaker") for s in data["segments"] if s.get("speaker")})
    print(f"[diar] {len(turns)} turnos · {n_spk} oradores (fusionadas {merged} voces) · {Path(transcript_path).name}")
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Bloque B — diarización (pyannote) + fusión con Whisper.")
    ap.add_argument("transcript", help="JSON de transcripción (data/transcripts/<id>.json)")
    ap.add_argument("audio", help="audio del pleno (wav/m4a 16 kHz mono)")
    ap.add_argument("--entidad", default=None,
                    help="slug del municipio: activa la asignación supervisada por huellas registradas")
    args = ap.parse_args()
    diarize_transcript(args.transcript, args.audio, entidad=args.entidad)


if __name__ == "__main__":
    main()
