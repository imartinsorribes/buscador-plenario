"""Carga de configuración (config.yaml) y secretos (.env)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _to_ns(obj):
    """Convierte dicts anidados en SimpleNamespace para acceso cómodo: cfg.asr.model."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_ns(v) for v in obj]
    return obj


def load_config(path=None) -> SimpleNamespace:
    """Lee config.yaml y carga el .env (HF_TOKEN, etc.) si existe."""
    import os
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cfg = _to_ns(data)
    cfg.root = ROOT
    # PLENO_LLM_MODEL: cambia el modelo LLM sin tocar config.yaml (pareja de PLENO_OLLAMA_HOST
    # para usar el servidor de la UV: qwen2.5:14b / mistral-small:24b). Sin variable -> lo local.
    if os.environ.get("PLENO_LLM_MODEL") and hasattr(cfg, "llm"):
        cfg.llm.model = os.environ["PLENO_LLM_MODEL"]
    return cfg


def resolve_path(rel) -> Path:
    """Resuelve una ruta relativa respecto a la raíz del proyecto."""
    p = Path(rel)
    return p if p.is_absolute() else (ROOT / p)
