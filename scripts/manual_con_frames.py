"""Inserta los fotogramas del vídeo (uno por capítulo) en el manual generado y rehace el PDF.

Idempotente: parte siempre del md original y coloca cada data/sedipualba/frames/capNN.png bajo
el título de su sección NN (mismo orden determinista de capítulos que video_a_manual).

Uso:  python scripts/manual_con_frames.py
"""
import re
import subprocess
import sys
from pathlib import Path

MD = Path("docs/manual_secoin_generado.md")
FRAMES = Path("data/sedipualba/frames")
PY = sys.executable


def main() -> None:
    text = MD.read_text(encoding="utf-8")
    text = re.sub(r"\n!\[[^\]]*\]\([^)]*\)\n", "\n", text)      # quita inserciones previas
    parts = text.split("\n## ")
    out = [parts[0]]
    for k, sec in enumerate(parts[1:], 1):
        frame = FRAMES / f"cap{k:02d}.png"
        if frame.exists():
            lines = sec.split("\n")
            lines.insert(1, f"\n![Captura del vídeo, capítulo {k}]({frame.as_posix()})")
            sec = "\n".join(lines)
        out.append(sec)
    MD.write_text("\n## ".join(out), encoding="utf-8")
    n = len(list(FRAMES.glob("cap*.png")))
    print(f"{n} fotogramas insertados en {MD}")
    subprocess.run([PY, "scripts/md_to_pdf.py", "docs/manual_secoin_generado.pdf", str(MD)], check=True)


if __name__ == "__main__":
    main()
