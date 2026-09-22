"""Ingesta del corpus de Diarios de Sesiones (carpeta de JSON) en SQLite + ChromaDB.

Dos fases independientes y reanudables:

  * SQL        : una fila por intervención  -> fichas/agregados EXACTOS al instante (sin GPU).
  * Embeddings : trocea e indexa en ChromaDB -> búsqueda semántica (la parte lenta).

El modelo de embeddings se carga UNA sola vez. Cada pleno se confirma por separado,
así que un proceso interrumpido se reanuda donde lo dejó (salta lo ya hecho).

Uso:
    python scripts/ingest_diarios.py --dir diarios_congreso_2016-2026
    python scripts/ingest_diarios.py --dir ... --sql-only     # solo agregados (rápido, sin GPU)
    python scripts/ingest_diarios.py --dir ... --embed-only   # solo indexar lo que falte
    python scripts/ingest_diarios.py --dir ... --reindex      # rehacer SQL y embeddings
    python scripts/ingest_diarios.py --dir ... --limit 20     # muestra para pruebas
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import diarios                 # noqa: E402
from src.config import load_config      # noqa: E402
from src.db import connect              # noqa: E402

try:
    from tqdm import tqdm
except ImportError:                     # progreso opcional
    def tqdm(it, **_):
        return it


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Ingesta del corpus de Diarios (JSON) -> SQLite + ChromaDB.")
    ap.add_argument("--dir", help="carpeta con los .json del corpus")
    ap.add_argument("--sql-only", action="store_true", help="solo agregados en SQLite (sin embeddings)")
    ap.add_argument("--embed-only", action="store_true", help="solo indexar en ChromaDB lo pendiente")
    ap.add_argument("--reindex", action="store_true", help="rehacer SQL y embeddings de cada pleno")
    ap.add_argument("--limit", type=int, default=0, help="procesar como mucho N archivos (pruebas)")
    ap.add_argument("--prune-stats", action="store_true",
                    help="muestra cuánto se podaría del índice por umbral (solo SQL, no indexa)")
    args = ap.parse_args()

    cfg = load_config()
    con = connect()
    diarios.ensure_schema(con)

    if args.prune_stats:
        skip_proc = getattr(cfg.chunking, "skip_procedural", True)
        base = diarios.prune_stats(con, 0, skip_proc)
        if not base["total_interv"]:
            raise SystemExit("No hay datos en SQL todavía. Ejecuta antes la fase --sql-only.")
        print(f"Total: {base['total_interv']:,} intervenciones · {base['total_words']:,} palabras")
        print(f"(skip_procedural={skip_proc})  umbral -> se podaría:")
        for mw in (0, 10, 15, 20, 30, 50):
            s = diarios.prune_stats(con, mw, skip_proc)
            pi = 100 * s["pruned_interv"] / base["total_interv"]
            pw = 100 * s["pruned_words"] / max(base["total_words"], 1)
            print(f"  min_words={mw:>3}:  -{s['pruned_interv']:>7,} interv ({pi:4.1f}%)  ·  "
                  f"-{s['pruned_words']:>10,} palabras ≈ índice ({pw:4.1f}%)")
        con.close()
        return

    do_sql = not args.embed_only
    do_embed = not args.sql_only

    if not args.dir:
        raise SystemExit("Falta --dir (carpeta con los .json).")
    folder = Path(args.dir)
    if not folder.is_absolute():
        folder = Path.cwd() / folder
    files = sorted(folder.glob("*.json"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        raise SystemExit(f"No se encontraron .json en {folder}")

    embedder = collection = None
    if do_embed:
        from src.index import get_embedder
        embedder = get_embedder(cfg)                 # carga única del modelo
        collection = diarios.get_corpus_collection(cfg)

    n_sql = n_chunks = procesados = saltados = errores = 0
    for path in tqdm(files, desc="plenos", unit="pleno"):
        try:
            d = diarios.load_diario(path)
        except Exception as exc:                     # JSON corrupto: avisa y sigue
            errores += 1
            print(f"[error] {path.name}: {str(exc)[:80]}")
            continue

        in_sql, in_chroma = diarios.is_ingested(con, d.pleno_id)
        trabajo = False

        if do_sql and (args.reindex or not in_sql):
            if args.reindex:
                diarios.clear_pleno(con, d.pleno_id)
            n_sql += diarios.ingest_sql(con, d)
            in_sql, in_chroma, trabajo = True, False, True

        if do_embed and (args.reindex or not in_chroma):
            if not in_sql:                           # asegura la fila + el flag
                diarios.ingest_sql(con, d)
            n_chunks += diarios.ingest_chroma(con, cfg, d, embedder, collection)
            trabajo = True

        procesados += trabajo
        saltados += not trabajo

    con.close()
    print(f"\nListo · {len(files)} archivos · {procesados} procesados · {saltados} ya estaban "
          f"· {errores} con error\n"
          f"       {n_sql:,} intervenciones en SQL · {n_chunks:,} fragmentos indexados")


if __name__ == "__main__":
    main()
