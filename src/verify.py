"""Verificador de fidelidad (anti-alucinación) por grounding semántico.

Para cada frase del resumen mide su MÁXIMA similitud (coseno, BGE-M3) con las
frases del texto fuente. Si la mejor similitud es baja, la frase NO está respaldada
→ posible alucinación. No es regex: capta paráfrasis (mismo significado, otras palabras).
"""
from __future__ import annotations

import re

import numpy as np

from .config import load_config
from .index import get_embedder


def split_sentences(text: str, min_len: int = 25) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= min_len]


def faithfulness(summary: str, source_text: str, cfg=None, threshold: float = 0.6) -> dict:
    """Devuelve por cada frase del resumen su apoyo máximo en el texto y si supera el umbral."""
    cfg = cfg or load_config()
    emb = get_embedder(cfg)
    claims = split_sentences(summary)
    sources = split_sentences(source_text)
    if not claims or not sources:
        return {"score": None, "claims": []}
    cv = np.array(emb.encode(claims, normalize_embeddings=True, batch_size=4))
    sv = np.array(emb.encode(sources, normalize_embeddings=True, batch_size=8))
    best = (cv @ sv.T).max(axis=1)
    claims_out = [{"claim": c, "support": float(b), "ok": bool(b >= threshold)}
                  for c, b in zip(claims, best)]
    grounded = sum(c["ok"] for c in claims_out)
    return {"score": grounded / len(claims_out), "grounded": grounded,
            "n": len(claims_out), "claims": claims_out}


_nli_cache: dict = {}


def _get_nli():
    if not _nli_cache:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        name = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForSequenceClassification.from_pretrained(
            name, use_safetensors=True,
            torch_dtype=torch.float16 if dev == "cuda" else torch.float32,
        ).to(dev).eval()
        ent = next(i for i, lab in model.config.id2label.items() if "entail" in lab.lower())
        _nli_cache.update(tok=tok, model=model, ent=int(ent), torch=torch, dev=dev)
    return _nli_cache


def _entail_batch(pairs: list[tuple[str, str]], bs: int = 16) -> list[float]:
    """Prob. de entailment para (premisa, hipótesis), por lotes y en GPU."""
    nli = _get_nli()
    tok, model, ent, torch, dev = (nli["tok"], nli["model"], nli["ent"], nli["torch"], nli["dev"])
    out: list[float] = []
    for k in range(0, len(pairs), bs):
        chunk = pairs[k:k + bs]
        inp = tok([p for p, _ in chunk], [h for _, h in chunk], return_tensors="pt",
                  truncation=True, max_length=512, padding=True).to(dev)
        with torch.no_grad():
            out.extend(torch.softmax(model(**inp).logits, -1)[:, ent].float().tolist())
    return out


def prepare_source(source_text: str, cfg=None):
    """Embebe las frases de la fuente UNA vez (para reusar en varias comprobaciones)."""
    cfg = cfg or load_config()
    sources = split_sentences(source_text)
    sv = np.array(get_embedder(cfg).encode(sources, normalize_embeddings=True, batch_size=8))
    return sources, sv


def faithfulness_nli(summary: str, source_text: str = "", cfg=None, top_k: int = 4,
                     threshold: float = 0.5, source=None) -> dict:
    """Fidelidad por ENTAILMENT: recupera las frases fuente afines (BGE-M3) y comprueba con
    NLI si IMPLICAN cada afirmación. `source`=(sources, vecs) precomputado evita re-embeber."""
    cfg = cfg or load_config()
    sources, sv = source if source is not None else prepare_source(source_text, cfg)
    claims = split_sentences(summary)
    if not claims or not sources:
        return {"score": None, "claims": []}
    cv = np.array(get_embedder(cfg).encode(claims, normalize_embeddings=True, batch_size=4))
    # premisa = las top_k frases afines JUNTAS (así una síntesis verdadera se sostiene
    # sobre el conjunto, pero una mentira sigue sin estar respaldada)
    pairs = []
    for ci, cvec in enumerate(cv):
        top = np.argsort(-(sv @ cvec))[:top_k]
        premise = " ".join(sources[int(i)] for i in top)
        pairs.append((premise, claims[ci]))
    best = _entail_batch(pairs)
    out = [{"claim": c, "entail": round(b, 3), "ok": b >= threshold} for c, b in zip(claims, best)]
    grounded = sum(o["ok"] for o in out)
    return {"score": grounded / len(out), "grounded": grounded, "n": len(out), "claims": out}
