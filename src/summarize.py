"""Bloque C (resumen): resúmenes con un LLM local vía Ollama.

Resúmenes NEUTRALES y FIELES: no inventa, no opina y no pone palabras en boca de
nadie; solo condensa lo que aparece en el texto. Sirve para un resumen global del
pleno o por intervención/tema. Requiere Ollama corriendo y `llm.enabled: true`.

Uso:
    python -m src.summarize data/transcripts/<id>.json
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from .config import load_config

_SUMMARY_PROMPT = """Texto de una sesión plenaria (fragmento):
\"\"\"
{text}
\"\"\"

Eres un analista parlamentario. Resume EL TEXTO ANTERIOR en español, de forma NEUTRAL y FIEL: usa solo lo que aparece en el texto, no inventes datos ni opiniones, no pongas palabras en boca de nadie. Ignora los trámites (apertura/cierre de sesión, horarios, turnos de palabra, aplausos) y céntrate en los TEMAS debatidos, las posturas y las cifras.
Responde SOLO con este formato, sin repetir el texto y SIN puntos repetidos:
TITULAR: <una línea>
PUNTOS:
- <3 a 5 puntos clave: qué se plantea, posturas, propuestas o cifras citadas>"""


def _ollama_generate(model: str, prompt: str, host: str | None = None,
                     timeout: int = 600) -> str:
    import os

    # PLENO_OLLAMA_HOST permite apuntar a OTRO Ollama (p. ej. el servidor de la UV con 16 GB,
    # vía túnel SSH en localhost:11435) sin tocar código. Por defecto, el local de siempre.
    # Si el remoto no responde (túnel caído), se DEGRADA al local con PLENO_LLM_LOCAL en vez
    # de fallar: peor modelo un rato es mejor que un error en plena demo.
    host = host or os.environ.get("PLENO_OLLAMA_HOST", "http://localhost:11434")

    def _call(h: str, m: str) -> str:
        payload = {
            "model": m, "prompt": prompt, "stream": False,
            "think": False,   # desactiva el modo "pensante" de qwen3 -> mucho más rápido
            "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 512},
        }
        req = urllib.request.Request(
            h + "/api/generate", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "").strip()

    local = "http://localhost:11434"
    try:
        return _call(host, model)
    except (urllib.error.URLError, TimeoutError) as e:
        if host.rstrip("/") == local:
            raise
        modelo_local = os.environ.get("PLENO_LLM_LOCAL", "qwen2.5:3b")
        print(f"[llm] remoto no responde ({e}); degrado a local {modelo_local}", flush=True)
        return _call(local, modelo_local)


def summarize_text(text: str, cfg=None) -> str:
    cfg = cfg or load_config()
    if not getattr(cfg.llm, "enabled", False):
        raise RuntimeError("LLM deshabilitado: pon llm.enabled: true en config.yaml.")
    return _ollama_generate(cfg.llm.model, _SUMMARY_PROMPT.format(text=text[:8000]))


def summarize_transcript(transcript_path, cfg=None, window_chars: int = 6000) -> str:
    """Resumen de un pleno largo por 'map-reduce': resume bloques y luego los une."""
    cfg = cfg or load_config()
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    full = " ".join(s["text"].strip() for s in data.get("segments", [])).strip()
    if not full:
        return "(transcripción vacía)"

    blocks = [full[i:i + window_chars] for i in range(0, len(full), window_chars)]
    partials = [summarize_text(b, cfg) for b in blocks]
    if len(partials) == 1:
        return partials[0]

    joined = "\n\n".join(partials)
    reduce_prompt = (
        "Une estos resúmenes parciales de una misma sesión plenaria en UN solo resumen "
        "en español, fiel y sin repetir, con el formato TITULAR / PUNTOS:\n\n" + joined
    )
    return _ollama_generate(cfg.llm.model, reduce_prompt)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bloque C — resumen de un pleno (LLM local).")
    ap.add_argument("transcript", help="ruta al JSON de transcripción (data/transcripts/<id>.json)")
    args = ap.parse_args()
    print(summarize_transcript(args.transcript))


if __name__ == "__main__":
    main()
