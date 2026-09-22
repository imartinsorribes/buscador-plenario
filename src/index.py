"""Bloque C (2/3): embeddings + base vectorial.

Trocea la transcripción, calcula embeddings (BGE-M3) y los guarda en ChromaDB
con metadatos (vídeo, orador, timestamps y enlace a YouTube en el minuto exacto)
para la búsqueda semántica.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .chunk import chunk_transcript
from .config import load_config, resolve_path

_embedder_cache: dict = {}
_chroma_lock = threading.Lock()


def _yt_link(url: str | None, start: float) -> str:
    if not url:
        return ""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(start)}s"


def get_embedder(cfg):
    from sentence_transformers import SentenceTransformer
    key = cfg.embeddings.model
    if key not in _embedder_cache:
        # BGE-M3 solo publica pytorch_model.bin (sin safetensors). Con transformers
        # 4.46.3 (FIJADO en requirements) torch.load del .bin esta permitido, asi que
        # NO forzamos safetensors: evita el lio del marcador .no_exist de huggingface_hub
        # que sombrea copias locales tras reorganizarse la cache.
        # fp16 + tope de secuencia para que BGE-M3 quepa en los 4 GB de la RTX 3050.
        dtype = "float16" if cfg.embeddings.device == "cuda" else "float32"
        m = SentenceTransformer(
            key, device=cfg.embeddings.device,
            model_kwargs={"use_safetensors": False, "torch_dtype": dtype},
        )
        m.max_seq_length = 512
        _embedder_cache[key] = m
    return _embedder_cache[key]


def get_collection(cfg):
    import chromadb
    # el candado evita la carrera de la PRIMERA inicialización desde hilos (alertas,
    # jobs): dos PersistentClient a la vez corrompen el estado compartido de chroma
    with _chroma_lock:
        try:
            client = chromadb.PersistentClient(path=str(resolve_path(cfg.vector_db.path)))
        except (KeyError, AttributeError):
            # estado compartido roto por una init concurrente previa: limpiar y reintentar
            from chromadb.api.shared_system_client import SharedSystemClient
            SharedSystemClient.clear_system_cache()
            client = chromadb.PersistentClient(path=str(resolve_path(cfg.vector_db.path)))
        return client.get_or_create_collection(
            cfg.vector_db.collection, metadata={"hnsw:space": "cosine"}
        )


def index_transcript(transcript_path, meta: dict, cfg=None) -> int:
    cfg = cfg or load_config()
    transcript = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    ch = cfg.chunking
    chunks = chunk_transcript(
        transcript, max_chars=ch.max_chars,
        respect_speaker=ch.respect_speaker,
        overlap_segments=getattr(ch, "overlap_segments", 1),
    )
    if not chunks:
        print("[index] la transcripción no produjo fragmentos.")
        return 0

    embedder = get_embedder(cfg)
    embs = embedder.encode(
        [c["text"] for c in chunks],
        batch_size=getattr(cfg.embeddings, "batch_size", 16),
        normalize_embeddings=True, show_progress_bar=True,
    )

    vid = str(meta.get("id") or Path(transcript_path).stem)
    title = meta.get("title") or ""
    url = meta.get("url") or ""
    ids, documents, embeddings, metadatas = [], [], [], []
    for i, (c, e) in enumerate(zip(chunks, embs)):
        ids.append(f"{vid}-{i:04d}")
        documents.append(c["text"])
        embeddings.append(e.tolist())
        metadatas.append({
            "video_id": vid, "title": title, "url": url,
            "start": float(c["start"]), "end": float(c["end"]),
            "speaker": c.get("speaker") or "",
            "youtube_link": _yt_link(url, c["start"]),
        })

    col = get_collection(cfg)
    col.delete(where={"video_id": vid})  # borra los fragmentos viejos de este pleno (evita restos)
    col.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    print(f"[index] {len(ids)} fragmentos indexados de '{title or vid}'.")
    return len(ids)
