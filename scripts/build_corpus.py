"""Construye el corpus multi-pleno: descarga e indexa varios Diarios de Sesiones.

Todos los plenos caen en el MISMO ChromaDB, así que la búsqueda es sobre todos.
El modelo de embeddings se carga una sola vez (bucle en un solo proceso).

Uso:
    python scripts/build_corpus.py --leg 15 --desde 100 --hasta 114
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config, resolve_path  # noqa: E402
from src.diario import (attach_parties, download_diario, extract_text,  # noqa: E402
                        parse_interventions, session_date, to_transcript)
from src.index import index_transcript  # noqa: E402

URL = "https://www.congreso.es/public_oficiales/L{leg}/CONG/DS/PL/DSCD-{leg}-PL-{n}.PDF"


def main() -> None:
    ap = argparse.ArgumentParser(description="Descarga e indexa un rango de Diarios.")
    ap.add_argument("--leg", type=int, default=15)
    ap.add_argument("--desde", type=int, required=True)
    ap.add_argument("--hasta", type=int, required=True)
    args = ap.parse_args()

    cfg = load_config()
    diarios = resolve_path("data/diarios")
    tr_dir = resolve_path(cfg.paths.transcripts)
    tr_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for n in range(args.desde, args.hasta + 1):
        url = URL.format(leg=args.leg, n=n)
        try:
            pdf = download_diario(url, diarios)
        except Exception:
            print(f"PL-{n}: no disponible (404/erro)")
            continue
        text = extract_text(pdf)
        ints = attach_parties(parse_interventions(text), text)
        if not ints:
            print(f"PL-{n}: sin intervenciones")
            continue
        stem = pdf.stem
        date = session_date(text)
        tr_path = tr_dir / f"{stem}.json"
        tr_path.write_text(json.dumps(to_transcript(ints, source=stem), ensure_ascii=False, indent=2),
                           encoding="utf-8")
        n_idx = index_transcript(tr_path, {"id": stem, "title": f"{stem} · {date}", "url": ""}, cfg)
        print(f"PL-{n}: {len(ints)} intervenciones -> {n_idx} fragmentos  [{date}]")
        ok += 1

    print(f"\nCorpus listo: {ok} plenos indexados en ChromaDB.")


if __name__ == "__main__":
    main()
