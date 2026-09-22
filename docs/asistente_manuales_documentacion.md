# Asistente Multimodal de Manuales SEDIPUALBA

Documentación técnica: arquitectura, fundamentos matemáticos y modelos · Reto 2 — Ampliación

**Abstract.** Este documento describe el funcionamiento de un asistente de consulta sobre la documentación oficial de la plataforma de administración electrónica Sedipualb@ (13 manuales PDF, ~270 capturas de pantalla y vídeos tutoriales). El sistema sigue el principio *indexar una vez, consultar muchas*: la documentación se procesa una sola vez (fase costosa, offline, con visión artificial para las capturas) y a partir de ahí responde preguntas en lenguaje natural con la garantía de que **cada afirmación lleva una cita verificable** — manual y página, o minuto del vídeo — comprobable en un clic. Se detallan la construcción de la base de conocimiento multimodal, la representación vectorial, la recuperación con prioridad de fuente, el ámbito blando del modo conversación, la localización de pantallas a partir de una captura del usuario, la generación con citas obligatorias y la evaluación empírica de cada etapa.

# 1. Objetivo y visión general

El usuario pregunta *cómo se hace algo* en la plataforma («¿cómo se registra una omisión de la función interventora?») y obtiene una respuesta con pasos completos donde cada afirmación lleva su fuente exacta. La unidad de cita es deliberadamente **gruesa y verificable**: la *página* de un manual (que se muestra renderizada junto a la respuesta) o el *minuto* de un vídeo (reproducible embebido). El objetivo de diseño no es solo acertar, sino que el funcionario pueda **comprobar** que se acierta sin salir de la página.

Hay dos modos de consulta: la **búsqueda** (un turno; la pregunta queda fija sobre la respuesta) y el **asistente de dudas** (chat con hilo, que mantiene contexto y admite adjuntar una captura de pantalla del punto donde el usuario está atascado).

# 2. Construcción de la base de conocimiento

## 2.1 Texto por páginas

Cada manual PDF se trocea **por páginas**: un fragmento es la tupla f = (texto, manual, página, tipo). Se elige la página como unidad — y no un chunking por longitud — porque es la unidad natural de cita de un manual: la afirmación «se pulsa el botón Login [1 · SERES p.3]» se verifica mirando la página 3. El texto de contexto que recibe el modelo por fragmento es de ~1 300 caracteres.

## 2.2 Capturas de pantalla: visión con caché

Las imágenes de cada PDF se extraen con su página de origen y se filtran los iconos y logotipos por tamaño (se exige ancho ≥ 200 px, alto ≥ 120 px y peso ≥ 8 KB). Cada captura c se convierte en un texto buscable mediante un modelo de visión g condicionado al texto de su página P(c):

    desc(c) = g(c, P(c))

con instrucciones orientadas a la recuperación: qué pantalla o menú se ve, qué acción ilustra y qué botones o campos aparecen (citando sus rótulos literales), sin especular. La descripción se almacena bajo el hash SHA-1 del contenido de la imagen, de modo que el coste de visión es **amortizado O(1) por imagen**: relanzar la ingesta no repite llamadas y el coste total es c · |imágenes nuevas| (céntimos, una única vez).

## 2.3 Vídeos tutoriales: ventanas con marca de tiempo

Los vídeos se transcriben (ASR en GPU) y la narración se empaqueta en ventanas de ~700 caracteres (≈45-60 s) que conservan el instante inicial t₀; la cita resultante es el minuto exacto, enlazado y reproducible. Sobre la transcripción se aplica una corrección léxica del dominio con un glosario verificado de la plataforma («SEGES» → SEGEX, «seficu» → SEFYCU), solo con sustituciones de una palabra y alias exactos — el emparejamiento fonético multipalabra se midió y se descartó por dañino. Decisión de producto: los vídeos **no generan manuales**; bien indexados, basta con enlazar el momento para quien prefiera verlos.

## 2.4 Espacio único e idempotencia

Los tres tipos de fragmento (texto, captura descrita, ventana de vídeo) se proyectan al **mismo espacio vectorial**, de modo que una consulta los recupera indistintamente y compiten por relevancia. La ingesta es idempotente (borra y reinserta la colección) y publica un fichero de versión; los procesos servidores detectan el cambio y **recargan el índice en caliente**: subir un manual nuevo no requiere reiniciar nada.

## 2.5 Almacenamiento: dónde vive todo

El índice es una colección de **ChromaDB persistente en disco local** (`sedipualba`), dentro del mismo almacén vectorial de la aplicación. A fecha de este documento contiene **929 fragmentos**: 495 de texto por páginas, 330 capturas descritas y 104 ventanas de vídeo. Cada fragmento lleva su embedding (d = 1024) y un diccionario de metadatos según su tipo:

| Tipo | Metadatos | La cita resultante |
|---|---|---|
| texto | manual, página | «manual X · pág. Y» (abre la página renderizada) |
| captura | manual, página, fichero de imagen | «manual X · pág. Y · captura» (abre ESA imagen) |
| vídeo | id del vídeo, título, segundo inicial | «vídeo · min M:SS» (reproductor en el minuto) |

Los identificadores de fragmento son **deterministas** (derivados del manual y la página, o del vídeo y la ventana), de modo que la reingesta es reproducible. Alrededor del índice, en `data/sedipualba/`, viven los artefactos de apoyo: los PDF originales (`manuales/`), las capturas extraídas (`images/`), las páginas renderizadas bajo demanda que abren las citas (`pages/`, PNG a 110 dpi, cacheadas), la caché de descripciones de visión (`descripciones.json`, clave = SHA-1 de la imagen), los transcripts de los vídeos (`transcripts/`), el glosario del dominio, los votos de utilidad (`feedback.jsonl`) y el set de evaluación.

**Recarga en caliente.** Cada ingesta escribe al terminar un fichero de versión (`index.version`). Cada proceso servidor guarda la versión que vio; si en una consulta detecta que cambió, limpia la caché de clientes compartida de ChromaDB y reabre la colección — por eso subir un manual desde la web lo hace buscable sin reiniciar nada.

**Concurrencia.** La creación del cliente de ChromaDB está protegida con un candado y se calienta en el arranque del servidor: durante la validación se detectó (y corrigió) una carrera real en la que dos hilos inicializando el cliente a la vez corrompían el estado compartido de la biblioteca. Las consultas sobre la colección ya abierta son concurrentes sin problema.

# 3. Representación vectorial

Se emplea BGE-M3 (BAAI/bge-m3, d = 1024) como función de embedding e : X → R^d. Los vectores se normalizan a la esfera unidad, ê(x) = e(x)/‖e(x)‖₂, y la afinidad entre consulta q y fragmento p es la similitud coseno

    sim(q, p) = ê(q) · ê(p) ∈ [−1, 1].

BGE-M3 es multilingüe: castellano y valencià comparten el espacio, por lo que una pregunta en valencià recupera fragmentos redactados en castellano (y el modelo de lenguaje responde en el idioma de la pregunta). El índice es ChromaDB con HNSW, con coste de búsqueda esperado O(log N).

# 4. Recuperación con prioridad de fuente

## 4.1 Ranking por tipo de fuente

No todas las fuentes valen lo mismo: el **manual oficial tiene prioridad sobre el vídeo**. La documentación escrita es la referencia normativa (citable por página); el vídeo es un apoyo que solo entra cuando es genuinamente pertinente (§4.2). La consulta recupera un pool ampliado de candidatos, aplica esta prioridad y sirve k = 8 fragmentos al modelo.

## 4.2 Umbral relativo para el vídeo

El vídeo solo entra si es genuinamente pertinente. Siendo s* la mejor similitud del pool, una ventana v se admite si

    sim(q, v) ≥ 0,52  y  sim(q, v) ≥ s* − 0,12,

umbrales calibrados empíricamente (con el umbral absoluto solo, aparecían vídeos incorrelados con la pregunta; el término relativo lo corrige).

## 4.3 Ámbito blando en el chat

Cuando el hilo está acotado a un manual M (heredado de la búsqueda anterior o del pantallazo), la recuperación no se restringe del todo: se toman los mejores k−3 fragmentos de M y se **reservan 3 huecos globales** para el resto de manuales,

    F = top_{k−3} { f : manual(f) = M } ∪ top_3 { f : manual(f) ≠ M }.

La motivación es un fallo real detectado en la validación: con ámbito duro, un dato transversal de la plataforma (el acceso con Cl@ve, que vive en el manual de Conceptos y no en el de SERES) aparecía en la respuesta **con la cita mal atribuida** — el modelo lo sabía, pero no tenía fuente citable. El ámbito blando garantiza que los datos transversales siempre tienen su fuente.

# 5. Generación con citas obligatorias

El modelo de lenguaje recibe los k fragmentos numerados, cada uno con su fuente exacta, y un contrato estricto: responder **solo** con los fragmentos; citar cada afirmación con su número [n]; enumerar **todos** los pasos que consten, incluidas las alternativas (p. ej. certificado digital *y* Cl@ve si constan ambas); responder en el **idioma de la pregunta**; no añadir temas colindantes no preguntados; y declarar honestamente si falta información. En la interfaz, cada cita se muestra expandida — `[1 · SERES p.3]` — y es **clicable**: abre la página del manual o la captura concreta citada (cada cita, su imagen). Las fuentes citadas van destacadas; las no citadas, plegadas; los fragmentos de una misma página se agrupan en una tarjeta.

# 6. Localización de pantallas (búsqueda por pantallazo)

El usuario adjunta en el chat una captura u de la pantalla donde está atascado. El sistema la describe con el mismo modelo de visión (y la misma caché por hash), d = g(u), y resuelve la pantalla más parecida entre las capturas indexadas:

    c* = argmax_{c : tipo=captura} sim(e(d), e(desc(c))).

Si sim ≥ 0,45 se declara «pantalla reconocida» (manual y página de c*) y la pregunta —o una por defecto, «¿en qué pantalla estoy y cuál es el paso siguiente?»— se responde **acotada a ese manual** (con el ámbito blando de §4.3); el hilo del chat queda fijado a él para las dudas siguientes. Por debajo del umbral, el sistema se **abstiene honestamente** de identificar y responde solo con texto.

# 7. Conversación con hilo

El chat conserva las últimas 3 interacciones para resolver referencias anafóricas («¿y cómo lo firmo?», «¿dónde está ese botón?»). El ámbito del hilo se hereda como la **moda de los manuales citados** en la última respuesta, y el usuario puede liberarlo en un clic («usar todos los manuales»).

# 8. Funciones de gestión

- **Alta de un manual (PDF)** en dos fases independientes: el texto se indexa al momento (buscable en segundos, sin GPU de visión); las capturas se describen en segundo plano y se reindexan solas al terminar. La ingesta interrumpida se reanuda: la caché de descripciones hace que solo se paguen las imágenes nuevas.
- **Alta de un vídeo tutorial**: descarga, transcripción y ventanas por minutos (§2.3), sin generar documento.
- **Diff entre versiones** (API): novedades de la versión B respecto de la A como los fragmentos sin equivalente semántico, nuevo(B|A) = { b : max_a sim(b, a) < 0,75 }, cada uno con su página; validado con SEGEX v2 (detectó la incorporación real de los diagramas de Gantt).
- **Voto de utilidad** («¿te ha servido?») bajo cada respuesta: métrica viva acumulada en local.

# 9. Evaluación empírica

| Prueba | Resultado |
|---|---|
| Recuperación, 15 preguntas con respuesta conocida | hit@6 = 87 % manual correcto; 100 % página exacta en las verificadas |
| Batería extremo a extremo, 16 preguntas × 3 pasadas | fuente correcta/honesta 16/16 · citas válidas 15/15 |
| Groundedness (soporte por frase, máx. similitud con lo citado) | medias 0,55–0,79; los mínimos, revisados a mano, son encabezados de paso, no invenciones |
| Pregunta fuera de dominio (trampa) | abstención honesta, sin inventar |
| Localización de pantalla | identificada correctamente con capturas reales de dos manuales distintos |
| Verificación literal | respuestas cotejadas palabra a palabra contra la página citada |

La *validez de citas* se comprueba mecánicamente: todo [n] de la respuesta debe existir en las fuentes servidas. El *groundedness* de una respuesta con frases s₁…sₘ y fragmentos citados F se define como soporte(sᵢ) = max_{f∈F} sim(e(sᵢ), e(f)); los valores bajos se inspeccionan manualmente.

# 10. Modelos y componentes utilizados

| Componente | Modelo / herramienta | Papel |
|---|---|---|
| Embeddings | BGE-M3 (d = 1024, fp16) | espacio único texto · capturas · vídeo, multilingüe |
| Índice vectorial | ChromaDB (HNSW) | búsqueda O(log N), local, recarga en caliente |
| Visión | gemini-3.5-flash (OpenRouter) | descripción de capturas y pantallazos; caché SHA-1: 1 pago por imagen |
| ASR de vídeos | faster-whisper large-v3-turbo (int8, GPU) | transcripción 18,4× tiempo real |
| Corrección léxica | lexfix + glosario Sedipualb@ | términos del dominio tras el ASR |
| Modelo de lenguaje | qwen2.5:14b (GPU 16 GB) · qwen2.5:7b (8 GB) · qwen2.5:3b (local) | generación con citas; el 7b iguala al 14b en la batería (16/16 · 15/15) siendo 2,4× más rápido; degradación automática al local si el remoto no responde |
| Render de páginas | PyMuPDF | página citada → PNG cacheado (verificación en un clic) |
| Ficha imprimible | reportlab | pregunta + respuesta + páginas citadas, en PDF |

# 11. Rendimiento y coste

Consulta caliente: recuperación < 0,5 s; generación ~3 s (7b) / ~8 s (14b). Indexar un manual: segundos (texto) + visión en segundo plano (céntimos, una única vez por imagen — coste marginal cero a partir de ahí). Pantallazo con imagen nueva: una llamada de visión; con imagen ya vista: gratuito. Todo lo recurrente corre en local: el coste por consulta es 0 €.

# 12. Resumen del flujo de una consulta

1. La pregunta (o la descripción del pantallazo) se vectoriza con BGE-M3.
2. HNSW recupera el pool; se aplica la prioridad oficial ≻ vídeo, el umbral relativo del vídeo y, en el chat, el ámbito blando del manual en contexto.
3. El modelo de lenguaje redacta con el contrato de citas obligatorias, en el idioma de la pregunta.
4. La interfaz muestra la respuesta con citas clicables `[n · manual p.X]` que abren la página o captura exacta, las fuentes destacadas y las utilidades (ficha PDF, voto de utilidad).
5. En el chat, el hilo conserva contexto y ámbito para las siguientes dudas.
