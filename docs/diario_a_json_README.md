# Diario de Sesiones (PDF) → JSON + búsqueda inteligente

Script para **probar plenos nuevos**: convierte el PDF del Diario de Sesiones en un JSON
estructurado y lo deja **indexado en la búsqueda semántica**. Pensado para correr de uno
en uno (no es el pipeline de lote de los 667 plenos).

`scripts/diario_a_json.py`

## Cómo se usa

Desde la raíz del repo, con el entorno del proyecto (`.venv`):

```bash
# un pleno ya descargado → JSON del corpus + indexarlo en la búsqueda
.venv\Scripts\python.exe scripts\diario_a_json.py data\diarios\DSCD-15-PL-50.pdf

# varios PDFs, o una carpeta entera con PDFs dentro
.venv\Scripts\python.exe scripts\diario_a_json.py mis_plenos\

# solo el JSON, sin tocar la búsqueda (no carga el modelo de embeddings → es instantáneo)
.venv\Scripts\python.exe scripts\diario_a_json.py mi_pleno.pdf --no-index

# bajar el Diario directamente desde el vídeo de YouTube del pleno
.venv\Scripts\python.exe scripts\diario_a_json.py --from-youtube https://www.youtube.com/watch?v=XXXX
```

Salidas:
- **JSON del corpus** → `data/diarios_json/<ID>.json` (cambia con `--out`).
- **Índice de búsqueda** → ChromaDB (colección `plenos`); ya queda buscable. Reindexar el
  mismo pleno es idempotente (borra los fragmentos viejos antes de volver a meterlos).

## Esquema del JSON

```jsonc
{
  "id": "DSCD-15-PL-50",
  "legislatura": 15,
  "fecha": "28 de noviembre de 2023",
  "tema_sesion": "…orden del día de la cabecera…",
  "votaciones": [ { "emitidos": 342, "a_favor": 311, "en_contra": 31, "abstenciones": null }, … ],
  "n_intervenciones": 46,
  "interventions": [
    { "speaker": "MONTESINOS DE MIGUEL", "party": "PP",
      "role": "diputado", "topic": "…punto del orden del día…", "text": "…" }
  ]
}
```

Reglas del modelo (importante):
- `party` = **siempre** una sigla (`PP`/`PSOE`/`VOX`/`Cs`/`Podemos`/`Sumar`/`ERC`/`Junts`/
  `EH Bildu`/`PNV`/`CC`/`Plural`/`Mixto`/`DL`) o `""`. **Nunca** "Gobierno"/"Presidencia":
  eso es la función y va en `role`.
- `role` = `diputado | candidato | presidente del gobierno | vicepresidente del gobierno |
  ministro | secretario de estado | presidencia | representante autonómico | otros`.

## De dónde sale el partido (por fiabilidad)

1. Corrección manual → `data/party_overrides.csv` (columnas `speaker`, `party_correcto`,
   y opcional `legislatura`). Tiene prioridad sobre todo.
2. Sumario del propio Diario (empareja "señor X, del Grupo Y").
3. Registro oficial → `data/registro_diputados.json` (roster por legislatura).
4. Si nada de lo anterior lo resuelve → `""` (nunca se adivina).

**Caveat con plenos sueltos:** a diferencia del corpus completo (que cruzó los 667 PDFs),
un pleno nuevo solo dispone de su propio sumario + el registro. Si un orador no aparece en
ninguno, su `party` quedará `""`. Para fijarlo, añade una línea en `party_overrides.csv` y
vuelve a correr el script. (En una prueba con DSCD-15-PL-10 quedaron 44/46 oradores con
partido; 2 en blanco — nunca uno mal.)

## Requisitos

- PDF con **texto** (los Diarios del Congreso lo traen). Un PDF escaneado sin OCR daría 0
  intervenciones → el script lo avisa y lo salta.
- Para `--from-youtube`: `yt-dlp` + Deno (ya en el entorno).
- Para indexar: el modelo de embeddings (BGE-M3) ya está en el proyecto; con `--no-index`
  no hace falta.
