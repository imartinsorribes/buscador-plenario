# Buscador Plenario Inteligente — Dossier técnico (mi parte)
### IDAL · Reto 2 — Generación del acta a partir del vídeo del pleno

> Documento de estudio para la reunión con el profesor. Cubre **mi parte**: convertir el vídeo
> de un pleno en un acta formal, buscable y verificable, **sin necesitar un acta oficial previa**.
> (Las otras partes —búsqueda de actas oficiales y modo ciudadano/KPIs— las llevan mis compañeros.)

---

## 1. El problema y la solución

**Problema.** Muchos ayuntamientos no pueden pagar una transcripción profesional de sus plenos.
El pleno queda grabado en vídeo (YouTube), pero **sin acta buscable**: nadie puede consultar qué
se dijo, quién lo dijo ni qué se votó sin verse horas de vídeo.

**Solución.** A partir de **un enlace de YouTube** generamos automáticamente:
1. La **transcripción** completa (voz a texto), buscable.
2. Un **acta formal** con el estilo del *Diario de Sesiones* (PDF + texto): asistentes, orden del
   día, estadísticas, desarrollo por puntos y votaciones.
3. Un **visor sincronizado** acta↔vídeo (clic en una frase → salta a ese momento).

Todo **en local** (sin enviar datos a la nube ni pagar por API) y **a ciegas** (sin un acta oficial
de referencia; esa solo la usamos para *calibrar* contra el Congreso, que sí publica Diarios).

---

## 2. Arquitectura — el pipeline

```
   Enlace YouTube
        │  (yt-dlp + Deno)
        ▼
 [A] DESCARGA  ──►  audio (.m4a/.wav) + vídeo (.mp4)
        │
        ▼
 [B] TRANSCRIPCIÓN (ASR)            faster-whisper large-v3-turbo (int8, GPU)
        │   · VAD (corta silencios)   · multilingüe (valencià/castellà)
        ▼
 [C] DIARIZACIÓN (¿quién habla?)    pyannote 3.1 → clusters de voz + solapamientos
        │   · fusión de voces (ECAPA) + absorción de clusters fantasma
        ▼
 [D] NOMBRADO                       anuncios ("tiene la palabra…") + NER + roster
        │                            (en municipal: "Voz N" → etiquetado humano 1 vez)
        ▼
 [E] CORRECCIÓN LÉXICA (lexfix)     términos locales contra glosario (fonético)
        │
        ▼
 [F] ACTA  (estilo Diario de Sesiones)   reportlab → PDF + texto
        │   · orden del día (convocatoria, vía LLM) · estadísticas · votaciones
        ├──► [G] VISOR sincronizado acta↔vídeo (FastAPI /sync)
        └──► [H] VOTACIONES POR VISIÓN (integración): YOLO-pose cuenta manos
```

**Bucle que mejora solo (self-improving):** al etiquetar las voces una vez, se guarda una *huella
de voz* del orador; en el **siguiente** pleno del mismo ayuntamiento esa voz se reconoce sola.

---

## 3. Cada bloque en detalle

### [A] Descarga
- **yt-dlp** (descargador) + **Deno** (runtime JS para resolver el `nsig` de YouTube).
- Audio para la transcripción; vídeo (≤480p) para el visor y la visión.
- *Decisión:* para plenos largos se pueden bajar **solo los tramos** necesarios (`--download-sections`),
  no el vídeo entero.

### [B] Transcripción (ASR — *Automatic Speech Recognition*)
- **faster-whisper** con el modelo **large-v3-turbo** en **int8** (entra en 4 GB de VRAM).
- **VAD** (*Voice Activity Detection*): recorta silencios y trocea en pausas → evita que Whisper
  "se salte" texto en tramos largos de habla rápida.
- **`multilingual=True`**: detecta el idioma **por fragmento** → imprescindible en plenos bilingües
  (valencià/castellà). Forzar "es" destrozaba el valenciano ("L'esmena" → "La semana").
- **`word_timestamps`**: tiempos por palabra (los usa la votación por visión para saber el instante
  exacto de "¿votos a favor?").

### [C] Diarización (¿quién habla?)
- **pyannote-audio 3.1**: segmenta el audio en *clusters* de voz (SPEAKER_00, 01…).
- **Solapamiento (cruce):** marca los tramos donde hablan dos a la vez (discusión) y los excluye de
  las huellas de voz.
- **Fusión / absorción:** une clusters que son la misma persona (coseno de huella ECAPA) y absorbe
  clusters "fantasma" diminutos nacidos del cruce → arregla el "Voz 4 que en realidad es Voz 3".

### [D] Nombrado (¿quién dijo qué?)
- **Anuncios:** detecta "tiene la palabra el señor X" + **NER** (reconocimiento de entidades) + casado
  con el **roster** (lista de concejales). Funciona bien en el Congreso (anuncios formales).
- **En municipal** apenas hay anuncios → las voces salen como **"Voz N"** y el secretario las etiqueta
  **una sola vez** (escucha una muestra, pone el nombre). *No recomendamos nombre/cargo a ciegas*
  (falla mucho); solo la **huella de voz** ofrece una sugerencia fiable de un clic.

### [E] Corrección léxica (`lexfix`)
- El ASR ya está cerca del techo, pero falla en **términos locales** ("mancomunidad" → "bancomunidad").
- Ningún ajuste de Whisper lo arregla (probado prompt, hotwords, modelo grande).
- `lexfix` corrige por **similitud fonética** contra un glosario cerrado del municipio (sin regex de
  clasificación): conservador, no toca palabras correctas ni inventa.

### [F] Acta (estilo *Diario de Sesiones*)
- **reportlab** genera el PDF (calco del Diario nuevo del Congreso: membrete, una columna, versalitas).
- **Orden del día:** los puntos salen de la **convocatoria** (PDF) → un **LLM** local extrae los
  títulos oficiales exactos. Si no hay convocatoria, se detectan por el habla ("punto número uno").
- **Estadísticas:** tiempo por orador y por partido. **Asistentes:** oradores + intervenciones.
- **Tiempos enlazados al vídeo** (clic en el minuto → YouTube en ese segundo).

### [G] Visor sincronizado
- **FastAPI** sirve `/sync`: vídeo de YouTube (IFrame API) + transcripción que se resalta sola; clic
  en una frase salta al vídeo. Para verificar el acta contra la grabación.

### [H] Votaciones por visión (integración con la parte del compañero)
- **YOLO11-pose** (ultralytics) detecta manos levantadas y cuenta a favor / en contra / abstención.
- Se dispara con **nuestros tiempos** (las ventanas de cada votación salen de la transcripción con
  *word-timestamps*). El recuento se coloca en su punto del acta; los fotogramas con el **esqueleto**
  de pose sirven de prueba visual.

---

## 4. Stack tecnológico (qué y por qué)

| Tecnología | Para qué | Por qué esta |
|---|---|---|
| **faster-whisper** (large-v3-turbo, int8) | Transcripción (ASR) | 5× más rápido que large-v3, calidad casi igual; int8 entra en 4 GB |
| **pyannote-audio 3.1** | Diarización (quién habla) | Estándar de facto en separación de locutores |
| **ECAPA-TDNN** (speechbrain) | Huella de voz (192-d) | Reconocer al mismo orador entre plenos (self-improving) |
| **BGE-M3** (sentence-transformers) | *Embeddings* semánticos | Búsqueda por significado y comparación de actas; multilingüe |
| **Transformers (NER)** | Nombres en los anuncios | Extraer entidades de persona del habla |
| **Ollama + qwen2.5:3b** | LLM local | Resúmenes neutrales y extracción del orden del día de la convocatoria; cabe en 4 GB |
| **YOLO11-pose** (ultralytics) | Votaciones por visión | Contar manos levantadas a mano alzada |
| **reportlab** + **PyMuPDF** | Acta PDF / render | Documento formal estilo Diario de Sesiones |
| **FastAPI** + Tailwind + YouTube IFrame | Interfaz (Bloque D) | UI moderna; visor con vídeo incrustado |
| **yt-dlp** + **Deno** | Descarga de YouTube | Resolver el anti-bot de YouTube (nsig) |

**Hardware:** todo corre en una **RTX 3050 Laptop (4 GB VRAM)** → coste cero por transcripción, dato
local (clave para RGPD y para el argumento "municipios sin presupuesto").

---

## 5. Validadores y métricas (cómo sabemos que funciona)

> Idea central: el *Diario de Sesiones* oficial **no es literal** (edita el habla), así que el WER
> crudo contra él no sirve. Medimos con las herramientas adecuadas a cada cosa.

| Qué medimos | Herramienta | Resultado |
|---|---|---|
| **Precisión del ASR** (palabra a palabra) | `scripts/eval_goldset.py` (vs *gold set* verbatim hecho a mano, 5 min de Chiva, 693 palabras) | **WER 4,3% → ~96% de acierto** (3,9% con lexfix) |
| **Por qué no WER vs Diario** | `scripts/eval_asr.py` | En 208 min solo hay ~5 tramos literales → no medible; lo demostramos |
| **¿Detecta que es la MISMA voz?** | `scripts/eval_voice.py` (cluster ↔ orador oficial) | **Consistencia 22/22 = 100%** (biunívoco) en PL-161 |
| **Acierto de NOMBRE** (de los anuncios) | `scripts/compare_diario.py` | 87% — pero el nombre lo confirma el humano 1 vez; lo que importa es la voz (100%) |
| **Parecido end-to-end vs Diario oficial** | `scripts/compare_diario.py` (PL-161, pleno de 3,5 h, a ciegas) | **90,8%** · cobertura 100% · fidelidad 0,89 · tema 87% · **votaciones 4/4** |
| **Reconocimiento de voz entre sesiones** | `src/voiceid.py` (2 plenos de Chiva) | **5 de 6** voces reconocidas (sim 0,81–0,92); la 6ª, nueva, **rechazada** (open-set: nunca inventa) |
| **Votaciones por visión** | `src/vote_detect.py` (Chiva) | Sentido correcto ("aprobado por mayoría"); conteo aproximado (vídeo a 360p) |
| **Bilingüe** | Llíria (pleno en valencià, 2,5 h) | valencià y castellà transcritos cada uno en su idioma |

**Cómo leer los números clave (para el profesor):**
- **96%** de transcripción sobre audio real, validado contra transcripción humana.
- **Separación de voz 100%** (cada persona = una voz, uno a uno): etiquetando una vez → atribución
  perfecta y reutilizable. El "87%" es solo el adivina-nombres automático, que el producto **no usa**.
- **90,8%** de parecido con el Diario oficial del Gobierno, **a ciegas**, en un pleno de 3,5 h.

---

## 6. Decisiones de diseño (y su porqué)

1. **A ciegas** (sin acta oficial): es el caso real del municipio. El Diario solo se usa para *calibrar*.
2. **NER/embeddings/LLM, nunca regex** para clasificar/extraer (más robusto y mantenible).
3. **lexfix posterior**, no afinar Whisper: el ASR está en el techo; los términos locales se arreglan
   con un glosario, no reentrenando.
4. **Multilingüe por fragmento**: forzar "es" rompe el valenciano.
5. **Etiquetado humano 1 vez + reúso de huella** en lugar de auto-nombrado: el auto-nombrado es
   propio del Congreso (anuncios) y falla en municipal; la voz sí es fiable y mejora sola.
6. **RGPD desde el diseño**: el dato es local; la huella se guarda **con consentimiento** (casilla
   "Guardar voz", opt-out) y hay **aviso de transparencia**. Base: cargos públicos / publicidad de
   los plenos. No se aplica al público.
7. **Solo clips para la visión**: no descargar plenos de 5 h enteros.

---

## 7. Limitaciones honestas (mejor decirlas tú antes que las pregunten)

- **Conteo de votos**: el vídeo de Chiva en YouTube es 360p → infracuenta (detecta ~5–6 de ~9). El
  **sentido** (aprobado/mayoría) es correcto. Con vídeo en HD sería exacto.
- **Solapamiento (cruce de voces)**: cuando hablan a la vez, la atribución puede fallar; lo marcamos
  como "(cruce de intervenciones)". Es inherente a la diarización.
- **Orden del día automático** (sin convocatoria): los títulos salen aproximados → por eso usamos la
  convocatoria oficial (PDF → LLM) cuando se aporta.
- **Nombres**: a ciegas no se "saben"; se confirman una vez (humano) o por huella.

---

## 8. Preguntas probables del profesor (y respuestas)

- **"¿No es esto solo Whisper?"** → No. Whisper es solo el bloque A. El valor está en hacerlo **a
  ciegas y formal**: diarización + identidad de voz reutilizable + acta estilo Diario + votaciones por
  visión + validación. Y todo **local** (RGPD, coste cero).
- **"¿Cómo sabéis que funciona si no hay acta?"** → Calibramos contra el **Diario oficial del
  Congreso** (90,8%) y contra un **gold set verbatim** hecho a mano (96%).
- **"¿Y si se equivoca con un nombre?"** → La **voz** es 100% consistente; el nombre lo confirma el
  secretario **una vez** y queda bien en todas sus intervenciones (y para los próximos plenos).
- **"¿Datos personales / RGPD?"** → Local, con consentimiento por persona (opt-out), aviso de
  transparencia, cargos públicos. (El DPD de Chiva confirmó que basta el aviso, sin firma.)
- **"¿Escala a plenos largos?"** → Sí: validado en uno de 3,5 h (Congreso) y 2,5 h (Llíria).
- **"¿Qué os diferencia del resto?"** → Acta verbatim + identidad de voz reutilizable + **votaciones
  leídas por visión** (ni la videoacta oficial de Llíria transcribe el debate: solo enlaza al vídeo).

---

## 9. Glosario

- **ASR**: transcripción automática del habla (voz → texto).
- **VAD**: detección de actividad de voz (separa habla de silencio).
- **Diarización**: dividir el audio por *quién* habla (sin saber el nombre).
- **Huella de voz / *embedding* de locutor (ECAPA)**: vector que representa una voz; voces parecidas
  → vectores cercanos (coseno alto).
- **Embedding semántico (BGE-M3)**: vector que representa el *significado* de un texto.
- **NER**: reconocimiento de entidades nombradas (personas, organizaciones…).
- **WER** (*Word Error Rate*): % de palabras mal transcritas frente a una referencia.
- **Open-set**: el sistema admite que una voz sea de alguien **nuevo** y no fuerza un nombre.
- **Pose / *keypoints* (YOLO-pose)**: esqueleto de articulaciones de cada persona en la imagen.
- **LLM**: modelo de lenguaje grande (aquí qwen2.5:3b, local vía Ollama).

---

# ACTUALIZACIÓN (3 de julio de 2026)

Este dossier describe el sistema a 25 de junio. Desde entonces (ver `pipeline_completo.pdf`, el documento maestro actualizado):

- **Asignación supervisada por huella**: el registro de voces ya no solo sugiere nombres — corrige el clustering de la diarización (pureza 100 % medida, 0 falsos). La identidad sale solo del humano o de la huella consentida; el naming por anuncios quedó desactivado.
- **Validación externa nueva**: Ayuntamiento de **Madrid** (municipio real con Diario verbatim): 85,3 % de palabras literales a ciegas; media de 3 Diarios oficiales = 88 %.
- **Servidor GPU de la UV** (RTX 4060 Ti 16 GB): qwen2.5:14b vía túnel SSH con interruptor por variables de entorno; bake-off de 9 LLMs local+comercial.
- **Ampliación multimodal SEDIPUALBA completa** (pestaña Manuales): asistente sobre 12 manuales + 270 capturas descritas por visión + vídeo tutorial, con citas página/minuto (hit@6 = 87 %); y generador de **manuales ilustrados desde vídeos** con barrera anti-duplicados (validado a ciegas contra el manual oficial: 10/14 capítulos coinciden).
- **Buscador del Congreso v2**: consultas de evolución temporal por legislaturas.
- Operativa: arranque con un comando (`arrancar_uv.ps1`), auto-resurrección de servicios, alta de municipio en 1 comando, backfill del canal del ayuntamiento.
- **(4-5 de julio)** Pestaña **Alertas para vecinos**: suscripción a temas de catálogo cerrado (o a todos los plenos) con correo de citas literales + minuto de inicio + acta; detección semántica calibrada (umbral 0,57 medido), doble opt-in, vigilante del canal para el autopiloto. Y **5 mejoras en Manuales**: búsqueda por pantallazo (visión), diff entre versiones (validado con SEGEX v2), feedback de utilidad, respuestas en valencià y ficha PDF imprimible.
