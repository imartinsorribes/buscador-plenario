# Alertas al Ciudadano

Documentación técnica: arquitectura, fundamentos matemáticos y modelos · Reto 2 — Pestaña Alertas

**Abstract.** Este documento describe el sistema de alertas para vecinos: un ciudadano se suscribe a temas de un **catálogo cerrado** (o al boletín de todos los plenos) y, cuando su ayuntamiento trata uno en un pleno, recibe un correo con las **citas literales**, el **minuto donde empieza** el tema (enlazado al vídeo) y el **acta**. Se detallan la representación de los temas como centroides de embeddings, la calibración empírica del umbral de detección, la composición 100 % extractiva del correo, el ciclo de suscripción con doble confirmación, las garantías de privacidad por diseño y el modo autopiloto (vigilante del canal de YouTube). El sistema no usa ningún modelo generativo: todo lo que llega al vecino es literal y verificable.

# 1. Objetivo y visión general

El pleno municipal es público, pero nadie ve tres horas de vídeo. La alerta invierte la carga: el vecino declara **una vez** qué temas le importan y el sistema le avisa **cuando ocurren**, llevándolo al momento exacto. Principios de diseño: (a) catálogo **cerrado** de temas — nunca texto libre —, lo que hace la detección calibrable e impide por construcción seguir a personas; (b) contenido **100 % extractivo** — citas literales con orador y minuto, sin resúmenes generados —; (c) todo local: las suscripciones viven en la base de datos del ayuntamiento.

# 2. El catálogo de temas

Quince temas municipales (vivienda; urbanismo y obras; impuestos y tasas; presupuestos; fiestas y cultura; deportes; educación; medio ambiente; agua y residuos; movilidad y tráfico; seguridad; servicios sociales; empleo; sanidad; participación ciudadana) más una suscripción especial: **«todos los plenos»** (boletín). Cada tema t se define con 3-5 **frases-ancla** redactadas en el registro real de un pleno («la subida o bajada del IBI y de los impuestos municipales», …). Añadir un tema = añadir frases; no hay reglas ni palabras clave.

# 3. Representación: centroides de tema

Con el mismo embedder del resto del sistema (BGE-M3, d = 1024), el tema t se representa como el **centroide normalizado** de sus anclas a₁…aₘ:

    c_t = normalizar( (1/m) · Σ ê(aᵢ) ).

La afinidad entre un fragmento de pleno x y el tema es la similitud coseno ê(x) · c_t. Usar frases-ancla en lugar de la palabra del tema hace la detección robusta a la forma de hablar real de un pleno.

# 4. Detección sobre el pleno

## 4.1 Fragmentos con orador y segundo

El pleno se representa como fragmentos con hablante y marca de tiempo. Si el pleno está en el índice vectorial, sus **embeddings se reutilizan** (coste cero); si no, se trocea el transcript agrupando segmentos consecutivos del mismo hablante (≤ ~900 caracteres) — conservando el nombre etiquetado y el partido — y se embebe al vuelo (segundos de GPU).

## 4.2 Regla de disparo, calibrada

Un tema t se declara presente si algún fragmento x cumple

    ê(x) · c_t ≥ 0,57   con   |texto(x)| ≥ 120 caracteres.

Ambas constantes salen de una **calibración empírica** sobre plenos reales (un municipio y dos del Congreso): los positivos verdaderos midieron 0,57-0,64 — p. ej. 0,640 el debate de vivienda en el pleno de la ley de alquiler, 0,632 un punto de Hacienda real — y el ruido quedó en ≤ 0,569. El filtro de longitud existe porque las interjecciones cortas producen similitudes espurias («El miércoles, el miércoles.» marcaba 0,55 en *movilidad*). La calibración es reproducible (`scripts/calibrar_alertas.py`).

## 4.3 Presentación cronológica

De los fragmentos que superan el umbral se toman los mejores por similitud y se presentan **ordenados por tiempo**: el dato principal para el vecino es **dónde empieza** a tratarse su tema. El correo abre cada tema con «Se empieza a tratar en el minuto M:SS — ir a ese momento del vídeo» (el enlace lleva el parámetro de tiempo; si el pleno no guardó URL, se reconstruye de forma determinista a partir del identificador del vídeo).

# 5. El correo

Composición 100 % extractiva, sin modelo generativo: asunto con los temas y la fecha; por tema, el minuto de inicio y hasta 3 **citas literales** con su orador (y partido si consta); botón al **acta completa en PDF**; y pie con el enlace de **baja en un clic**. La variante *boletín* («todos los plenos») se envía con cada pleno nuevo e incluye un **índice compacto** de todos los temas del catálogo detectados (una cita por tema). La variante *bienvenida* llega al confirmar la suscripción, con lo último que se dijo de los temas del vecino en los plenos recientes (se escanean los 3 últimos).

# 6. Ciclo de suscripción

1. **Alta**: correo + municipio + temas del catálogo (la interfaz no admite texto libre). Se genera un token y un correo de confirmación.
2. **Doble confirmación (opt-in)**: solo el clic de confirmación activa la suscripción; solo la **primera** confirmación dispara la bienvenida (reabrir el enlace no reenvía).
3. **Avisos**: al terminar de procesarse un pleno del municipio, el sistema detecta temas y envía un correo por vecino, agrupando sus temas.
4. **Baja**: un clic desde cualquier correo (el token elimina las suscripciones).

**Antiduplicados**: el registro de envíos guarda (pleno, destinatario); regenerar un acta — p. ej. tras etiquetar voces — **no reenvía** correos, y la bienvenida cuenta como envío de su pleno. El backfill del histórico tampoco dispara alertas: solo los plenos que entran por el flujo normal.

# 7. Autopiloto: el vigilante del canal

Una tarea programada diaria (`scripts/vigilante_canal.py`) lista el canal de YouTube del ayuntamiento, detecta plenos **nuevos** (por título y contra los ya procesados), procesa como máximo uno por pasada y dispara las alertas al terminar. Ciclo completo sin intervención: *el pleno se publica por la noche; por la mañana, el vecino tiene el correo con el minuto exacto*.

# 8. Privacidad por diseño

- **Imposible suscribirse a personas**: el catálogo cerrado se valida en servidor; «Fulanito Pérez» se rechaza (verificado con test).
- Doble opt-in, baja en un clic, y el correo del vecino vive **solo** en la base de datos local del ayuntamiento.
- El contenido es literal y público (el pleno lo es); no se generan afirmaciones nuevas sobre nadie.

# 9. Almacenamiento

Dos tablas SQLite locales: `alerta_sub` (municipio, correo, tema, confirmado, token) y `alerta_envio` (el registro de correos: pleno, destinatario, temas, asunto, HTML, tipo — confirmación / bienvenida / aviso). Sin servidor de correo configurado, `alerta_envio` hace de **bandeja de demostración** visible en la pestaña; con tres variables de entorno (`PLENO_SMTP_HOST/PORT/FROM`) los envíos salen por SMTP real.

# 10. Evaluación

| Prueba | Resultado |
|---|---|
| Calibración del umbral (3 plenos reales, 15 temas) | verdaderos 0,57-0,64 · ruido ≤ 0,569 |
| Positivo verificado a mano | el 0,632 de «presupuestos» era un punto de Hacienda real (Agenda de Reconstrucción) |
| Validación extremo a extremo | suscripción → confirmación → pleno de Chiva → 1 aviso de *presupuestos* correcto y *vivienda* correctamente silenciada |
| Suscripción a una persona | rechazada («elige un tema del catálogo») |
| Doble clic en el enlace de confirmación | una sola bienvenida |
| Reprocesado del mismo pleno | 0 reenvíos (antiduplicados) |
| Vigilante (canal real, 99 plenos) | detecta correctamente el pleno nuevo más reciente |

# 11. Modelos y componentes

| Componente | Herramienta | Papel |
|---|---|---|
| Embeddings | BGE-M3 (d = 1024) | centroides de tema y fragmentos del pleno |
| Índice | ChromaDB local | reutilización de embeddings ya calculados |
| Suscripciones y envíos | SQLite local | doble opt-in, tokens, antiduplicados, bandeja demo |
| Autopiloto | yt-dlp + tarea programada | detección de plenos nuevos en el canal |
| Correo | HTML extractivo + SMTP opcional | citas + minuto + acta; sin LLM |

# 12. Resumen del flujo

1. El vecino elige temas del catálogo (o el boletín) y confirma por correo (doble opt-in).
2. El vigilante detecta el pleno nuevo y el pipeline lo procesa (transcripción → voces → acta).
3. Los fragmentos del pleno se comparan con los centroides de tema; dispara lo que supera 0,57 (y 120 caracteres).
4. Cada vecino recibe un único correo con sus temas: minuto de inicio enlazado, citas literales con orador y el acta en PDF.
5. Baja en un clic; regenerar el acta no reenvía nada.
