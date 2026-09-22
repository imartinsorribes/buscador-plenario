"""Perfil temporal: nº de brazos por encima de la cabeza, frame a frame, en una ventana."""
import cv2, numpy as np, sys
from ultralytics import YOLO

import os
VID = os.environ.get("PLENO_VIDEO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "grabacion.mp4"))
CROP_Y0, CROP_H, UP = 55, 110, 4
model = YOLO("yolo11x-pose.pt")

def frames(t0, t1, fps):
    cap = cv2.VideoCapture(VID)
    t = t0
    while t <= t1:
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ok, fr = cap.read()
        if ok: yield round(t,2), fr
        t += 1.0/fps
    cap.release()

def raised_count(fr):
    band = fr[CROP_Y0:CROP_Y0+CROP_H, :]
    up = cv2.resize(band, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
    r = model(up, conf=0.20, imgsz=2560, verbose=False)[0]
    if r.keypoints is None or r.keypoints.conf is None: return 0
    kp = r.keypoints.xy.cpu().numpy(); cf = r.keypoints.conf.cpu().numpy()
    n = 0
    for p, c in zip(kp, cf):
        # cabeza: y mas alta entre nariz/ojos/orejas con confianza
        head = [p[i,1] for i in (0,1,2,3,4) if c[i] > 0.20]
        if not head: continue
        head_top = min(head)
        up_arm = False
        for wi, ei in ((9,7),(10,8)):
            if c[wi] > 0.15 and p[wi,1] < head_top - 12: up_arm = True
            elif c[ei] > 0.15 and c[wi] > 0.10 and p[ei,1] < head_top: up_arm = True  # codo sobre cabeza
        if up_arm: n += 1
    return n

t0, t1, fps = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]) if len(sys.argv)>3 else 3
print(f"ventana [{t0},{t1}] @ {fps}fps")
for t, fr in frames(t0, t1, fps):
    print(f"  t={t:7.2f}  manos_arriba={raised_count(fr)}")
