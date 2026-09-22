"""Bloque C (temática): descubre los temas de los plenos con BERTopic.

Reutiliza los embeddings ya guardados en ChromaDB (no recalcula) y agrupa los
fragmentos en temas, etiquetándolos con palabras clave (c-TF-IDF). No necesita
LLM: los temas salen del clustering. El LLM solo entra después para ponerles
un nombre legible si se quiere.

Uso:
    python -m src.topics                 # temas de todo lo indexado
    python -m src.topics --video-id XXX  # temas de un pleno concreto
"""
from __future__ import annotations

import argparse

import numpy as np

from .config import load_config
from .index import get_collection

# Stopwords en español para que las palabras clave de cada tema sean informativas
# (incluye muletillas del hemiciclo: "señoría", "presidente", "grupo"...).
_SPANISH_STOPWORDS = (
    "a al algo algunas algunos ante antes asi como con contra cual cuando de del desde donde "
    "durante e el ella ellas ellos en entre era eran es esa esas ese eso esos esta estas este "
    "esto estos fue fueron ha haber habia han hasta hay la las le les lo los mas me mi mis "
    "mucho muy nada ni no nos nuestra nuestro o os otra otro para pero poco por porque pues que "
    "quien se senor senora senoria senorias sea ser si sin sobre solo son su sus tambien tan "
    "tanto te tiene todo todos tu tus un una uno unos usted ustedes y ya gracias presidente "
    "presidenta diputado diputada grupo parlamentario palabra usia"
).split()


def discover_topics(cfg=None, video_id: str | None = None, min_topic_size: int = 5):
    cfg = cfg or load_config()
    col = get_collection(cfg)
    where = {"video_id": video_id} if video_id else None
    data = col.get(where=where, include=["documents", "embeddings", "metadatas"])
    docs = data.get("documents") or []
    embs = data.get("embeddings")
    embs = [] if embs is None else list(embs)
    if len(docs) < max(min_topic_size + 1, 6):
        raise RuntimeError(
            f"Solo hay {len(docs)} fragmentos indexados; pocos para modelar temas. "
            "Indexa un pleno entero o más minutos."
        )

    from bertopic import BERTopic
    from sklearn.feature_extraction.text import CountVectorizer

    vectorizer = CountVectorizer(stop_words=_SPANISH_STOPWORDS, ngram_range=(1, 2), min_df=2)
    topic_model = BERTopic(
        embedding_model=None, vectorizer_model=vectorizer,  # usa los embeddings ya guardados (sin GPU)
        min_topic_size=min_topic_size, calculate_probabilities=False, verbose=False,
    )
    topic_model.fit_transform(docs, embeddings=np.array(embs))
    return topic_model


def main() -> None:
    ap = argparse.ArgumentParser(description="Bloque C — temas de los plenos (BERTopic).")
    ap.add_argument("--video-id", default=None, help="limitar a un pleno (id de YouTube)")
    ap.add_argument("--min-topic-size", type=int, default=5)
    args = ap.parse_args()

    cfg = load_config()
    tm = discover_topics(cfg, args.video_id, args.min_topic_size)
    info = tm.get_topic_info()
    cols = [c for c in ("Topic", "Count", "Name") if c in info.columns]
    print(info[cols].to_string(index=False))


if __name__ == "__main__":
    main()
