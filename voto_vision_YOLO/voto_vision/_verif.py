"""Verificador visual: dibuja decision de 'mano levantada' por persona y la altura relativa."""
import cv2, numpy as np, sys
from ultralytics import YOLO
import os
_B = os.path.dirname(os.path.abspath(__file__))
VID = os.environ.get("PLENO_VIDEO", os.path.join(_B, "grabacion.mp4"))
OUT = os.path.join(_B, "outputs")
CROP_Y0, CROP_H, UP = 55, 110, 4
REL_THR = float(sys.argv[2]) if len(sys.argv) > 2 else 0.70
m = YOLO("yolo11x-pose.pt")

def hand_score(p, c):
    """Devuelve altura relativa max de las manos: 0=hombro, 1=cabeza, >1 sobre cabeza."""
    head = [p[i,1] for i in (0,1,2,3,4) if c[i] > 0.20]
    sh   = [p[i,1] for i in (5,6)       if c[i] > 0.20]
    if not head or not sh: return None
    ht, shy = min(head), np.mean(sh)
    if shy - ht < 8*UP*0.0 + 4: return None  # cabeza-hombro degenerado
    best = -9
    for ei, wi in ((7,9),(8,10)):
        hy = None
        if c[wi] > 0.25: hy = p[wi,1]
        elif c[ei] > 0.50: hy = p[ei,1]          # fallback codo si muñeca floja
        if hy is None: continue
        rel = (shy - hy) / (shy - ht)
        best = max(best, rel)
    return best

t = float(sys.argv[1])
cap = cv2.VideoCapture(VID); cap.set(cv2.CAP_PROP_POS_MSEC, t*1000); _, fr = cap.read(); cap.release()
band = fr[CROP_Y0:CROP_Y0+CROP_H, :]
up = cv2.resize(band, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
r = m(up, conf=0.20, imgsz=2560, verbose=False)[0]
vis = up.copy()
kp = r.keypoints.xy.cpu().numpy(); cf = r.keypoints.conf.cpu().numpy()
boxes = r.boxes.xyxy.cpu().numpy()
nvote = 0
for p, c, b in zip(kp, cf, boxes):
    s = hand_score(p, c)
    raised = (s is not None and s >= REL_THR)
    if raised: nvote += 1
    col = (0,0,255) if raised else (180,180,180)
    cv2.rectangle(vis, (int(b[0]),int(b[1])), (int(b[2]),int(b[3])), col, 2)
    lbl = f"{s:.2f}" if s is not None else "NA"
    cv2.putText(vis, lbl, (int(b[0]), int(b[1])-4), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
print(f"t={t} REL_THR={REL_THR} -> VOTOS(mano arriba)={nvote}")
cv2.imwrite(f"{OUT}/verif_{int(t)}_{REL_THR}.jpg", vis)
