# -*- coding: utf-8 -*-
"""Experimento: pose TOP-DOWN (recorto cada persona y corro pose en su crop)."""
import cv2, numpy as np, sys
from ultralytics import YOLO
VID = r"C:\Users\david\OneDrive\Escritorio\RETO2\reto_video\grabacion.mp4"
OUT = r"C:\Users\david\OneDrive\Escritorio\RETO2\voto_vision\outputs"
CROP_Y0, CROP_H, UP = 55, 110, 4
m = YOLO("yolo11x-pose.pt")
T = float(sys.argv[1]) if len(sys.argv) > 1 else 62.6
THR = 0.80

def rel_height(p, c):
    head = [p[i,1] for i in (0,1,2,3,4) if c[i] > 0.20]
    sh   = [p[i,1] for i in (5,6)       if c[i] > 0.20]
    if not head or not sh: return None
    yh, ys = min(head), float(np.mean(sh))
    if ys - yh < 4: return None
    best = None
    for ei, wi in ((7,9),(8,10)):
        y = p[wi,1] if c[wi] > 0.25 else (p[ei,1] if c[ei] > 0.50 else None)
        if y is None: continue
        r = (ys - y)/(ys - yh)
        best = r if best is None else max(best, r)
    return best

cap = cv2.VideoCapture(VID); cap.set(cv2.CAP_PROP_POS_MSEC, T*1000); _, fr = cap.read(); cap.release()
H, W = fr.shape[:2]

# --- Paso 1: deteccion global para localizar a las personas (cajas) ---
band = fr[CROP_Y0:CROP_Y0+CROP_H, :]
up = cv2.resize(band, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
r0 = m(up, conf=0.20, imgsz=2560, verbose=False)[0]
boxes_up = r0.boxes.xyxy.cpu().numpy()

# --- Paso 2: por cada persona, recorto en RESOLUCION NATIVA con margen y reproceso ---
vis = up.copy()
n_global = 0
if r0.keypoints is not None and r0.keypoints.conf is not None:
    for p,c in zip(r0.keypoints.xy.cpu().numpy(), r0.keypoints.conf.cpu().numpy()):
        rr = rel_height(p,c); n_global += (rr is not None and rr >= THR)

n_td = 0; results = []
for b in boxes_up:
    # caja en nativo (deshago x4 y el offset de la banda) con margen generoso arriba
    x0 = max(0, int(b[0]/UP) - 6);  x1 = min(W, int(b[2]/UP) + 6)
    y0 = max(0, CROP_Y0 + int(b[1]/UP) - 18)        # margen alto: el brazo sube
    y1 = min(H, CROP_Y0 + int(b[3]/UP) + 4)
    crop = fr[y0:y1, x0:x1]
    if crop.size == 0: continue
    # amplio el crop de una sola persona a ~360 px de alto
    s = 360.0 / crop.shape[0]
    cup = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    rc = m(cup, conf=0.20, imgsz=640, verbose=False)[0]
    if rc.keypoints is None or rc.keypoints.conf is None or len(rc.keypoints)==0:
        results.append(None); continue
    # me quedo con la persona mas centrada/grande del crop
    areas = (rc.boxes.xyxy.cpu().numpy()[:,2]-rc.boxes.xyxy.cpu().numpy()[:,0])
    k = int(np.argmax(areas))
    rr = rel_height(rc.keypoints.xy.cpu().numpy()[k], rc.keypoints.conf.cpu().numpy()[k])
    results.append(rr)
    raised = rr is not None and rr >= THR
    n_td += raised
    col = (0,0,255) if raised else (160,160,160)
    cv2.rectangle(vis, (int(b[0]),int(b[1])),(int(b[2]),int(b[3])), col, 2)
    cv2.putText(vis, f"{rr:.2f}" if rr is not None else "NA", (int(b[0]),int(b[1])-4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)

print(f"t={T}  manos>=({THR}):  GLOBAL(1 pasada)={n_global}   TOP-DOWN(crop x persona)={n_td}")
print("  rel por persona (top-down):", [round(x,2) if x is not None else None for x in results])
cv2.imwrite(f"{OUT}/topdown_{int(T)}.jpg", vis)
