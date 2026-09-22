"""Censura las CARAS en los fotogramas extraídos de los vídeos (recuadro negro sobre la ventana
de cámara del ponente) — capturas más profesionales y sin datos personales innecesarios (RGPD).

Detección con OpenCV (frontal + frontal-alt + perfil, sin posiciones a mano); cada cara se
expande para tapar la ventana de la webcam completa. Los originales se guardan en _orig/.

Uso:  python scripts/censurar_caras.py data/sedipualba/frames/TO3KMwAOkSE
"""
import shutil
import sys
from pathlib import Path

import cv2

_CASCADES = None


def _cascades():
    global _CASCADES
    if _CASCADES is None:
        base = cv2.data.haarcascades
        _CASCADES = [cv2.CascadeClassifier(base + n) for n in
                     ("haarcascade_frontalface_default.xml",
                      "haarcascade_frontalface_alt.xml",
                      "haarcascade_profileface.xml")]
    return _CASCADES


def _merge(boxes: list) -> list:
    """Une cajas que se solapan (varios detectores sobre la misma cara)."""
    out = []
    for b in boxes:
        x, y, w, h = b
        merged = False
        for i, (X, Y, W, H) in enumerate(out):
            if not (x > X + W or X > x + w or y > Y + H or Y > y + h):
                nx, ny = min(x, X), min(y, Y)
                out[i] = (nx, ny, max(x + w, X + W) - nx, max(y + h, Y + H) - ny)
                merged = True
                break
        if not merged:
            out.append(tuple(int(v) for v in b))
    return out


_YOLO = None


def _yolo_persons(img):
    """Personas por YOLO (CPU): caza al ponente aunque la cara esté de perfil o sea pequeña.
    Solo cajas pequeñas respecto a la imagen (ventana de webcam), para no tapar diapositivas."""
    global _YOLO
    try:
        if _YOLO is None:
            from ultralytics import YOLO
            _YOLO = YOLO("yolo11n.pt")
        H, W = img.shape[:2]
        res = _YOLO.predict(img, classes=[0], conf=0.35, device="cpu", verbose=False)[0]
        out = []
        for b in res.boxes.xyxy.cpu().numpy():
            x0, y0, x1, y1 = (int(v) for v in b)
            if (x1 - x0) * (y1 - y0) <= 0.25 * W * H:      # ventana de cámara, no media pantalla
                out.append((x0, y0, x1 - x0, y1 - y0))
        return out
    except Exception:
        return []


def censor_faces(path: str | Path) -> int:
    """Tapa las caras de una imagen con un recuadro negro (expandido a la ventana de cámara).
    Ensemble: cascadas de cara (frontal+perfil) ∪ personas YOLO. Modifica el fichero in-place."""
    p = Path(path)
    img = cv2.imread(str(p))
    if img is None:
        return 0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    boxes = []
    for casc in _cascades():
        for b in casc.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)):
            boxes.append(b)
    boxes += _yolo_persons(img)
    boxes = _merge(boxes)
    H, W = img.shape[:2]
    for x, y, w, h in boxes:
        # expandir a la ventana de la webcam: margen generoso alrededor de la cara
        x0 = max(0, int(x - 1.3 * w)); y0 = max(0, int(y - 0.8 * h))
        x1 = min(W, int(x + w + 1.3 * w)); y1 = min(H, int(y + h + 1.1 * h))
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 0), -1)
    if boxes:
        cv2.imwrite(str(p), img)
    return len(boxes)


def censor_dir(folder: str | Path) -> None:
    folder = Path(folder)
    backup = folder / "_orig"
    backup.mkdir(exist_ok=True)
    total = 0
    for png in sorted(folder.glob("*.png")):
        dst = backup / png.name
        if dst.exists():
            shutil.copy(dst, png)                 # re-censura SIEMPRE desde el original
        else:
            shutil.copy(png, dst)                 # respaldo del original (una vez)
        n = censor_faces(png)
        total += n
        print(f"  {png.name}: {n} zona(s) censurada(s)")
    print(f"total: {total} censuras en {folder}")


if __name__ == "__main__":
    censor_dir(sys.argv[1] if len(sys.argv) > 1 else "data/sedipualba/frames/TO3KMwAOkSE")
