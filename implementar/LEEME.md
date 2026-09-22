# El Congreso, en Datos 2016-2026 — app_completa

Web autónoma e interactiva con 4 gráficas sobre 10 temas y 3 legislaturas (XII, XIV, XV):
1. **Mapa de calor** — posición de cada partido por tema.
2. **Índice de contradicción** — estabilidad/ambigüedad del voto.
3. **Agenda parlamentaria (sismógrafo + radar)** — de qué hablan.
4. **Calculadora de afinidad** — afinidad del usuario con cada partido.

Las **posiciones** se basan en los **votos nominales oficiales del Congreso** (Datos Abiertos), agregados por
grupo y clasificados por tema. El **sismógrafo** se basa en los **diarios de sesiones** (discursos).

## Cómo usarla
1. **Mantén los dos archivos JUNTOS en la misma carpeta**: `index.html` y `plotly.min.js`.
2. Abre **`index.html`** en el navegador (doble clic), o sírvela con cualquier servidor estático.

No hay nada que instalar: los datos van **embebidos** dentro de `index.html` y todas las referencias son
**relativas**. Por eso **funciona en cualquier ordenador y en cualquier ruta** (no depende de rutas absolutas
ni de dónde esté la carpeta).

> Nota: al abrir el archivo puede tardar 1-2 s en pintar (carga `plotly.min.js`, 4,4 MB). Es normal.

## Integrarla en vuestra app
Es una página estática autocontenida. Opciones:
- **Servir la carpeta** como recurso estático y enlazar a `index.html`, o
- **Incrustarla** con un iframe:
  `<iframe src="ruta/app_completa/index.html" style="width:100%;height:100vh;border:0"></iframe>`

Único requisito: que `plotly.min.js` quede junto a `index.html`.

## Si hay que regenerar con datos nuevos (opcional)
No es necesario para que funcione (los datos ya están dentro del HTML). Para reconstruirla hacen falta, de David:
`crear_app_completa.py`, `votos_oficial.json`, `construir_votos.py`, `download_votos.ps1`, la carpeta
`diarios_congreso_2016-2026/` y `plotly.min.js`. Comando: `python crear_app_completa.py`.
