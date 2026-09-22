"""Bloque A end-to-end: URL de YouTube -> audio -> transcripción (JSON + SRT).

Uso:
    python -m src.process_audio "https://www.youtube.com/watch?v=XXXX"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config, resolve_path
from .download import download_audio
from .transcribe import transcribe


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Bloque A — transcribe un audio (URL de YouTube o archivo local)."
    )
    ap.add_argument("source", help="URL de YouTube o ruta a un archivo de audio/vídeo local.")
    ap.add_argument("--clip", default=None,
                    help="Transcribir solo un tramo, p.ej. --clip 0:00-3:00 (rápido para pruebas).")
    ap.add_argument("--index", action="store_true",
                    help="Tras transcribir, trocear + embeddings + indexar en ChromaDB (Bloque C).")
    ap.add_argument("--minutes", type=float, default=None,
                    help="Transcribir solo los primeros N minutos (descarga completa + recorte local).")
    args = ap.parse_args()

    cfg = load_config()
    raw_dir = resolve_path(cfg.paths.raw_audio)
    tr_dir = resolve_path(cfg.paths.transcripts)

    src = args.source
    local = Path(src)
    if local.exists():  # archivo local -> saltamos la descarga de YouTube
        local = local.resolve()
        meta = {"id": local.stem, "title": local.stem, "url": "",
                "duration": None, "audio_path": str(local)}
        print(f"[1/2] Archivo local: {local}")
    else:
        dl = getattr(cfg, "download", None)
        print(f"[1/2] Descargando audio de: {src}")
        meta = download_audio(
            src, raw_dir, clip=args.clip,
            cookies_from_browser=(getattr(dl, "cookies_from_browser", None) if dl else None),
            cookies_file=(getattr(dl, "cookies_file", None) if dl else None),
        )
        print(f"      -> {meta['title']}  ({meta['duration']} s)\n         {meta['audio_path']}")

    if args.minutes:
        import subprocess
        clip_path = f"{Path(meta['audio_path']).with_suffix('')}_first{int(args.minutes)}min.wav"
        print(f"[~] Recortando primeros {args.minutes} min...")
        subprocess.run(["ffmpeg", "-y", "-i", meta["audio_path"], "-t", str(int(args.minutes * 60)),
                        "-ac", "1", "-ar", "16000", clip_path], check=True, capture_output=True)
        meta["audio_path"] = clip_path

    print("[2/2] Transcribiendo con faster-whisper...")
    transcribe(meta["audio_path"], cfg, tr_dir)

    if args.index:
        from .index import index_transcript
        tr_path = tr_dir / f"{Path(meta['audio_path']).stem}.json"
        print("[+] Indexando (trocear + embeddings + ChromaDB)...")
        index_transcript(tr_path, meta, cfg)


if __name__ == "__main__":
    main()
