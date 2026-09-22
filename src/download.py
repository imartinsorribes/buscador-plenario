"""Bloque A (1/2): descarga el audio de un vídeo de YouTube con yt-dlp.

YouTube (2026) exige un runtime JS (Deno/Node) + el solucionador EJS para resolver
el 'nsig'; sin eso estrangula la descarga a 0 bytes. Por eso invocamos la CLI de
yt-dlp con `--remote-components ejs:github` y un formato de audio directo (m4a 140).

Requisitos en PATH (instalados con winget): **deno** y **ffmpeg**. yt-dlp va en el venv.
Para tramos (`clip`) usa el descargador ffmpeg, que hace seeking remoto fiable.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def download_audio(url: str, out_dir, clip: str | None = None,
                   audio_format: str = "140/bestaudio[ext=m4a]/bestaudio",
                   cookies_from_browser: str | None = None,
                   cookies_file: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--remote-components", "ejs:github",   # baja el solucionador del nsig de YouTube
        "--no-playlist",
        "-f", audio_format,
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        "--write-info-json",
        "--newline",   # progreso en líneas nuevas -> visible en el terminal
    ]
    # Cookies para sortear el anti-bot / estrangulamiento de YouTube
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    elif cookies_file:
        cmd += ["--cookies", cookies_file]
    if clip:  # p.ej. clip="2:00-5:00" -> descarga solo ese tramo vía ffmpeg
        cmd += ["--download-sections", f"*{clip}", "--downloader", "ffmpeg"]
    cmd.append(url)

    # NO capturamos la salida: así se ve el progreso de yt-dlp en vivo.
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(
            "yt-dlp no pudo descargar (revisa la salida de arriba). "
            "¿Están 'deno' y 'ffmpeg' en el PATH y hay acceso a YouTube?"
        )

    # yt-dlp deja <id>.info.json + el audio <id>.<ext>
    info_jsons = sorted(out_dir.glob("*.info.json"), key=lambda p: p.stat().st_mtime)
    if not info_jsons:
        raise RuntimeError("Descarga sin .info.json: algo falló en yt-dlp.\n" + res.stdout[-800:])
    info = json.loads(info_jsons[-1].read_text(encoding="utf-8"))
    vid = info["id"]
    audio = next((p for p in out_dir.glob(f"{vid}.*") if p.suffix != ".json"), None)
    if audio is None:
        raise RuntimeError(f"No se encontró el audio descargado para {vid}.")

    return {
        "id": vid,
        "title": info.get("title"),
        "url": info.get("webpage_url", url),
        "duration": info.get("duration"),
        "audio_path": str(audio),
    }
