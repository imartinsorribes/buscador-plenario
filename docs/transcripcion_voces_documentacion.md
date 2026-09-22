# Transcripción y Voces del Pleno

Documentación técnica: arquitectura, fundamentos matemáticos y modelos · Reto 2 — Bloques de transcripción y registro de voces

**Abstract.** Este documento describe la primera mitad del pipeline: la conversión del vídeo de un pleno municipal en una **transcripción anclada al tiempo** y la atribución de cada intervención a su orador. Se detallan el modelo de reconocimiento de voz y su cuantización, el tratamiento de plenos bilingües, la corrección léxica con glosario municipal, la separación de voces (diarización), la identificación por huella de voz con consentimiento, la revisión humana y la metodología de evaluación — diseñada expresamente porque el Diario de Sesiones oficial no es una transcripción literal. Todas las cifras citadas están medidas sobre plenos reales.

# 1. Objetivo y visión general

La entrada es el enlace de YouTube del pleno; la salida, un **acta con estilo de Diario de Sesiones** donde cada intervención tiene su orador y cada frase su instante de vídeo. El principio de diseño que gobierna esta parte: **la identidad de un orador nunca se adivina** — sale del etiquetado humano o de una huella de voz registrada con conocimiento del interesado; una voz sin huella queda como «orador sin identificar». La marca de tiempo es el hilo estructural: gracias a ella el buscador salta al minuto exacto, las alertas enlazan el momento en que empieza un tema y el módulo de votaciones sabe qué ventana del vídeo mirar.

# 2. Del vídeo al audio

El vídeo se descarga con yt-dlp y se extrae el audio a WAV mono de 16 kHz (la frecuencia de trabajo del modelo). Un detector de actividad de voz (VAD) descarta silencios y pausas largas, de modo que el transcriptor solo procesa habla: menos coste y menos alucinaciones del modelo en tramos vacíos.

# 3. Transcripción (ASR)

## 3.1 Modelo y cuantización

Se emplea **Whisper large-v3-turbo** servido con **faster-whisper** (runtime CTranslate2) y cuantizado a **int8**: los pesos pasan de coma flotante de 16/32 bits a enteros de 8, reduciendo la memoria a ~1,5 GB — el modelo grande cabe así en una GPU doméstica de 4 GB. La elección no fue a ojo: en un bake-off contra el large-v3 completo, el turbo int8 obtuvo la **misma fidelidad** (88,0 % frente a 87,9 % de palabras literales contra Diarios oficiales) siendo el triple de rápido: **18,4× tiempo real** frente a 6× — un pleno de 3 horas se transcribe en ~10 minutos.

## 3.2 Plenos bilingües

En la Comunitat un pleno alterna castellano y valencià dentro de la misma sesión. La detección de idioma se hace **por fragmento**, no por vídeo: cada intervención se transcribe en su idioma real. Aguas abajo, el buscador usa embeddings multilingües, así que una consulta en castellano encuentra lo dicho en valencià y viceversa.

## 3.3 Salida anclada al tiempo

El resultado es un JSON de segmentos con marca de tiempo: cada frase conoce su segundo inicial y final. Esta estructura es la interfaz con el resto del sistema (búsqueda al minuto, alertas, ventanas de votación, muestras de audio del registro de voces).

# 4. Corrección léxica con glosario municipal

## 4.1 El problema

Whisper aprendió de audio genérico: transcribe perfectamente el léxico común, pero no conoce los topónimos, pedanías, partidas o siglas de cada municipio, ni los nombres de plataformas administrativas. Reentrenar (afinar) el modelo por municipio se evaluó y se descartó: coste alto y el error local apenas baja. La solución adoptada corrige el **texto**, no el modelo.

## 4.2 Mecanismo

El glosario de un municipio es un fichero de texto plano (`data/ref/terms_<municipio>.txt`) que se crea como plantilla en el **alta de la entidad** (un comando) y se rellena a mano con lo distintivo local — deliberadamente corto (el de Chiva tiene 6 términos). Sobre él operan dos mecanismos:

1. **Alias exactos** («MAL=BIEN», p. ej. `SEGES=SEGEX`): sustitución de palabra completa para errores conocidos del reconocedor. Riesgo nulo — la forma errónea no existe como palabra real.
2. **Similitud de cadenas**: cada palabra transcrita se compara con los términos del glosario mediante el ratio de `difflib.SequenceMatcher` sobre formas normalizadas (minúsculas, sin acentos). Una palabra suelta solo se corrige si el parecido supera un **umbral alto (0,90)**, y la sustitución conserva el patrón de mayúsculas original.

## 4.3 Lo que se probó y se descartó (con medición)

- **Emparejamiento fonético multipalabra**: corregiría «se hace» → SEFACE por sonar parecido; arrasaba frases comunes del castellano. Desactivado.
- **Reducción de ruido previa al ASR**: empeoraba la transcripción. Descartada.
- **Glosario extraído automáticamente del corpus**: no aportaba frente al curado a mano.

# 5. Evaluación del ASR: metodología propia

## 5.1 El problema metodológico

El Diario de Sesiones oficial **no es literal**: los taquígrafos corrigen, pulen y reordenan. Medir el error de palabra estándar,

    WER = (S + D + I) / N

(sustituciones, borrados e inserciones sobre N palabras de referencia), contra el Diario mediría la distancia entre *hablar* y *redactar*, no los errores del sistema. La evaluación es por ello doble:

## 5.2 Las dos medidas

1. **Patrón oro verbatim propio**: tramos de un pleno municipal real transcritos a mano, palabra a palabra. Contra esa referencia sí tiene sentido el WER: **precisión del 96,1 %** (WER 3,9 %, con la corrección léxica aplicada).
2. **Comparación a ciegas contra Diarios oficiales reales**: se genera el acta sin haber visto el Diario y se mide el porcentaje de palabras que coinciden literalmente. Con 2 plenos del Congreso y 1 municipio real con Diario (Madrid): **88 % literal de media** (Madrid, 85,3 %) — sabiendo que parte de la diferencia es el pulido del taquígrafo, no error del sistema.

# 6. Separación de voces (diarización)

Se emplea **pyannote speaker-diarization 3.1**: segmenta el audio, calcula un embedding de voz por tramo y agrupa los tramos por hablante (clustering aglomerativo), produciendo etiquetas anónimas VOZ 1, VOZ 2… con sus intervalos temporales. Alineando esos intervalos con los timestamps de la transcripción, cada frase queda asignada a una voz. Validación: en un pleno completo del Congreso (3,5 h), la correspondencia voz-orador fue **biunívoca en 22 de 22 oradores**. Límite honesto: el **solapamiento** (dos personas hablando a la vez) no se atribuye — se marca como cruce.

# 7. Identificación por huella de voz

## 7.1 Fundamento

Una huella de voz es un **vector de 192 dimensiones** producido por **ECAPA-TDNN** (SpeechBrain): e(audio) ∈ R^192, normalizado. La afinidad entre una voz del pleno y una huella registrada es la **similitud coseno** de sus vectores. Para cada voz anónima del pleno se calcula su embedding medio y se compara con las huellas de la entidad:

    identidad(v) = argmax_h sim(e(v), e(h))   si el máximo supera el umbral;
    en caso contrario, la voz queda «sin identificar».

Nunca se asigna un nombre por debajo del umbral: el sistema prefiere no saber a equivocarse.

## 7.2 Asignación supervisada (medida)

Con huellas registradas, la asignación no solo sugiere nombres: **corrige el clustering** de la diarización (tramos que el clustering ciego mezclaría se reasignan por huella). Validado en un pleno municipal real: **pureza del 100 % y 0 falsos positivos** sobre 92 tramos. Además, el sistema **aprende entre sesiones**: las voces confirmadas en un pleno sugieren automáticamente en el siguiente (5/6 aciertos al segundo pleno, medido).

## 7.3 Límite honesto: el canal importa

El embedding mezcla la voz con el **canal de grabación** (micrófono, sala, códec). Una huella registrada por un canal distinto al del pleno (p. ej. una nota de voz de mensajería) baja la similitud a la zona ambigua. Regla operativa: **enrolar con el mismo micrófono/canal del salón de plenos.**

# 8. Registro de voces y protección de datos

- Se registra a **cargos públicos, con su conocimiento**; el dato almacenado es el **vector** de 192 números — no el audio — y es **borrable** en cualquier momento.
- Todo permanece en el equipo del ayuntamiento (local-first).
- El etiquetado por otras vías especulativas (p. ej. deducir el nombre porque la presidencia lo anuncia) está **desactivado por diseño**: solo humano o huella.

# 9. Revisión humana y regeneración

La pestaña de registro incluye un **editor con reproductor**: la persona que levanta acta escucha muestras de cada voz, confirma o corrige el nombre, y **el acta se regenera** con las asignaciones confirmadas. El sistema está diseñado para que la última palabra sea siempre humana — la automatización prepara el 95 % del trabajo y la revisión lo remata.

# 10. El acta

La salida final es un acta **estilo Diario de Sesiones** (TXT y PDF): encabezado de sesión, intervenciones con orador y grupo, y orden del día si se aporta. Cada intervención conserva su enlace al minuto del vídeo. Las cifras de fidelidad de la sección 5 aplican al documento completo.

# 11. Modelos y componentes utilizados

| Componente | Modelo / herramienta | Papel |
|---|---|---|
| Descarga | yt-dlp | vídeo → audio WAV 16 kHz |
| ASR | Whisper large-v3-turbo (faster-whisper, int8, CUDA) | transcripción 18,4× tiempo real en GPU de 4 GB |
| Corrección léxica | glosario municipal + difflib (umbral 0,90) y alias exactos | términos locales que el ASR no conoce |
| Diarización | pyannote speaker-diarization 3.1 | separación en voces anónimas |
| Huella de voz | ECAPA-TDNN (SpeechBrain), vector 192-d | identificación por similitud coseno, con umbral |
| Acta | plantilla estilo Diario + reportlab | TXT/PDF con orador, grupo y minuto |

# 12. Rendimiento y coste

Un pleno de 3 horas: ~10 minutos de transcripción y ~20-45 minutos de pipeline completo (descarga → ASR → diarización → huellas → acta → índice) en una GPU de 4 GB. Coste recurrente: **0 €** (solo electricidad). Sin GPU, el proceso es viable en CPU como tarea nocturna.

# 13. Resumen del flujo

1. yt-dlp descarga el vídeo y extrae el audio (WAV 16 kHz); el VAD descarta silencios.
2. Whisper turbo int8 transcribe con detección de idioma por fragmento; cada frase sale con su marca de tiempo.
3. El glosario del municipio corrige los términos locales (alias exactos + similitud con umbral alto).
4. pyannote separa las voces; ECAPA compara cada voz con las huellas registradas y nombra solo por encima del umbral.
5. La secretaría revisa con el editor (escucha, confirma) y el acta estilo Diario se regenera.
6. La transcripción anclada al tiempo alimenta al resto del sistema: búsqueda al minuto, alertas y votaciones.
