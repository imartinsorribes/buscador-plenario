# Estudio de costes por modelo y despliegue

Reto 2 · julio de 2026. Precios de API tomados **en vivo del catálogo de OpenRouter** (julio 2026) y tarifa publicada de la API de Whisper; el resto, medido en nuestro sistema. Conversión aplicada en los totales: 1 $ ≈ 0,92 €. Se marca claramente qué es medido, qué es tarifa oficial y qué es estimación.

# 1. Supuestos de carga (municipio tipo)

| Magnitud | Valor | Origen |
|---|---|---|
| Plenos al año | 24 (12 ordinarios + extraordinarios) | estimación conservadora |
| Duración por pleno | 3 h (180 min) | típico medido |
| Transcript por pleno | ≈ 45.000 tokens | medido (≈30.000 palabras) |
| Trabajo LLM por pleno (extracción, temas) | ≈ 50.000 tokens entrada · 8.000 salida | medido en nuestro pipeline |
| Consultas al asistente de manuales | 500/mes → 6.000/año | estimación |
| Por consulta de manuales | ≈ 6.000 tokens entrada · 600 salida | medido (k=8 fragmentos) |
| Capturas de manuales (visión, una única vez) | 330 imágenes hoy | medido |

# 2. Tarifas actuales (julio 2026)

| Modelo (API) | $/M tokens entrada | $/M salida | Nota |
|---|---|---|---|
| gpt-4o-mini | 0,15 | 0,60 | gama económica |
| mistral-small-3.2-24b (alojado) | 0,075 | 0,20 | el más barato del catálogo |
| qwen-2.5-72b (alojado) | 0,36 | 0,40 | pariente grande de nuestro modelo local |
| claude-haiku-4.5 | 1,00 | 5,00 | gama media |
| gemini-3.5-flash | 1,50 | 9,00 | el que usamos para VISIÓN |
| claude-sonnet-5 | 2,00 | 10,00 | gama alta |
| gpt-5.2 | 1,75 | 14,00 | gama alta |
| **ASR en nube (API Whisper)** | **0,006 $/minuto de audio** | | la partida dominante |

# 3. Coste por pleno si todo fuera a la nube

- **Transcripción**: 180 min × 0,006 $ = **1,08 $ por pleno** — es la partida que manda, con cualquier LLM.
- **Trabajo LLM del pleno** (50k entrada + 8k salida): de **0,005 $** (mistral-small alojado) a **0,20 $** (gpt-5.2); gama media (haiku-4.5) ≈ 0,09 $.
- **Total por pleno en nube: ≈ 1,1-1,3 $.**

# 4. Coste por consulta del asistente de manuales

| Vía | Coste por consulta |
|---|---|
| Local (qwen 3b/7b/14b) — nuestra elección | **0 €** |
| gpt-4o-mini | ≈ 0,0013 $ |
| claude-haiku-4.5 | ≈ 0,009 $ |
| gemini-3.5-flash | ≈ 0,014 $ |
| claude-sonnet-5 / gpt-5.2 | ≈ 0,018-0,02 $ |

# 5. La visión (lo único que sí compramos)

Descripción de capturas con gemini-3.5-flash: ≈ **0,45 céntimos de dólar por imagen** (≈1.200 tokens de imagen+prompt y 300 de salida). Nuestra ingesta completa (330 capturas) costó **≈ 1,5 $ en total, una sola vez** — la caché por hash garantiza que ninguna imagen se paga dos veces. Un manual nuevo típico (~25 capturas) ≈ 0,11 $. Un pantallazo de usuario: 0,45 c$ la primera vez, gratis después.

# 6. Comparación anual (municipio tipo: 24 plenos + 6.000 consultas)

| Despliegue | Año 1 | Años siguientes | Notas |
|---|---|---|---|
| **Todo local (nuestra elección)** | ≈ 300-450 € de GPU (una vez, si no hay equipo) + ~2 € de luz + 1,5 $ de visión inicial | **≈ 2 €/año** (luz) + céntimos por manual nuevo | datos sin salir del ayuntamiento |
| Todo nube, gama económica (4o-mini) | ≈ 34 $/año | ≈ 34 $/año | ASR domina (26 $); el dato viaja fuera |
| Todo nube, gama media (haiku-4.5) | ≈ 82 $/año | ≈ 82 $/año | |
| Todo nube, gama alta (sonnet-5 / gpt-5.2) | ≈ 140 $/año | ≈ 140 $/año | |
| Videoacta comercial (referencia de mercado) | licencias anuales de 4 cifras | ídem | estimación de mercado, por sesión o anualidad |

**A escala de 100 municipios**: la nube crece lineal (≈ 3.400-14.000 $/año); el despliegue local no (cada consistorio corre lo suyo, coste marginal ~0).

# 7. Lectura honesta

Para **un** municipio, la nube no es cara (~30-140 $/año). La elección local no se justifica solo por dinero, sino por cuatro razones en este orden:

1. **Soberanía del dato (RGPD)**: el audio y las actas del pleno — con nombres de vecinos en ruegos y preguntas — no salen del equipo del ayuntamiento. Es la razón principal.
2. **Independencia**: sin dependencia de tarifas que cambian, cuotas, ni conexión a internet en el salón de plenos.
3. **Escala**: el modelo de producto es para muchos municipios; el coste nube escala lineal, el local es plano.
4. **Coste plano y previsible**: un ayuntamiento presupuesta una vez (hardware, si no lo tiene) y opera a coste cero — sin sorpresas por picos de uso.

La nube queda para lo único donde aporta algo que lo local no tiene: **visión** (describir capturas) — y ahí, con caché por hash, cada imagen se paga una única vez en la vida del sistema.

# 8. Dónde encaja el selector borroso

Estas cifras son las **entradas económicas** del selector de modelo (memoria técnica, §10): presupuesto y sensibilidad del dato se fuzzifican junto a la VRAM y la exigencia de calidad, y el sistema recomienda el despliegue idóneo por municipio — incluida la degradación automática al modelo local si el remoto no responde.
