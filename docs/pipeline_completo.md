# Buscador Plenario Inteligente — Pipeline completo (act. 3-jul-2026)

**IDAL · Reto 2 + Ampliación multimodal.** Producto para ayuntamientos: de un vídeo de YouTube de un pleno municipal a un **acta verbatim** estilo Diario de Sesiones, **sin necesidad de un Diario oficial previo**, ejecutado **en local** (coste cero por pleno; los datos no salen del equipo). Ampliado con un **asistente multimodal de manuales y tutoriales** (SEDIPUALBA) con citas verificables. El Congreso de los Diputados se usa como banco de calibración.

## La aplicación — 5 pestañas (un solo comando de arranque)

| Pestaña | Qué hace | Autoría |
|---|---|---|
| **Generar acta** | YouTube → descarga → transcribe → separa voces → acta + visor + export | nuestra |
| **Registro de voces** | huella de voz por concejal, local por municipio, editable, con control de nitidez | nuestra |
| **Buscar** | búsqueda inteligente del corpus del Congreso (respuesta + fuentes; **evolución temporal** por legislaturas) | compañero (integrado) |
| **Manuales** | asistente multimodal SEDIPUALBA (manuales+capturas+vídeo, citas página/minuto) + **crear manual desde un vídeo** | nuestra (extra) |
| **Ciudadano** | "El Congreso, en datos": posiciones, contradicción, agenda, afinidad | compañero (integrado) |

`arrancar_uv.ps1` levanta todo (app :8000 + buscador :8100 + túnel SSH a la GPU de la UV); `arrancar.ps1` = modo local puro. El buscador se **auto-resucita** si se cae y el índice de manuales se **recarga sin reiniciar**.

# Pipeline de "Generar acta"

## Bloque A — De audio a texto
1. **Descarga** solo el audio (yt-dlp + Deno).
2. **ASR**: faster-whisper **large-v3-turbo int8** (elegido por bake-off: misma calidad que large-v3, 3× más rápido, mitad de VRAM). VAD (Silero) para pausas; **multilingüe por fragmento** (valencià/castellà); sin initial_prompt (envenenaba).
3. **Corrección léxica (lexfix)**: términos LOCALES contra glosario curado por similitud fonética + **alias exactos** ('SEGES=SEGEX') para errores conocidos del ASR. Conservador: verificado 0 daños colaterales.

## Bloque B — Quién habla (sin adivinar jamás)
4. **Diarización** (pyannote 3.1) con marca de **cruce** (solapamiento).
5. **Huella de voz** ECAPA-TDNN (192-d, multi-huella por persona).
6. **Nombres**: por defecto "Voz N". La identidad solo viene de (a) el secretario en el editor, o (b) una **huella registrada** (biometría consentida). El naming por anuncios/NER quedó desactivado tras medirlo (confundía "Maestre"/"Maestra": un nombre mal es peor que "Voz N").
7. **Asignación SUPERVISADA por huella** (novedad): si el municipio tiene concejales registrados, las huellas **corrigen el clustering** (tramo limpio ≥2,5 s que casa con umbral+margen → esa persona; voto por cluster ≥80 %; el cruce nunca decide, solo hereda). **Validado: pureza 100 %, cobertura 100 %, 0 falsos** en voces no registradas.

## El acta híbrida formal
Encabezado + **escudo del municipio** (descarga automática de Wikimedia Commons) + asistentes + orden del día (de la convocatoria PDF vía LLM) + estadísticas de palabra + cuerpo por puntos con **tiempos clicables al minuto del vídeo** y votación ("aprobado por mayoría/unanimidad"). **Visor** sincronizado acta+vídeo. **Export**: PDF (revisión) → **Word editable** (la secretaria remata) · transcripción original (auditoría). Flujo: *revisa el PDF; si hay que cambiar algo, Word*.

## Registro de voces (por municipio)
Pre-registro con frases leídas (multi-huella), **local y seccionado por municipio**, editable (renombrar/grupo), **control de nitidez** (repite si no está clara) y aviso del canal ("el micrófono cuenta"). RGPD: vector local, no el audio; borrable. **Alta de un municipio nuevo en 1 comando** (`alta_municipio.py`: entidad + escudo + glosario). **Backfill**: `backfill_canal.py` lista el canal del ayuntamiento y procesa el histórico en lote (Chiva: 99 plenos detectados).

# Ampliación multimodal (SEDIPUALBA) — Bloques E-I

**Asistente de manuales**: 12 PDFs (7 del reto + 5 oficiales de sedipualba.es) + vídeo tutorial (101 min) en un índice único (ChromaDB): texto por página, **270 capturas descritas con visión** (gemini-flash, cacheadas por hash = coste único) y 104 ventanas de vídeo con minuto. Respuesta con **citas verificables**: manual+página (con la página renderizada o la captura, clicable) y **vídeo al segundo** (`youtu.be/…?t=`, player embebido). **Modo conversación** (seguimientos: "¿y cómo lo firmo?"). **Evaluación de recuperación: hit@6 = 87 % por manual correcto; 100 % de página exacta en las verificadas.**

**Crear manual desde un vídeo** (desde la pestaña): transcripción → **capítulos por cambio semántico** → **BARRERA anti-duplicados** (si los manuales existentes cubren ≥60 % de capítulos → "ya existe manual, no se genera", indicando cuál) → si es hueco, manual **ilustrado** (fotograma del punto medio por capítulo + cada sección citando su tramo `min X–Y` con enlace clicable) → PDF/markdown. Los manuales generados **se indexan como fuente** (círculo cerrado), sin contar para la barrera. **Validación fuerte**: el manual de SECOIN se generó a ciegas y el manual oficial (descubierto después) coincide en 10/14 capítulos con mapeo página a página correcto.

# Infraestructura de cómputo

| Dónde | Qué corre | Nota |
|---|---|---|
| Portátil (RTX 3050, 4 GB) | Whisper, pyannote, ECAPA, BGE-M3 — todo el pipeline de actas | probado de punta a punta |
| **Servidor UV (RTX 4060 Ti, 16 GB)** | Ollama con **qwen2.5:14b** (trabajo) y mistral-small:24b (calidad) | túnel SSH por clave (sin contraseña); interruptor por variables `PLENO_OLLAMA_HOST`/`PLENO_LLM_MODEL`; sin variables, todo local |
| Nube (céntimos, coste único) | gemini-3.5-flash **solo para visión** (describir capturas) y redacción de manuales | elegido por bake-off |

# Métricas (todas medidas, ninguna estimada)

| Qué | Resultado | Cómo |
|---|---|---|
| Fidelidad vs Diario oficial | **88 %** palabras literales (media) | 3 plenos: 2 Congreso + **Ayto. Madrid** (85,3 %) |
| Precisión ASR (control) | 96,1 % (WER 3,9 %) | gold set verbatim Chiva + lexfix |
| Parecido global end-to-end | 90,8 % | Congreso PL-161 (3,5 h) |
| Separación de voces | 100 % (22/22 biunívoco) | PL-161 completo |
| **Asignación supervisada por huella** | **pureza 100 %, 0 falsos** | Chiva, 2 registrados, 92 tramos |
| Auto-aprendizaje de voces | 5/6 al 2º pleno | Chiva, entre sesiones |
| ASR turbo vs large-v3 | 88,0 % vs 87,9 % literal; **18,4× vs 6× tiempo real** | bake-off 3 plenos |
| **Buscador de manuales** | **hit@6 = 87 %** manual correcto; 100 % página en verificadas | eval_qa 15 preguntas |
| Manual generado vs oficial | 10/14 capítulos coinciden (generado A CIEGAS, oficial descubierto después) | SECOIN |

# Bake-off de LLMs (9 modelos, local + comercial)

En 4 GB: qwen2.5:3b (rápido, limpio) y **phi4-mini** (mejor extractor local). En 16 GB: **qwen2.5:14b = calidad comercial en extracción** (8/8 títulos reales del orden del día, 20 s). Comercial: **gemini-3.5-flash mejor valor** (único que además caza la coherencia; céntimos). mistral-small:24b no supera a qwen14b y es 2× más lento. Conclusión: local gratis para lo recurrente; nube céntimos solo para visión.

# Coste por pleno

| Capa | Coste |
|---|---|
| Pipeline completo local (o con GPU UV propia) | **0 €** (solo luz) |
| + visión para manuales (una vez por manual) | céntimos |
| Alternativa todo-nube (referencia) | ~1,5-3 €/pleno recurrente |

# Decisiones de diseño y límites honestos

- **Nada de regex para clasificar**; NER/embeddings/huellas/LLM. **Nunca adivinar identidades.** Local-first, RGPD (huella=vector local, consentimiento, borrable; transparencia en el editor).
- Límites medidos y documentados: (1) el **solapamiento** (hablar a la vez) no se atribuye — se marca cruce; (2) en cámaras grandes con muchas voces parecidas y poco audio la diarización ciega se degrada — **la asignación supervisada por huella lo corrige en el caso municipal**; (3) el denoise previo al ASR **empeora** (probado y descartado); (4) la coherencia automática del acta requiere modelo grande (mistral-7B local o gemini) — no disponible en 4 GB.
- Cada mejora descartada lo fue **con medición**, no por intuición (denoise, glosario automático, censura de caras, editor de coherencia local).

# Alertas para vecinos (pestaña 6, añadida el 4 de julio)

El producto deja de ser solo una herramienta para el secretario: **el vecino se suscribe** a temas de un **catálogo cerrado de 15** (vivienda, presupuestos, fiestas…) o al boletín de **todos los plenos**, y cuando su ayuntamiento trata uno recibe un correo con las **citas literales** (quién lo dijo), el **minuto donde empieza** el tema (enlace directo al vídeo) y el **acta en PDF**.

- **Detección semántica calibrada con datos** (sin regex): cada tema = frases-ancla → centroide BGE-M3; umbral 0,57 medido sobre plenos reales (verdaderos 0,57-0,64; ruido ≤0,56). Todo extractivo: cero riesgo de poner palabras en boca de nadie.
- **Privacidad por diseño**: catálogo cerrado → es imposible suscribirse a personas. Doble opt-in, baja en un clic, datos solo en la BD local del ayuntamiento.
- **Bienvenida inmediata**: al confirmar llega "lo último que se dijo de tus temas" del pleno más reciente.
- **Autopiloto**: `scripts/vigilante_canal.py` (tarea programada) detecta el pleno nuevo en el canal de YouTube, lo procesa solo y dispara los avisos. Guarda antiduplicados: regenerar un acta no reenvía correos; el backfill histórico no spamea.
- Sin SMTP configurado, los correos van a la **bandeja de demostración** de la pestaña (para la demo); con 3 variables de entorno se conecta el correo real.

# Manuales: 5 mejoras (4 de julio)

1. **Búsqueda por pantallazo**: el funcionario sube una captura de donde está atascado → la visión la describe (caché por hash: se paga una vez) → se identifica la pantalla en las capturas indexadas (manual + página, o nota honesta si no se reconoce) → el asistente, acotado a ese manual, responde el paso siguiente.
2. **"Qué cambió" entre versiones**: diff semántico entre dos manuales (validado con SEGEX oficial vs v2: 12 fragmentos nuevos con su página; detectó los diagramas de Gantt reales de la v2) + síntesis LLM citada.
3. **Feedback "¿te ha servido?"**: voto Sí/No bajo cada respuesta → métrica viva de utilidad acumulada en local.
4. **Multiidioma**: responde en el idioma de la pregunta (castellano o valencià), aunque los manuales estén en castellano.
5. **Ficha imprimible**: cualquier respuesta se descarga como PDF con la pregunta, la respuesta y las páginas citadas incrustadas.

Validación tras los cambios: batería de 16 preguntas de punta a punta — fuente correcta/honesta 16/16, citas válidas 15/15, pregunta trampa rechazada (`scripts/qa_manuales.py`).
