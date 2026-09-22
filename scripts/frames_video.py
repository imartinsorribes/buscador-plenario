"""Extrae UNA captura del vídeo tutorial por CAPÍTULO (en su punto medio) para ilustrar el
manual generado — sin bajar el vídeo entero (mini-clips de ~4 s con yt-dlp --download-sections).

Idempotente: si el fotograma ya existe, no re-descarga. Salida: data/sedipualba/frames/capNN.png
Uso:  python scripts/frames_video.py
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.video_a_manual import TRANSCRIPT, VIDEO_ID, _chapters, _mmss, _windows  # noqa: E402
from src.config import load_config  # noqa: E402
from src.index import get_embedder  # noqa: E402

FRAMES = Path("data/sedipualba/frames")
PY = sys.executable


def main() -> None:
    segs = json.loads(Path(TRANSCRIPT).read_text(encoding="utf-8"))["segments"]
    wins = _windows(segs)
    cfg = load_config()
    cfg.embeddings.device = "cpu"      # solo calcula capítulos: no compite por la GPU (4 GB llenos)
    chaps = _chapters(wins, get_embedder(cfg))
    FRAMES.mkdir(parents=True, exist_ok=True)
    ok = fail = skip = 0
    for k, (a, b) in enumerate(chaps, 1):
        dest = FRAMES / f"cap{k:02d}.png"
        if dest.exists():
            skip += 1
            continue
        mid = int((wins[a]["start"] + wins[b - 1]["end"]) / 2)
        clip = FRAMES / f"_clip{k:02d}.mp4"
        r = subprocess.run(
            [PY, "-m", "yt_dlp", "--remote-components", "ejs:github", "-q",
             "-f", "bestvideo[height<=720]/best[height<=720]",
             "--download-sections", f"*{mid}-{mid + 4}",
             "-o", str(clip), f"https://www.youtube.com/watch?v={VIDEO_ID}"],
            capture_output=True, text=True)
        real = clip if clip.exists() else next(iter(FRAMES.glob(f"_clip{k:02d}.*")), None)
        if not real:
            print(f"  cap{k:02d} @{_mmss(mid)}: FALLO descarga ({(r.stderr or '')[-80:]})")
            fail += 1
            continue
        subprocess.run(["ffmpeg", "-y", "-ss", "2", "-i", str(real), "-frames:v", "1", str(dest)],
                       capture_output=True)
        real.unlink(missing_ok=True)
        if dest.exists():
            print(f"  cap{k:02d} @{_mmss(mid)} -> {dest.name}")
            ok += 1
        else:
            fail += 1
    print(f"\nfotogramas: {ok} nuevos · {skip} ya existían · {fail} fallos")


if __name__ == "__main__":
    main()
