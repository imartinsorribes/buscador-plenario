"""Screencast CORTO (solo pantalla): el flujo de uso de la app, sin portadas ni slides.
Reusa los frames de make_demo_pro (UI recreada + acta real + fotograma real del vídeo).

Uso:  python scripts/make_demo_screencast.py   ->  data/processed/demo_pantalla.mp4
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.make_demo_pro import (acta_body_frame, acta_overview_frame, form_frame,  # noqa: E402
                                    prep_assets, progress_frame, visor_frame, FR)

OUT = "data/processed/demo_pantalla.mp4"


def main():
    vsegs = prep_assets()
    frames = [
        (form_frame(False, False), 1.4),
        (form_frame(True, True), 2.6),
        (progress_frame(1, pct=35, elapsed="0:12", msg="Descargando el vídeo…"), 1.6),
        (progress_frame(2, eta=4, elapsed="1:20", rem="4 min", msg="Transcribiendo (voz a texto)…"), 2.2),
        (progress_frame(3, elapsed="3:40", rem="2 min", msg="Separando las voces…"), 1.6),
        (progress_frame(5, done=True, elapsed="5:30", msg="Acta generada.", link=True), 2.4),
        (acta_overview_frame(), 4.4),
        (acta_body_frame(), 4.0),
        (visor_frame(vsegs, 1), 4.6),
    ]
    total = 0.0
    with open(os.path.join(FR, "list.txt"), "w", encoding="utf-8") as fh:
        for i, (img, dur) in enumerate(frames):
            img.save(os.path.join(FR, f"s{i:02d}.png"))
            fh.write(f"file 's{i:02d}.png'\nduration {dur}\n")
            total += dur
        fh.write(f"file 's{len(frames)-1:02d}.png'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-vf", f"fps=25,format=yuv420p,fade=t=in:st=0:d=0.3,fade=t=out:st={total-0.5:.2f}:d=0.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.abspath(OUT)],
                   cwd=FR, check=True, capture_output=True)
    print(f"OK  {OUT}  ·  {total:.1f}s")


if __name__ == "__main__":
    main()
