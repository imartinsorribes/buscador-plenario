"""Bloque C (3/3): búsqueda semántica sobre los plenos indexados.

Búsqueda EXTRACTIVA: devuelve la cita literal del fragmento más relevante, su
orador (si el Bloque B ya lo añadió) y el enlace a YouTube en el minuto exacto.
No genera texto -> sin riesgo de poner palabras en boca de nadie.

Uso:
    python -m src.search "¿qué se debatió sobre vivienda?"
"""
from __future__ import annotations

import argparse

from .config import load_config
from .index import get_collection, get_embedder


def _hms(t) -> str:
    t = int(t or 0)
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def search(query: str, cfg=None, final_k: int | None = None, video: str | None = None) -> list[dict]:
    cfg = cfg or load_config()
    final_k = final_k or getattr(cfg.retrieval, "final_k", 5)
    top_k = getattr(cfg.retrieval, "top_k", 20)

    q_emb = get_embedder(cfg).encode([query], normalize_embeddings=True)[0].tolist()
    where = {"video_id": video} if video else None
    res = get_collection(cfg).query(query_embeddings=[q_emb], n_results=top_k, where=where)

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res.get("distances", [[None] * len(docs)])[0]
    hits = [{"text": d, "meta": m, "distance": dist}
            for d, m, dist in zip(docs, metas, dists)]

    # Reranking opcional (cross-encoder) para subir la precisión del top.
    if getattr(cfg, "reranker", None) and getattr(cfg.reranker, "enabled", False) and hits:
        try:
            ce = _get_reranker(cfg)
            scores = ce.predict([(query, h["text"]) for h in hits])
            for h, s in zip(hits, scores):
                h["rerank"] = float(s)
            hits.sort(key=lambda h: h["rerank"], reverse=True)
        except Exception as e:
            # Sin reranker seguimos devolviendo el orden del embedding: resultados
            # algo menos finos pero la búsqueda nunca se queda colgada.
            print(f"[search] reranker no disponible ({type(e).__name__}: {e}); orden por embedding")

    return hits[:final_k]


_RERANKER = {}


def _get_reranker(cfg):
    """CrossEncoder cacheado a nivel de módulo: cargarlo por consulta costaba segundos
    y, con la VRAM llena, Windows lo desborda a memoria compartida y la petición se
    eterniza sin dar error. `reranker.device: cpu` en config.yaml lo saca de la GPU."""
    key = cfg.reranker.model
    if key not in _RERANKER:
        from sentence_transformers import CrossEncoder
        device = getattr(cfg.reranker, "device", None) or cfg.embeddings.device
        _RERANKER[key] = CrossEncoder(key, device=device, max_length=512)
    return _RERANKER[key]


def main() -> None:
    ap = argparse.ArgumentParser(description="Bloque C — búsqueda semántica en los plenos.")
    ap.add_argument("query", help="Pregunta o tema, p.ej. '¿qué se dijo sobre vivienda?'")
    ap.add_argument("-k", type=int, default=None, help="nº de resultados")
    ap.add_argument("--video", default=None, help="filtrar por id de pleno (video_id)")
    args = ap.parse_args()

    cfg = load_config()
    results = search(args.query, cfg, final_k=args.k, video=args.video)
    if not results:
        print("Sin resultados. ¿Has indexado algún pleno? (python -m src.process_audio ...)")
        return
    for i, h in enumerate(results, 1):
        m = h["meta"]
        who = (m.get("speaker") or "").strip() or "orador sin identificar"
        pleno = (m.get("title") or m.get("video_id") or "").strip()
        print(f"\n#{i}  {who}  —  {pleno}")
        if m.get("youtube_link"):
            print(f"     ▶ {m['youtube_link']}")
        print(f"     {h['text'][:400]}")


if __name__ == "__main__":
    main()
