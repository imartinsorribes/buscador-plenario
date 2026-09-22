# Estudio del baseline — pleno 27/01/2026 (DSCD-15-PL-161)

Documento para estudiar QUÉ medimos, CÓMO se calcula cada métrica, qué valor dio y qué
significa. Pleno de prueba: vídeo YouTube `kO3eztYBvDo` (3h27m) ↔ Diario oficial PL-161.

---

## 0. Datos de partida (dónde está cada cosa)

| Qué | Fichero | Contenido |
|---|---|---|
| Texto de Whisper | `data/transcripts/kO3eztYBvDo.json` | 1929 segmentos: `start,end,text,speaker(diariz.),name,party,avg_logprob,no_speech_prob` |
| Acta generada | `data/actas/kO3eztYBvDo.acta.{txt,pdf}` | nuestra acta (sumario + desarrollo) |
| Diario oficial | `data/diarios/DSCD-15-PL-161.PDF` | acta oficial (ground truth) |
| Roster | `data/roster.json` | 276 diputados/Gobierno (nombre, grupo) |
| Corpus | ChromaDB `data/processed/chroma` | ~130 plenos de la XV legislatura |

---

## 1. Bloque A — texto de Whisper (la transcripción)

**Cómo:** `faster-whisper large-v3-turbo`, `int8`, GPU; `vad_filter` (recorta silencios),
`beam_size=5`, `condition_on_previous_text=false` (evita bucles), `initial_prompt` de dominio
(vocabulario parlamentario). Salida: 1929 segmentos con timestamps, 3h27m (12 428 s).

Cada segmento guarda ahora la **confianza** de Whisper:
- `avg_logprob`: log-probabilidad media del segmento (cuanto más cerca de 0, más seguro).
- `no_speech_prob`: probabilidad de que NO sea voz.
→ Es la señal de fiabilidad para municipios **sin** Diario (no hay con qué comparar; te fías de la confianza del modelo).

---

## 2. Fidelidad de la transcripción vs el Diario  (`scripts/validate_transcription.py`)

Mide el **Bloque A** comparando el texto de Whisper con el acta oficial. **OJO:** el Diario
**no es literal** (los taquígrafos editan: quitan muletillas, corrigen, normalizan cifras), así
que esto **infravalora** la precisión real del ASR — nunca dará 100% aunque Whisper sea perfecto.

| Métrica | Cómo se calcula | Valor | Qué significa |
|---|---|---|---|
| Recall de contenido | palabras de contenido (>3 letras, sin *stopwords*) de Whisper que aparecen en el Diario ÷ total de Whisper | **90.9%** | 91% de nuestras palabras "con significado" están en el acta oficial |
| Recall de entidades/cifras | nombres en mayúscula + números de Whisper que están en el Diario ÷ total | **73.2%** | bajo sobre todo por **formato de cifras** ("120.000" vs otra forma), no por errores reales |
| Similitud semántica | cada frase de Whisper → coseno máximo con alguna frase del Diario (embeddings BGE-M3), promediado | **0.856** | el sentido coincide mucho aunque las palabras exactas difieran |

> 4471 palabras de contenido · 724 entidades/cifras · 1253 frases analizadas.

---

## 3. EL BASELINE — nuestra acta vs la oficial, A CIEGAS  (`scripts/compare_acta.py`)

Esta es **la métrica que cuenta**: mide el **sistema entero** (texto + quién dijo qué). Se
genera nuestra acta **sin mirar el Diario** (nombres por NER+roster, no por el oficial) y se
compara con la oficial. El oficial es "la respuesta del examen", solo para puntuar.

**Cómo se calcula (paso a paso):**
1. **Nuestras intervenciones**: agrupar segmentos consecutivos del mismo orador (nombre por NER+roster) → 33 intervenciones (sin Presidencia ni trámite).
2. **Oficiales**: parsear el Diario → intervenciones con orador oficial → 25.
3. **Alinear por CONTENIDO** (no por nombre, para no hacer trampa): se embeben ambos textos (BGE-M3), se calcula la matriz de similitud y se alinean en orden con Needleman-Wunsch (admite huecos). → 25 parejas con similitud ≥ 0.5.
4. Sobre las parejas alineadas se miden las 3 cifras:

| Métrica | Cómo | Valor | Qué significa |
|---|---|---|---|
| **Cobertura** | nº de intervenciones oficiales que logramos emparejar ÷ total oficiales | **100%** | capturamos las 25 intervenciones del acta oficial, no se nos escapa ninguna |
| **Acierto de orador** | parejas donde nuestro nombre ≈ el oficial (similitud de tokens ≥ 0.6) ÷ parejas | **80%** | en 20 de 25 acertamos el "quién dijo qué" **a ciegas**; los fallos son apellidos que Whisper oye mal (p. ej. "Marcos Ortega" donde el oficial dice "Marí Bosó") |
| **Fidelidad de contenido** | similitud semántica media de las parejas | **0.892** | nuestro texto se parece mucho al oficial intervención a intervención |

---

## 4. Bloque B — diarización y nombrado (quién dijo qué)

- **Diarización** (`pyannote 3.1`): separa voces por el audio → **26 oradores**, 2026 turnos.
  No nombra (etiquetas `SPEAKER_00…`); además no aísla bien a la Presidencia (turnos cortos).
- **Nombrado** (`src/speakers.py`, SIN regex): combina (1) **embeddings** (detecta el acto de
  "dar la palabra" por similitud a frases-prototipo), (2) **NER** español (extrae el apellido),
  (3) **roster** (enlaza el nombre ruidoso de Whisper con el real por similitud de tokens).
  Resultado: 92 turnos, 41 intervenciones con nombre. (Con `--diario` se alinea por orden con el
  oficial = acta perfecta, pero eso NO es el camino del producto.)

---

## 5. Relaciones entre las métricas (cómo encaja todo)

- **Fidelidad de contenido (3) ⇐ calidad del ASR (Bloque A).** Si Whisper transcribe mejor
  (large-v3), sube la fidelidad y baja el ruido de nombres. Por eso medimos large-v3.
- **Acierto de orador (3) ⇐ Bloque B** (diarización + NER + roster). Es independiente del texto:
  mide si acertamos la persona. El 20% de fallo viene de apellidos mal oídos → se ataca con mejor
  NER, más roster, o cruzando con el Diario donde exista.
- **Cobertura (3) ⇐** que la diarización no fusione turnos ni se deje intervenciones, y que el
  detector de relevo dispare. 100% = el esqueleto del pleno está completo.
- **(2) vs (3):** la (2) (recall vs Diario) es un **proxy** limitado porque el Diario no es
  literal; la (3) (acta-vs-acta) es la métrica de producto. La (2) sirve sobre todo para
  **comparar modelos** (turbo vs large-v3) con la misma vara.
- **Precisión REAL del ASR:** ninguna de las de arriba lo es (el Diario no es literal). Para
  afirmar "95-99%" hace falta **WER contra un gold verbatim** (2-3 min transcritos a mano):
  herramienta lista en `scripts/validate_verbatim.py`, pendiente de ese gold.

---

## 6. Resúmenes (pendiente de generar)

Los **resúmenes de contenido** del pleno (de qué se habló) NO están generados aún en esta
tanda. El módulo existe: `src/summarize.py` (LLM local `qwen2.5:3b` vía Ollama, map-reduce) con
verificación anti-alucinación por NLI (`src/verify.py`). Se pueden generar por pleno o por
intervención cuando quieras.

---

## 7. Qué queda para subir los números

- **large-v3** (en curso): re-transcribir → re-medir (2) y (3) → antes/después de fidelidad.
- **Acierto de orador**: mejor NER / más roster / cruce con Diario donde exista.
- **Gold verbatim**: para el WER real (precisión absoluta del ASR).
- **Bucle**: `compare_acta.py` genera además un informe detallado `data/processed/comparacion_*.md`
  (tabla intervención a intervención: orador nuestro vs oficial, ¿coincide?, textos enfrentados)
  para estudiar dónde divergimos en cada iteración.
