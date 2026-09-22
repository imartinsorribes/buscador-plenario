# Buscador Plenario Inteligente

Convierte el vídeo de un pleno en un **buscador semántico**: escribes una idea, te lleva
al **minuto exacto** del vídeo, te dice **quién lo dijo y de qué grupo**, y enlaza la cita.
Funciona **aunque no exista Diario de Sesiones oficial** — pensado para que **ayuntamientos**
de toda España hagan buscables sus plenos sin pagar transcripciones caras.

Modelos **locales** (pensado para una RTX 3050 de 4 GB). El Congreso es el caso de arranque;
el motor es genérico para cualquier órgano deliberativo.

---

## Arquitectura (4 bloques + base de datos)

| Bloque | Qué hace | Módulo |
|---|---|---|
| **A** Transcripción | YouTube → audio → texto con timestamps (faster-whisper) | `src/download.py`, `src/transcribe.py`, `src/process_audio.py` |
| **B** Quién dijo qué | Diariza (pyannote) y **nombra** a cada orador con NER + embeddings + roster/Diario, **sin regex** | `src/diarize.py`, `src/speakers.py` |
| **C** Búsqueda | Trocea, embeddings (BGE-M3) en ChromaDB, búsqueda + reranker, deep-link al minuto | `src/index.py`, `src/search.py` |
| **D** Interfaz | Web sobria (FastAPI + Tailwind) con reproductor que salta al minuto | `app/server.py`, `app/index.html` |
| **BD** | Entidad → roster → plenos (SQLite). Permite nombrar oradores sin Diario | `src/db.py` |

Fuentes de roster (de más a menos automática): **Diario oficial** (`scripts/build_roster.py`),
**CSV** de concejales (`db.roster_from_csv`), **bootstrap del NER** + confirmación
(`db.roster_bootstrap_from_transcript`).

Validación del ASR (`scripts/validate_transcription.py`): contra el acta oficial mide recall de
contenido y similitud semántica; sin acta, la confianza sale del `avg_logprob` de Whisper.

---

## Instalación (Windows + GPU NVIDIA)

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1

# 1) PyTorch con CUDA PRIMERO (no desde requirements):
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
# 2) El resto (versiones FIJADAS a propósito; ver nota abajo):
pip install -r requirements.txt
# 3) Herramientas externas:
winget install Gyan.FFmpeg DenoLand.Deno     # deno = resolver el nsig de YouTube
# 4) (Opcional) Ollama para resúmenes:  https://ollama.com  + `ollama pull qwen2.5:3b`
```

Para la **diarización** (Bloque B): crea `.env` con `HF_TOKEN=hf_xxx` y acepta las
condiciones de `pyannote/speaker-diarization-3.1` y `pyannote/segmentation-3.0` en HuggingFace
(con la misma cuenta del token).

> **Nota de versiones:** instala torch ANTES y respeta los pines de `requirements.txt`.
> Instalar pyannote/transformers sin pines arrastra majors nuevas (huggingface_hub 1.x,
> transformers 5.x, sentence-transformers 5.x) que **rompen la GPU** y la importación.

---

## Procesar un pleno

```powershell
# A) descargar + transcribir + indexar
python -m src.process_audio "https://www.youtube.com/live/<ID>" --index

# B) diarizar (necesita WAV 16 kHz mono):
ffmpeg -y -i data\raw_audio\<ID>.m4a -ac 1 -ar 16000 data\raw_audio\<ID>.wav
python -m src.diarize data\transcripts\<ID>.json data\raw_audio\<ID>.wav

# B) nombrar oradores  (--diario opcional: alinea por orden con el acta oficial)
python -m src.speakers data\transcripts\<ID>.json --roster data\roster.json --diario data\diarios\<DSCD>.PDF

# (Congreso) construir el roster desde los Diarios ya descargados, e iniciar la BD:
python scripts\build_roster.py
python -m src.db
```

## Arrancar la app

```powershell
python -m app.server        # -> http://127.0.0.1:8000
```

Búsqueda por línea de comandos: `python -m src.search "subida de las pensiones"`

---

## Dar de alta un AYUNTAMIENTO (sin Diario)

1. Roster de concejales: CSV con cabecera `nombre,grupo,cargo` →
   `db.roster_from_csv(...)` + `db.set_roster(con, entidad_id, rows, fuente="csv")`.
   *O* arranque en frío: procesa el primer pleno y usa `db.roster_bootstrap_from_transcript`
   para que el NER proponga los oradores y el usuario confirme.
2. `process_audio` del vídeo → diarizar → `speakers --roster <roster_del_ayto>` (sin `--diario`).
3. La búsqueda ya devuelve orador + minuto, sin necesidad de acta oficial.

El reproductor embebido funciona con vídeos que permitan incrustación; si no (p. ej. los del
Congreso, error 153), cae automáticamente al **enlace directo a YouTube en el minuto exacto**.

---

## Reparto sugerido (4 personas)
- **A** Transcripción + validador del ASR · **B** Diarización + NER/roster ·
  **C** Búsqueda/RAG + reranker · **D** Interfaz + base de datos por entidad.

## Limitaciones conocidas
- Sin Diario, los nombres salen como los escribe Whisper hasta cargar un roster.
- Ministros pueden aparecer como "Gobierno" (cargo, no apellido).
- El reranker y BGE-M3 caben juntos en 4 GB; la 1ª búsqueda tarda ~15 s en cargar modelos.
