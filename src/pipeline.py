"""Pipeline completo sobre UNA sesión plenaria (orquesta A + B + C).

De una URL de YouTube (o un PDF de Diario) -> Diario oficial -> intervenciones
con orador + partido -> índice vectorial -> búsqueda semántica + resumen.

Uso:
    python -m src.pipeline "https://www.youtube.com/watch?v=XXXX"
    python -m src.pipeline --pdf data/diarios/DSCD-15-PL-109.pdf
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config, resolve_path
from .diario import (attach_parties, diario_url_from_youtube, download_diario,
                     extract_text, parse_interventions, to_transcript)
from .index import index_transcript
from .search import search
from .summarize import summarize_text


def _h(title: str) -> None:
    print("\n" + "=" * 64 + f"\n{title}\n" + "=" * 64)


def run(source: str, is_pdf: bool, query: str, cfg=None) -> None:
    cfg = cfg or load_config()

    _h("BLOQUE A — Texto oficial (Diario de Sesiones)")
    if is_pdf:
        pdf = Path(source)
        print(f"PDF local: {pdf}")
    else:
        print(f"YouTube: {source}")
        durl = diario_url_from_youtube(source)
        if not durl:
            raise SystemExit("No encontré el enlace al Diario en la descripción del vídeo.")
        print(f"Diario (de la descripción): {durl}")
        pdf = download_diario(durl, resolve_path("data/diarios"))
        print(f"Descargado: {pdf}")

    _h("BLOQUE A+B — Intervenciones con orador y partido")
    text = extract_text(pdf)
    ints = attach_parties(parse_interventions(text), text)
    by_party: dict[str, int] = {}
    for it in ints:
        k = it["party"] or "—"
        by_party[k] = by_party.get(k, 0) + 1
    print(f"{len(ints)} intervenciones · {len({i['speaker'] for i in ints})} oradores distintos")
    print("Reparto por partido:",
          ", ".join(f"{k}={v}" for k, v in sorted(by_party.items(), key=lambda x: -x[1])))

    _h("BLOQUE C — Indexado (embeddings + ChromaDB)")
    stem = pdf.stem
    tr_dir = resolve_path(cfg.paths.transcripts)
    tr_dir.mkdir(parents=True, exist_ok=True)
    tr_path = tr_dir / f"{stem}.json"
    tr_path.write_text(json.dumps(to_transcript(ints, source=stem), ensure_ascii=False, indent=2),
                       encoding="utf-8")
    index_transcript(tr_path, {"id": stem, "title": f"Diario {stem}", "url": ""}, cfg)

    _h(f"BLOQUE C — Búsqueda semántica: «{query}»")
    for i, h in enumerate(search(query, cfg, final_k=3), 1):
        who = (h["meta"].get("speaker") or "?").strip()
        print(f"\n#{i}  {who}\n    {h['text'][:240].strip()}…")

    if getattr(cfg.llm, "enabled", False):
        _h("BLOQUE C — Resumen de la sesión (LLM local)")
        print(summarize_text(text[:8000], cfg))


def main() -> None:
    ap = argparse.ArgumentParser(description="Pipeline completo sobre una sesión plenaria.")
    ap.add_argument("source", nargs="?", help="URL de YouTube del pleno")
    ap.add_argument("--pdf", help="o un PDF de Diario ya descargado")
    ap.add_argument("-q", "--query", default="¿qué se debatió sobre los presupuestos y los impuestos?")
    args = ap.parse_args()
    if not args.source and not args.pdf:
        ap.error("da una URL de YouTube o --pdf")
    run(args.pdf or args.source, is_pdf=bool(args.pdf), query=args.query)


if __name__ == "__main__":
    main()
