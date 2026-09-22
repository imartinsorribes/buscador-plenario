# Informe técnico — Ampliación multimodal SEDIPUALBA (pestaña Manuales)

Reto 2 IDAL · julio de 2026. Este informe detalla qué usa exactamente la ampliación: fuentes de conocimiento, modelos, pipeline de indexación, mecánica de las respuestas, funciones de gestión, validación y coste.

# 1. Qué es

Un asistente que responde *cómo se hace algo* en la plataforma de administración electrónica Sedipualb@ (SEGEX, SERES, SECON, SEFACE, SEFYCU, SECOIN, SECA…) usando **solo la documentación oficial** y citando la fuente exacta — página del manual o minuto del vídeo — **verificable en un clic**. Incluye un chat de dudas con hilo al que se le puede **adjuntar una captura de pantalla** ("estoy atascado aquí") y utilidades de gestión: subir manuales nuevos, indexar vídeos tutoriales, ficha imprimible y voto de utilidad.

# 2. Fuentes de conocimiento

| Fuente | Volumen | Tratamiento |
|---|---|---|
| Manuales PDF oficiales | 13 documentos (SEGEX oficial y v2, SERES ×4, SECON ×2, SEFACE, SEFYCU, SECOIN, SECA, Conceptos) | texto troceado **por páginas** (fragmento citable = manual + página) |
| Capturas de pantalla de los manuales | ~270 imágenes | descritas con visión, orientadas a búsqueda (qué pantalla es, qué botones se ven) |
| Vídeos tutoriales | transcritos e indexados | ventanas de ~45-60 s de narración → cita = minuto exacto enlazado |

Todo acaba en un **espacio vectorial único** (los tres tipos se buscan a la vez), en una colección ChromaDB local.

# 3. Qué tecnología usa cada pieza

| Pieza | Herramienta | Detalle |
|---|---|---|
| Extracción de PDF | PyMuPDF | texto por páginas; imágenes con su página de origen; filtro de iconos/logos por tamaño |
| Descripción de capturas | **gemini-3.5-flash** (visión, OpenRouter) | prompt orientado a búsqueda; **caché por hash sha1** del contenido: cada imagen se paga UNA vez (céntimos) y nunca más |
| Embeddings | **BGE-M3** (fp16) | multilingüe (castellano/valencià); mismo espacio para texto, capturas y vídeo |
| Índice vectorial | **ChromaDB** (local) | recarga **en caliente** por fichero de versión: subir un manual no requiere reiniciar |
| ASR de vídeos tutoriales | faster-whisper large-v3-turbo (int8, GPU) | + corrección léxica del dominio (glosario Sedipualb@: «SEGES»→SEGEX, «seficu»→SEFYCU…) |
| LLM de respuesta | **qwen2.5:14b** (GPU 16 GB) · 7b (8 GB) · 3b local | degradación automática si el remoto no responde; prompt con reglas estrictas (ver §4) |
| Render de páginas citadas | PyMuPDF → PNG cacheado | la cita abre la página o la captura exacta en la propia página (lightbox) |
| Ficha imprimible | reportlab | PDF con pregunta + respuesta + páginas citadas incrustadas |

# 4. Cómo se construye una respuesta (RAG con citas verificables)

1. **Recuperación**: la pregunta se vectoriza (BGE-M3) y se recuperan los 8 mejores fragmentos con **ranking por tipo de fuente**: PDF oficial > vídeo > manual generado. El vídeo solo entra si es realmente relevante (similitud ≥ 0,52 y a menos de 0,12 del mejor resultado — umbrales medidos).
2. **Generación acotada**: el LLM recibe los fragmentos numerados con instrucciones estrictas: usar SOLO los fragmentos, citar cada afirmación con [n], enumerar TODOS los pasos (incluidas alternativas, p. ej. certificado digital Y Cl@ve), responder en el idioma de la pregunta, no añadir temas colindantes, y decir honestamente si falta información.
3. **Presentación**: las citas se muestran como `[n · manual p.X]`, **clicables** — abren la página del manual o la captura concreta citada. Las fuentes citadas van destacadas; el resto, plegadas. Fragmentos de la misma página se agrupan en una sola tarjeta.
4. **Chat con ámbito blando**: el hilo hereda el manual dominante de la última búsqueda (coherencia), pero reserva huecos para fuentes globales — así los datos transversales de la plataforma (p. ej. Cl@ve, que vive en el manual de Conceptos) siempre tienen fuente citable. Esta decisión salió de un fallo real detectado y corregido: el ámbito duro producía citas mal atribuidas.
5. **Búsqueda por pantallazo**: la captura del usuario se describe con visión (misma caché), se compara con las ~270 capturas indexadas y, si el parecido supera 0,45, se identifica la pantalla (manual + página) y el asistente responde acotado a ese manual; si no, lo dice honestamente. El ámbito del chat queda fijado a ese manual para las siguientes dudas del hilo.

# 5. Funciones de gestión

- **Añadir un manual en PDF**: ingesta en 2 fases — el texto queda buscable al momento; las capturas se describen con visión en segundo plano y se reindexan solas.
- **Añadir un vídeo tutorial**: se transcribe (GPU) y queda indexado por minutos como una fuente más. Decisión de producto: los vídeos **no generan manuales**; bien indexados basta (el asistente enlaza el momento exacto para quien prefiera verlo).
- **Generador de manual ilustrado desde vídeo** (disponible por línea de comandos): con **barrera anti-duplicados** — si los manuales oficiales ya cubren ≥60 % de los capítulos del vídeo, se niega a crear un duplicado e indica qué manual lo cubre. Validado a ciegas: 10/14 capítulos coincidieron con el manual oficial descubierto después.
- **Diff de versiones** (disponible por API): fragmentos de la versión nueva sin equivalente semántico en la antigua, con su página (validado con SEGEX v2: detectó los diagramas de Gantt reales).
- **Feedback**: voto «¿te ha servido?» bajo cada respuesta → métrica viva de utilidad acumulada en local.

# 6. Validación (medida, no estimada)

| Prueba | Resultado |
|---|---|
| Recuperación (eval de 15 preguntas con respuesta conocida) | **hit@6 = 87 %** manual correcto; 100 % página exacta en las verificadas |
| Batería E2E (16 preguntas, con LLM, 3 pasadas en días distintos) | fuente correcta/honesta **16/16** · citas válidas **15/15** |
| Groundedness (apoyo de cada frase en las fuentes citadas) | 0,55-0,79 de media; las frases más débiles revisadas a mano = encabezados, no invenciones |
| Pregunta trampa fuera de dominio | rechazada honestamente, sin inventar |
| Pantallazo | pantalla identificada correctamente con capturas reales de dos manuales distintos |
| Verificación literal | respuestas cotejadas palabra a palabra contra la página citada del PDF |
| qwen2.5:7b vs 14b | mismo resultado en la batería (16/16 · 15/15) y 2,4× más rápido (~3 s vs ~8 s) |

# 7. Coste

| Concepto | Coste |
|---|---|
| Indexar un manual (texto) | 0 € |
| Describir sus capturas (visión, una única vez) | céntimos (cacheado por hash para siempre) |
| Cada pregunta / cada pantallazo con captura ya vista | 0 € (LLM local o GPU propia) |
| Pantallazo con captura nueva | céntimos (una descripción de visión) |

# 8. Privacidad

Los manuales son documentación pública del proveedor (sin datos personales). Los pantallazos del usuario se describen una vez (solo la descripción textual se conserva, en caché local) y el índice completo vive en el equipo del ayuntamiento. El voto de utilidad no guarda identidad.
