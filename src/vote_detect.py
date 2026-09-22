"""Detección de votaciones por VISIÓN sobre NUESTRO vídeo, disparada por la transcripción.

Reúsa el detector de manos levantadas del compañero (voto_vision_YOLO/voto_vision) y le pasa:
  - nuestro vídeo del pleno,
  - las ventanas de cada votación que saca `votes_vision.vote_windows` de la transcripción.
Guarda `data/votes/<video_id>.json` (recuento por votación) + fotogramas anotados, que el acta
coloca luego en su punto del orden del día.

Uso:  python -m src.vote_detect <video_id>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import resolve_path

_CW = Path(__file__).resolve().parent.parent / "voto_vision_YOLO" / "voto_vision"


def detect_votes(video_path: str, audio_path: str, segments: list[dict], video_id: str,
                 out_dir: str = "data/votes") -> list[dict]:
    from .votes_vision import vote_windows
    vw = vote_windows(audio_path, segments)
    if not vw:
        print("[votos] no se detectaron votaciones en la transcripción")
        return []

    sys.path.insert(0, str(_CW))
    import detectar_votaciones as dv      # carga el modelo YOLO-pose (se descarga la 1ª vez)

    od = resolve_path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    frames_dir = od / video_id
    frames_dir.mkdir(parents=True, exist_ok=True)
    dv.VID = os.path.abspath(video_path)
    dv.OUTDIR = str(frames_dir)
    dv.VOTACIONES = [
        {"id": f"V{k}", "punto": f"Votación {k}",
         "fases": {ph: (float(a), float(b)) for ph, (a, b) in v["fases"].items()}}
        for k, v in enumerate(vw, 1)
    ]
    res = [dv.procesar_votacion(v) for v in dv.VOTACIONES]
    for r, v in zip(res, vw):
        r["t"] = v["start"]                 # instante de la votación -> para situarla en su punto
    out_json = od / f"{video_id}.json"
    out_json.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[votos] {len(res)} votación(es) -> {out_json}")
    return res


def main() -> None:
    vid = sys.argv[1]
    tr = resolve_path(f"data/transcripts/{vid}.json")
    seg = json.loads(tr.read_text(encoding="utf-8"))["segments"]
    video = resolve_path(f"data/raw_video/{vid}.mp4")
    audio = resolve_path(f"data/raw_audio/{vid}.wav")
    res = detect_votes(str(video), str(audio), seg, vid)
    for r in res:
        c = r["recuento"]
        print(f"  {r['punto']} (t={r.get('t')}s): a favor {c['a_favor']} · "
              f"en contra {c['en_contra']} · abstención {c['abstencion']}")


if __name__ == "__main__":
    main()
