# Memoria técnica — Buscador Plenario Inteligente + Ampliación SEDIPUALBA

Reto 2 IDAL · julio de 2026. Este documento resume la arquitectura, los modelos, el consumo de recursos (memoria y tiempo) y el coste de operación del sistema completo. Las cifras marcadas como medidas provienen de las validaciones descritas en `pipeline_completo.pdf`.

# 1. Objeto

Producto para ayuntamientos con dos piezas: (a) generación y explotación de actas de pleno a partir del vídeo de YouTube — transcripción, separación de voces, acta estilo Diario de Sesiones, búsqueda semántica al minuto exacto, alertas a vecinos —; y (b) ampliación multimodal para SEDIPUALBA: un asistente que responde con los manuales oficiales (texto, capturas y vídeos tutoriales) citando página o minuto verificables.

Principios: local-first (los datos no salen del ayuntamiento), nada de reglas regex para clasificar (NER, embeddings, huellas de voz y LLM), identidades jamás adivinadas (solo etiquetado humano o huella de voz consentida), y toda métrica publicada está medida, no estimada.

# 2. Arquitectura

- **Aplicación web** (FastAPI + página única Tailwind), puerto 8000, seis pestañas: Generar acta, Registro de voces, Buscar, Manuales, Ciudadano y Alertas.
- **Servicio del corpus del Congreso** (puerto 8100), con proxy y auto-resurrección desde la app (si el proceso muere o queda zombi, se mata y relanza solo).
- **Ollama local** (11434) para LLM de respaldo y **Ollama remoto** en el servidor GPU de la UV (RTX 4060 Ti 16 GB) vía túnel SSH (11435). Interruptor por variables de entorno (`PLENO_OLLAMA_HOST`, `PLENO_LLM_MODEL`) y **degradación automática**: si el túnel cae, las llamadas caen al modelo local sin interrumpir el servicio.
- **Almacenamiento**: SQLite (entidades, plenos, roster, suscripciones de alertas) + ChromaDB (vectores) + ficheros (audio, transcripts, actas, manuales). Todo en el equipo.

# 3. Modelos y consumo de memoria

## En el portátil (RTX 3050 Laptop, 4 GB VRAM)

| Modelo | Uso | Precisión | VRAM aprox. |
|---|---|---|---|
| faster-whisper large-v3-turbo | transcripción (ASR) | int8 | ~1,5 GB |
| pyannote speaker-diarization 3.1 | separación de voces | fp32 | ~1 GB |
| ECAPA-TDNN (SpeechBrain) | huellas de voz (192-d) | fp32 | ~0,1 GB |
| BGE-M3 | embeddings (búsqueda e índices) | fp16, batch 4, seq 512 | ~1,2 GB |
| qwen2.5:3b (Ollama) | LLM local de respaldo | q4 | ~2,3 GB |
| bge-reranker-v2-m3 | reordenación fina | — | **desactivado** |

Notas medidas: los modelos se cargan por fases (el ASR y la diarización no conviven con el LLM); BGE-M3 exige fp16 + batch pequeño para caber. El reranker **no cabe** junto a BGE-M3: en Windows la VRAM desbordada pasa a memoria compartida sin dar error y la consulta se eterniza — se midió que en CPU costaba ~1,3 s/candidato con top-1 idéntico en 2 de 3 consultas, así que se desactivó en este equipo (orden por embedding: búsqueda en 0,3-0,4 s).

## En el servidor UV (RTX 4060 Ti, 16 GB VRAM)

| Modelo | Uso | VRAM aprox. |
|---|---|---|
| qwen2.5:7b-instruct | mismo resultado que el 14b en la batería E2E (16/16 fuentes, 15/15 citas) y 2,4× más rápido (~3 s vs ~8 s en caliente) — candidato idóneo para GPUs de 8 GB | ~5-6 GB |
| qwen2.5:14b | LLM de trabajo (extracción, respuestas de manuales, recap del corpus) | ~10-11 GB |
| mistral-small:24b | LLM de calidad (bajo demanda) | ~14,3 GB |

El bake-off de 9 LLMs concluyó: qwen2.5:14b da calidad comercial en extracción (8/8 títulos reales del orden del día); mistral-small no lo supera y es el doble de lento.

## En la nube (céntimos, un solo caso de uso)

| Modelo | Uso | Coste |
|---|---|---|
| gemini-3.5-flash (OpenRouter) | visión: describir capturas de manuales y pantallazos del usuario | céntimos; **cacheado por hash: cada imagen se paga una vez** |

# 4. Consumo de tiempo por pleno (medido)

- ASR turbo int8: **18,4× tiempo real** (un pleno de 3 h se transcribe en ~10 min de GPU).
- Pipeline completo (descarga → transcripción → diarización → huellas → acta → índice): **~20-45 min por pleno** según duración.
- Búsqueda semántica en actas: 0,3-0,4 s en caliente. Respuesta del asistente de manuales con qwen14b: ~20-40 s.
- Detección de temas para alertas: segundos por pleno (reutiliza embeddings ya calculados si el pleno está indexado).

# 5. Coste de operación

| Concepto | Coste |
|---|---|
| Pipeline completo en local (o GPU propia/UV) | **0 €** (solo electricidad) |
| Visión para manuales y pantallazos | céntimos, una vez por imagen (caché por hash) |
| Referencia todo-nube (evitada) | ~1,5-3 € por pleno recurrente |

El diseño evita costes recurrentes: lo que se repite (transcribir, buscar, responder) corre en local; la nube solo se usa para visión puntual cacheada.

# 6. Bloques funcionales

1. **Acta desde YouTube**: descarga (yt-dlp), ASR por fragmentos con detección de idioma (plenos bilingües valencià/castellano), corrección léxica del dominio (`lexfix` con glosario por municipio), diarización, asignación supervisada por huella de voz (pureza 100 % medida, 0 falsos), acta TXT/PDF estilo Diario, votaciones apoyadas en visión (YOLO-pose, módulo del compañero).
2. **Registro de voces**: alta de huella por entidad (vector de 192 dimensiones, no audio), sugerencia automática de orador en plenos nuevos, editor con reproductor para revisar/regenerar el acta.
3. **Buscar**: corpus del Congreso (667 plenos, XI-XV legislaturas) con interpretación de consulta y evolución temporal; y búsqueda extractiva en las actas propias con orador y minuto enlazado.
4. **Manuales (SEDIPUALBA)**: índice multimodal (13 PDFs por páginas + ~270 capturas descritas por visión + vídeos tutoriales indexados por minutos). Respuestas con citas clicables `[n · manual p.X]` que abren la página o captura exacta; chat de dudas con hilo y ámbito; **búsqueda por pantallazo** (el funcionario sube una captura de dónde está atascado y el sistema identifica la pantalla y el paso siguiente); subida de PDFs nuevos con indexación inmediata; ficha PDF imprimible; respuesta en el idioma de la pregunta; feedback de utilidad.
5. **Ciudadano**: dashboard de datos del Congreso (módulo del compañero).
6. **Alertas para vecinos**: suscripción a un catálogo cerrado de 15 temas (o al boletín de todos los plenos) con doble opt-in; correo 100 % extractivo con las citas literales, el minuto donde empieza cada tema (enlace al vídeo) y el acta; umbral de detección calibrado con plenos reales (0,57); vigilante del canal de YouTube para el autopiloto; sin servidor de correo, bandeja de demostración local.

# 7. Privacidad y RGPD

- Los datos del pleno (audio, transcript, acta) permanecen en el equipo del ayuntamiento.
- Huellas de voz: vector matemático local, de cargos públicos, con conocimiento, borrable; nunca se adivina una identidad.
- Alertas: catálogo cerrado (imposible suscribirse a personas por diseño), doble confirmación, baja en un clic, correos en la base local.
- La única salida a internet es la visión puntual de capturas de manuales (documentación pública del proveedor).

# 8. Métricas de validación (medidas, no estimadas)

| Qué | Resultado |
|---|---|
| Fidelidad vs Diario oficial (3 plenos, incl. Ayto. Madrid) | 88 % literal medio (Madrid 85,3 % a ciegas) |
| Precisión ASR (gold set verbatim + lexfix) | 96,1 % |
| Separación de voces (PL-161 completo) | 100 % (22/22) |
| Asignación por huella (Chiva) | pureza 100 %, 0 falsos |
| Buscador de manuales (eval 15 preguntas) | hit@6 87 %; 100 % página exacta en verificadas |
| Batería E2E del asistente (16 preguntas, 3 pasadas) | fuente correcta 16/16 · citas válidas 15/15 |
| Alertas (calibración con 3 plenos reales) | verdaderos 0,57-0,64 vs ruido ≤0,56 |

# 9. Operativa y resiliencia

Arranque con un comando (`arrancar_uv.ps1`: túnel + variables + servidor). Auto-resurrección del servicio del corpus (incluye matar procesos zombis). Degradación automática del LLM remoto al local si el túnel cae. Índice de manuales con recarga en caliente (subir un PDF no requiere reiniciar). Alta de un municipio nuevo en un comando (entidad + escudo + glosario). Backfill del histórico del canal por lotes y vigilante diario para plenos nuevos.

# 10. Selección de modelo por municipio (lógica borrosa)

La última capa del sistema es un **selector borroso** que responde a la pregunta operativa: *¿qué modelo conviene a ESTE ayuntamiento?* No todos los consistorios tienen los mismos recursos, así que la decisión no puede ser fija.

- **Entradas** (por municipio): VRAM disponible, presupuesto, sensibilidad de los datos, exigencia de calidad y urgencia.
- **Fuzzificación**: cada variable pasa a grados de pertenencia (baja / media / alta) con funciones triangulares.
- **Reglas legibles** (extracto): *si la privacidad es ALTA y la VRAM BAJA → modelo local pequeño con revisión humana*; *si la calidad exigida es ALTA y hay VRAM ALTA → qwen 14b*; *si la tarea es de VISIÓN → nube puntual con caché por hash*; *si el remoto NO RESPONDE → degradar al local*. Esta última regla ya corre en producción: es la degradación automática del túnel.
- **Salida**: un grado de idoneidad ∈ [0, 1] por modelo — una decisión **explicable** (se ven las reglas disparadas), no una caja negra.

Los grados se apoyan en las métricas **medidas** del bake-off de 9 modelos (calidad de extracción, velocidad, VRAM, coste y capacidad de visión). Cuatro escenarios ilustrativos: con GPU de 4 GB y datos sensibles mandan la privacidad y la memoria (modelo local pequeño); con GPU de 8 GB — la más común en un consistorio con algo de equipo — gana qwen2.5:7b (igualó al 14b en la batería E2E y responde 2,4× más rápido); con GPU de 16 GB gana qwen2.5:14b; en tareas de visión, la nube puntual cacheada. Sin GPU, el pipeline sigue siendo viable en CPU como proceso nocturno.

![selector](docs/selector_borroso.png)
