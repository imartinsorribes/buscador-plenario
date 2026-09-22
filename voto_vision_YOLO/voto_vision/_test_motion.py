# -*- coding: utf-8 -*-
"""Experimento: senal de 'brazo por encima de la linea de cabezas' (camara fija).
Compara un fotograma de votacion con una base de manos-bajadas (mediana)."""
import cv2, numpy as np, sys
import os
_B = os.path.dirname(os.path.abspath(__file__))
VID = os.environ.get("PLENO_VIDEO", os.path.join(_B, "grabacion.mp4"))
OUT = os.path.join(_B, "outputs")
CROP_Y0, CROP_H = 50, 70          # banda de cabezas/brazos
BASE_T = (50, 51, 52, 53, 54, 55, 56, 57, 58)   # manos abajo (perfil V1)
VOTE_T = float(sys.argv[1]) if len(sys.argv) > 1 else 62.6

def grab(t):
    cap = cv2.VideoCapture(VID); cap.set(cv2.CAP_PROP_POS_MSEC, t*1000); ok, fr = cap.read(); cap.release()
    return fr[CROP_Y0:CROP_Y0+CROP_H, :].astype(np.float32)

base = np.median(np.stack([grab(t) for t in BASE_T]), axis=0)
vote = grab(VOTE_T)
diff = np.abs(vote - base).mean(axis=2)               # diferencia de gris
mask = (diff > 22).astype(np.uint8)                   # foreground nuevo
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2,2), np.uint8))
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))

# columnas con foreground en la franja ALTA (brazos por encima de cabezas)
col = mask.sum(axis=0)
up_strip = mask[0:32, :].sum(axis=0)                  # parte superior de la banda
# visual: amplio x4 y pinto el mask en rojo sobre el frame
visf = cv2.resize((vote).astype(np.uint8), None, fx=4, fy=4)
vism = cv2.resize((mask*255), None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
vism = cv2.cvtColor(vism, cv2.COLOR_GRAY2BGR); vism[:,:,0]=0; vism[:,:,1]=0
out = cv2.addWeighted(visf, 0.7, vism, 0.6, 0)
cv2.imwrite(f"{OUT}/motion_{int(VOTE_T)}.jpg", out)
print(f"t={VOTE_T}: pixeles foreground total={int(mask.sum())}, en franja alta={int(up_strip.sum())}")
print("guardado motion_*.jpg (rojo = lo que aparece nuevo respecto a manos-abajo)")
