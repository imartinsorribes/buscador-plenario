"""Indexa en ChromaDB TODOS los Diarios de Sesiones descargados (corpus del Congreso).

Cada pleno: PDF -> intervenciones con orador/partido OFICIAL (src.diario) -> ChromaDB.
No usa NER ni vídeo: es texto oficial, base del buscador masivo / estudio de la legislatura.
Salta los que ya estén indexados. Registra cada pleno en la BD (src.db).

Uso:  python scripts/index_corpus.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import db  # noqa: E402
from src.config import load_config, resolve_path  # noqa: E402
from src.diario import (attach_parties, extract_text, parse_interventions,  # noqa: E402
                        session_date, to_transcript)
from src.index import get_collection, index_transcript  # noqa: E402


def main() -> None:
    cfg = load_config()
    try:
        cfg.embeddings.batch_size = 16   # solo BGE-M3 en VRAM -> cabe un batch mayor (más rápido)
    except Exception:
        pass

    col = get_collection(cfg)
    indexados = set()
    got = col.get(include=["metadatas"])
    for m in got.get("metadatas", []) or []:
        if m.get("video_id"):
            indexados.add(m["video_id"])

    con = db.connect()
    eid = db.upsert_entidad(con, "congreso", "Congreso de los Diputados", "congreso")
    trdir = resolve_path("data/transcripts"); trdir.mkdir(parents=True, exist_ok=True)
    base = resolve_path("data/diarios")
    pdfs = sorted(set(list(base.glob("DSCD-15-PL-*.PDF")) + list(base.glob("DSCD-15-PL-*.pdf"))))

    done = 0
    for p in pdfs:
        stem = p.stem
        if stem in indexados:
            continue
        try:
            txt = extract_text(p)
            ints = attach_parties(parse_interventions(txt), txt)
            tr = to_transcript(ints, source=stem)
            if not tr["segments"]:
                print("vacío", stem); continue
            fecha = session_date(txt)
            path = trdir / f"{stem}.json"
            path.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
            n = index_transcript(path, {"id": stem, "title": f"{stem}" + (f" — {fecha}" if fecha else ""), "url": ""}, cfg)
            db.register_pleno(con, eid, stem, titulo=stem, fecha=fecha)
            done += 1
            print(f"[{done}] {stem}: {n} fragmentos · {fecha}")
        except Exception as e:
            print("ERR", stem, str(e)[:70])
    con.close()
    print(f"\nCORPUS INDEXADO: {done} plenos nuevos")


if __name__ == "__main__":
    main()
