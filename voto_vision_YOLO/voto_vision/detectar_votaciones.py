# -*- coding: utf-8 -*-
"""
============================================================================
 DETECCION DE VOTACIONES A MANO ALZADA EN PLENOS  ·  Ayuntamiento de Chiva
============================================================================
Dado un video del pleno y los instantes (de la transcripcion/acta) en que se
dice "votos a favor / en contra / abstenciones", cuenta cuantas manos se
levantan en cada fase.

IDEA CLAVE
----------
1) La camara es FIJA  ->  los asientos son fijos: detectamos personas con
   estimacion de POSE (YOLO11-pose) y las agrupamos en "asientos" estables.
2) Para distinguir un VOTO de "apoyarse la cabeza con la mano" no miramos si
   hay una mano arriba, sino la ALTURA RELATIVA de la mano respecto al propio
   cuerpo:   rel = (y_hombro - y_mano) / (y_hombro - y_cabeza)
       rel ~ 0  -> mano a la altura del hombro (brazo bajado)
       rel ~ 1  -> mano a la altura de la cabeza
       rel > 1  -> mano POR ENCIMA de la cabeza  (voto claro)
   Quien se apoya la cara tiene la muneca por DEBAJO del hombro/oreja
   (rel < umbral) y queda excluido automaticamente.  Asi nos da igual que uno
   estire mas el brazo que otro: normalizamos por su propia anatomia.
3) Un voto se mantiene varios segundos: AGREGAMOS EN EL TIEMPO dentro de cada
   fase (un fallo puntual de un fotograma se recupera con los vecinos).

SALIDAS  (carpeta outputs/)
   - resultado_votaciones.json    recuento + decision por asiento
   - <votacion>_<fase>.jpg        fotograma anotado de cada fase
   - <votacion>_perfil.png        perfil temporal de manos levantadas
============================================================================
"""
import os, json, cv2, numpy as np
from collections import defaultdict
from ultralytics import YOLO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------- CONFIG ------------------------------------
# Rutas relativas a este fichero (autocontenido). Se puede sobreescribir el
# video con la variable de entorno PLENO_VIDEO.
import os as _os
_BASE   = _os.path.dirname(_os.path.abspath(__file__))
VID     = _os.environ.get("PLENO_VIDEO", _os.path.join(_BASE, "grabacion.mp4"))
OUTDIR  = _os.path.join(_BASE, "outputs")
WEIGHTS = "yolo11x-pose.pt"     # modelo grande: necesario por la baja resolucion
                                # (se descarga solo la 1a vez, ~113 MB)

# Recorte de la banda donde estan sentados los concejales (y la ampliamos x4
# para que la gente -muy pequena a 640x360- sea detectable por la pose).
CROP_Y0, CROP_H, UP = 55, 110, 4
IMGSZ   = 2560

FPS        = 5      # fotogramas por segundo a analizar dentro de cada fase
REL_THR    = 0.80   # umbral de altura relativa para considerar "mano de voto"
FRAC_THR   = 0.34   # fraccion minima de fotogramas de la fase con mano arriba
MIN_DETS   = 2      # minimo de fotogramas detectados para decidir un asiento
SEAT_GAP   = 14     # px (nativos) para separar asientos contiguos al agrupar

# Votaciones: ventanas de cada fase en SEGUNDOS de video (de la transcripcion).
#   "pasamos a votar... votos a favor? en contra? abstenciones? se aprueba..."
VOTACIONES = [
    {"id": "V1_ratificacion_urgencia", "punto": "Punto 1 - Ratificacion de la urgencia",
     "fases": {"a_favor": (60.0, 64.2), "en_contra": (64.3, 67.8), "abstencion": (67.9, 69.3)}},
    {"id": "V2_PAI_FEDER", "punto": "Punto 2 - Aprobacion PAI / fondos FEDER",
     "fases": {"a_favor": (1162.8, 1167.2), "en_contra": (1167.3, 1170.3), "abstencion": (1170.4, 1173.6)}},
]
COLOR = {"a_favor": (0, 180, 0), "en_contra": (0, 0, 220), "abstencion": (0, 170, 220)}

# Esqueleto COCO-17 (pares de keypoints a unir) para dibujar la pose sobre el fotograma.
SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6), (0, 1), (0, 2), (1, 3), (2, 4)]


def draw_skeleton(img, p, c, col, kpt_thr=0.25):
    """Dibuja la pose (líneas + puntos) de una persona sobre img. p: kp (17,2), c: conf (17,)."""
    for a, b in SKELETON:
        if c[a] > kpt_thr and c[b] > kpt_thr:
            cv2.line(img, (int(p[a, 0]), int(p[a, 1])), (int(p[b, 0]), int(p[b, 1])), col, 2)
    for i in range(len(p)):
        if c[i] > kpt_thr:
            cv2.circle(img, (int(p[i, 0]), int(p[i, 1])), 3, (255, 255, 255), -1)
# ---------------------------------------------------------------------------

os.makedirs(OUTDIR, exist_ok=True)
model = YOLO(WEIGHTS)


def hand_rel_height(p, c):
    """Altura relativa max de las manos de una persona (None si no hay datos).
    p: keypoints xy (17,2) en px ampliados ; c: confianzas (17,)."""
    head = [p[i, 1] for i in (0, 1, 2, 3, 4) if c[i] > 0.20]   # nariz/ojos/orejas
    sh   = [p[i, 1] for i in (5, 6)          if c[i] > 0.20]   # hombros
    if not head or not sh:
        return None
    y_head, y_sh = min(head), float(np.mean(sh))
    if y_sh - y_head < 4:            # geometria degenerada
        return None
    best = None
    for ei, wi in ((7, 9), (8, 10)):            # (codo, muneca) izq / der
        y = None
        if c[wi] > 0.25:      y = p[wi, 1]
        elif c[ei] > 0.50:    y = p[ei, 1]      # si la muneca es dudosa, uso el codo
        if y is None:
            continue
        rel = (y_sh - y) / (y_sh - y_head)
        best = rel if best is None else max(best, rel)
    return best


def head_x(p, c, box):
    """Ancla horizontal estable del asiento: x de la cabeza (o centro de caja)."""
    xs = [p[i, 0] for i in (0, 1, 2, 3, 4) if c[i] > 0.20]
    return float(np.mean(xs)) if xs else (box[0] + box[2]) / 2.0


def analizar_frame(t):
    """Devuelve lista de detecciones (x_nativo, rel, box_ampliada) y el frame."""
    cap = cv2.VideoCapture(VID)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, fr = cap.read()
    cap.release()
    if not ok:
        return [], None, None
    band = fr[CROP_Y0:CROP_Y0 + CROP_H, :]
    up = cv2.resize(band, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
    r = model(up, conf=0.20, imgsz=IMGSZ, verbose=False)[0]
    dets = []
    if r.keypoints is not None and r.keypoints.conf is not None:
        kp = r.keypoints.xy.cpu().numpy()
        cf = r.keypoints.conf.cpu().numpy()
        bx = r.boxes.xyxy.cpu().numpy()
        for p, c, b in zip(kp, cf, bx):
            rel = hand_rel_height(p, c)
            x_nat = head_x(p, c, b) / UP
            dets.append({"x": x_nat, "rel": rel, "box": b, "kp": p, "kpc": c})
    return dets, up, fr


def cluster_seats(all_x):
    """Agrupa posiciones x en asientos (gap clustering 1D)."""
    if not all_x:
        return []
    xs = sorted(all_x)
    seats, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] <= SEAT_GAP:
            cur.append(x)
        else:
            seats.append(cur); cur = [x]
    seats.append(cur)
    return [float(np.median(s)) for s in seats]


def nearest_seat(x, centers):
    d = [abs(x - c) for c in centers]
    i = int(np.argmin(d))
    return i if d[i] <= 3 * SEAT_GAP else None


def sample_phase(t0, t1):
    ts = np.arange(t0, t1 + 1e-6, 1.0 / FPS)
    out = []
    for t in ts:
        dets, up, fr = analizar_frame(float(t))
        out.append((float(t), dets, up, fr))
    return out


def procesar_votacion(v):
    print(f"\n===== {v['id']}  ({v['punto']}) =====")
    # 1) muestrear todas las fases
    fase_data = {f: sample_phase(*win) for f, win in v["fases"].items()}

    # 2) definir asientos a partir de TODAS las detecciones de la votacion
    all_x = [d["x"] for f in fase_data for (_t, dets, _u, _fr) in fase_data[f] for d in dets]
    seats = cluster_seats(all_x)
    print(f"  asientos (personas) detectados: {len(seats)}")

    # 3) por asiento y fase: fraccion de fotogramas con mano de voto
    #    raised[seat][fase] = (frac, mean_rel, n)
    raised = defaultdict(dict)
    for f, frames in fase_data.items():
        per_seat = defaultdict(list)
        for (_t, dets, _u, _fr) in frames:
            for d in dets:
                s = nearest_seat(d["x"], seats)
                if s is not None:
                    per_seat[s].append(d["rel"] if d["rel"] is not None else -9)
        for s, rels in per_seat.items():
            rels = np.array(rels, float)
            frac = float(np.mean(rels >= REL_THR))
            raised[s][f] = (frac, float(np.mean(rels[rels >= REL_THR])) if frac > 0 else 0.0, len(rels))

    # 4) decidir el voto de cada asiento: la fase con mas evidencia
    decision = {}
    for s in range(len(seats)):
        best_f, best_frac = None, 0.0
        for f in v["fases"]:
            frac, mrel, n = raised[s].get(f, (0, 0, 0))
            if n >= MIN_DETS and frac >= FRAC_THR and frac > best_frac:
                best_f, best_frac = f, frac
        decision[s] = (best_f, best_frac)

    # 5) recuento + fiabilidad (los asientos con frac intermedia se marcan "revisar")
    FRAC_SEGURO = 0.60
    conteo = {f: 0 for f in v["fases"]}
    revisar = []
    for s, (f, frac) in decision.items():
        if f is not None:
            conteo[f] += 1
            if frac < FRAC_SEGURO:
                revisar.append((s, round(seats[s], 1), f, round(frac, 2)))
    no_vota = sum(1 for s, (f, _) in decision.items() if f is None)

    print(f"  >> A FAVOR={conteo['a_favor']}  EN CONTRA={conteo['en_contra']}  "
          f"ABSTENCION={conteo['abstencion']}  (sin voto/no concejal={no_vota})")
    seguros = {f: sum(1 for s, (ff, fr) in decision.items() if ff == f and fr >= FRAC_SEGURO)
               for f in v["fases"]}
    print(f"     (votos de confianza ALTA -> a_favor={seguros['a_favor']} "
          f"en_contra={seguros['en_contra']} abstencion={seguros['abstencion']})")
    if revisar:
        print(f"     REVISAR {len(revisar)} asiento(s) limite: " +
              ", ".join(f"x={x}({f},{fr})" for _s, x, f, fr in revisar))

    # 6) fotograma anotado del pico de cada fase + perfil temporal
    perfil = {}
    for f, frames in fase_data.items():
        counts = []
        best_idx, best_n = 0, -1
        for i, (_t, dets, _u, _fr) in enumerate(frames):
            n = sum(1 for d in dets if d["rel"] is not None and d["rel"] >= REL_THR)
            counts.append(n)
            if n > best_n:
                best_n, best_idx = n, i
        perfil[f] = (frames[0][0], [c for c in counts])
        _t, dets, up, fr = frames[best_idx]
        if up is not None:
            vis = up.copy()
            for d in dets:
                s = nearest_seat(d["x"], seats)
                voto = s is not None and decision[s][0] == f
                col = COLOR[f] if voto else (150, 150, 150)
                b = d["box"].astype(int)
                cv2.rectangle(vis, (b[0], b[1]), (b[2], b[3]), col, 2)
                draw_skeleton(vis, d["kp"], d["kpc"], col)   # esqueleto de la pose
                if d["rel"] is not None:
                    cv2.putText(vis, f"{d['rel']:.2f}", (b[0], b[1] - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
            cv2.putText(vis, f"{v['id']}  {f.upper()}  t={_t:.1f}s  count={conteo[f]}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, COLOR[f], 2)
            cv2.imwrite(os.path.join(OUTDIR, f"{v['id']}_{f}.jpg"), vis)

    # perfil temporal (figura)
    plt.figure(figsize=(10, 3))
    for f, win in v["fases"].items():
        t0 = win[0]
        ts = t0 + np.arange(len(perfil[f][1])) / FPS
        plt.plot(ts, perfil[f][1], "-o", ms=3, label=f, color=np.array(COLOR[f][::-1]) / 255)
    plt.xlabel("t (s)"); plt.ylabel("manos de voto"); plt.title(v["id"])
    plt.legend(); plt.grid(alpha=.3); plt.tight_layout()
    plt.savefig(os.path.join(OUTDIR, f"{v['id']}_perfil.png"), dpi=110); plt.close()

    return {
        "id": v["id"], "punto": v["punto"],
        "asientos_detectados": len(seats),
        "recuento": conteo,
        "recuento_confianza_alta": seguros,
        "sin_voto": no_vota,
        "asientos_a_revisar": [
            {"x": x, "voto": f, "confianza_frac": fr} for _s, x, f, fr in revisar
        ],
        "detalle_asientos": [
            {"asiento": s, "x": round(seats[s], 1),
             "voto": decision[s][0], "confianza_frac": round(decision[s][1], 2),
             "fiabilidad": ("alta" if decision[s][1] >= FRAC_SEGURO
                            else "media-revisar" if decision[s][0] else "-")}
            for s in range(len(seats))
        ],
    }


def main():
    resultados = [procesar_votacion(v) for v in VOTACIONES]
    with open(os.path.join(OUTDIR, "resultado_votaciones.json"), "w", encoding="utf-8") as fp:
        json.dump(resultados, fp, ensure_ascii=False, indent=2)
    print("\n=========== RESUMEN ===========")
    for r in resultados:
        c = r["recuento"]
        print(f"{r['punto']}")
        print(f"   A FAVOR: {c['a_favor']}   EN CONTRA: {c['en_contra']}   "
              f"ABSTENCION: {c['abstencion']}")
    print(f"\nJSON e imagenes en: {OUTDIR}")


if __name__ == "__main__":
    main()
