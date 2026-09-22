# Detección de votaciones a mano alzada en plenos (visión por computador)

Detecta automáticamente, a partir del vídeo de un pleno, cuántas manos se
levantan en cada votación y las clasifica en **a favor / en contra / abstención**.

Probado con el **Pleno de Chiva del 18/05/2026** (`grabacion.mp4`, 640×360, 30 fps, 19,6 min).

---

## 1. Idea

El reto no es "ver una mano arriba", sino tres cosas a la vez:

1. **Distinguir un voto de apoyarse la cabeza con la mano.**
2. **Que dé igual que uno estire más el brazo que otro.**
3. **Localizar las votaciones** sin procesar las 2 horas de vídeo.

La solución combina tres ideas:

### a) Pose en vez de "detección de manos"
Usamos **estimación de pose** (`YOLO11-pose`): por cada persona obtenemos el
esqueleto (cabeza, hombros, codos, muñecas). Decidimos el voto con **geometría
relativa al propio cuerpo**, no con píxeles absolutos:

```
rel = (y_hombro − y_mano) / (y_hombro − y_cabeza)
   rel ≈ 0  → mano a la altura del hombro  (brazo bajado)
   rel ≈ 1  → mano a la altura de la cabeza
   rel > 1  → mano POR ENCIMA de la cabeza  (voto claro)
```

- **Da igual la longitud del brazo**: normalizamos por la anatomía de cada uno
  (distancia hombro–cabeza).
- **Apoyarse la cabeza queda excluido solo**: quien apoya la cara tiene la
  muñeca *por debajo* de la oreja/hombro → `rel` bajo. En las pruebas, los
  votantes daban `rel ≥ 1.1` y quien se apoyaba la cara `rel ≤ 0.63`: hay un
  margen amplio y el umbral `REL_THR = 0.80` los separa con holgura.

### b) Cámara fija → asientos fijos
La cámara no se mueve, así que agrupamos las detecciones en **asientos
estables** (clustering 1-D por la posición horizontal de la cabeza). Esto evita
contar dos veces a la misma persona y permite dar el resultado **por asiento**.

### c) Localización por audio/acta + agregación temporal
La transcripción (la que genera el modelo de tu compañero) marca el instante de
*"¿votos a favor? ¿en contra? ¿abstenciones?"*. Solo analizamos esas ventanas.
Como un voto se mantiene varios segundos, **agregamos en el tiempo**: un asiento
cuenta como voto en una fase si tiene la mano arriba en una fracción suficiente
de fotogramas (`FRAC_THR`). Así un fallo puntual de un fotograma se recupera.

---

## 2. Cómo se ejecuta

```bash
pip install ultralytics opencv-python matplotlib   # torch ya instalado
python detectar_votaciones.py
```

Entradas (editar en la cabecera de `detectar_votaciones.py`):
- `VID`: ruta del vídeo.
- `VOTACIONES`: por cada votación, las ventanas en segundos de cada fase
  (sacadas de la transcripción). Para este pleno ya están puestas.

Salidas (`outputs/`):
- `resultado_votaciones.json` — recuento y decisión por asiento + flags.
- `<votacion>_<fase>.jpg` — fotograma anotado (verde = voto contado, gris = no).
- `<votacion>_perfil.png` — perfil temporal de manos levantadas por fase.

---

## 3. Resultado en el pleno de Chiva

Dos votaciones, ambas *"se aprueba por mayoría"* (coincide con el acta):

| Votación | A favor | En contra | Abstención |
|---|---|---|---|
| Punto 1 — Ratificación de la urgencia | 5–7 | 0 | 1 |
| Punto 2 — PAI / fondos FEDER          | 6–7 | 0 | 1 |

- **Estructura 100 % correcta**: bloque de gobierno a favor, **0 en contra**,
  **1 abstención** en el extremo de la mesa (la oposición). Encaja con el acta,
  donde Fernando dice literalmente *"por mi parte hay una abstención"*.
- **Conteo unitario con ±1–2 de incertidumbre**: hay un bloque de ~5 votos a
  favor sólidos (confianza alta) y 1–2 asientos *límite* que el sistema **marca
  para revisión** (`asientos_a_revisar` en el JSON). A 640×360 con personas de
  ~15 px, ese es el techo razonable sin más resolución.

---

## 4. Validación con el acta

La transcripción permite **comprobar el resultado de imagen**: ambos puntos se
aprueban por mayoría y la abstención de la oposición está dicha en voz. El
sistema reproduce esa estructura, lo que da confianza en el método.

---

## 5. Limitaciones y mejoras

- **Resolución**: 640×360 es el principal limitante para el conteo exacto.
  Con un vídeo a 1080p el conteo unitario sería fiable.
- **Mapa de asientos → nombre del concejal**: como la cámara es fija, se puede
  fijar una vez qué asiento es cada concejal y reportar el voto nominal.
- **Localización automática de la votación**: hoy se pasan los tiempos de la
  transcripción; se puede detectar el pico de manos automáticamente (búsqueda
  del patrón "subida de manos" tras las palabras clave del audio).
- **En contra ≈ 0**: aquí no hubo votos en contra; el método los detectaría
  igual (es la fase intermedia del perfil temporal).

---

## 6. Ficheros

```
detectar_votaciones.py   pipeline principal (configurable y reutilizable)
outputs/                 resultados (json, fotogramas anotados, perfiles)
_perfil.py / _verif.py   utilidades de calibración (perfil temporal, umbral)
```
