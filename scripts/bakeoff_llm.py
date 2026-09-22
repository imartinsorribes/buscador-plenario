"""Bake-off de LLMs locales en tu equipo (4 GB): gemma3:1b vs qwen2.5:3b vs mistral:7b.

Dos tareas reales del producto, con tiempo medido (clave en 4 GB):
  A) Extracción de ORDEN DEL DÍA de una convocatoria real (Llíria 28-may, ~8 puntos).
  B) COHERENCIA: ¿pilla un error de transcripción ("humana comunidad"->mancomunidad) y respeta
     una frase limpia (NINGUNO)?  -> donde el local fallaba.

Uso:  python scripts/bakeoff_llm.py
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.summarize import _ollama_generate  # noqa: E402

# Locales (Ollama) + comerciales (OpenRouter, prefijo "or:"). Pon OPENROUTER_API_KEY en .env
# para activar los comerciales; sin clave, se saltan solos.
MODELS = ["gemma3:1b", "qwen2.5:3b", "llama3.2:3b", "phi4-mini", "mistral:7b"]
OPENROUTER = ["or:openai/gpt-4o-mini", "or:anthropic/claude-haiku-4.5",
              "or:google/gemini-3.5-flash", "or:mistralai/mistral-small-3.2-24b-instruct"]


def _load_env():
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for ln in env.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _openrouter(model: str, prompt: str, timeout: int = 120) -> str:
    """Llama a un modelo comercial vía OpenRouter (clave leída del entorno, nunca en claro)."""
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return "[sin OPENROUTER_API_KEY/OPENAI_API_KEY en .env]"
    payload = {"model": model.split(":", 1)[1],
               "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"].strip()

_ORDEN = """Texto de una convocatoria de pleno municipal:
\"\"\"
{text}
\"\"\"
Extrae SOLO los puntos del ORDEN DEL DÍA, uno por línea, con su título tal cual aparece.
Sin numerar, sin preámbulo, y SIN las cláusulas de "notificar"/"publicar"/"dar cuenta".
Si no hay orden del día, responde: NINGUNO"""

_COH = """Revisa esta transcripción automática de un pleno municipal. Marca SOLO palabras MAL
transcritas (suenan parecido a la palabra correcta del contexto). NO marques nombres propios ni
palabras en valenciano. Si dudas, no marques.
TEXTO: "{text}"
Una línea por error con formato: PROBLEMA | <texto literal> | <corrección> | <motivo>.
Si no hay errores, responde solo: NINGUNO"""

_COH_ERROR = "se constituye la humana comunidad de municipios de la comarca para gestionar la basura"
_COH_CLEAN = "se aprueba por mayoría el dictamen de la comisión de hacienda y patrimonio"


def _run(model, prompt, npredict=300):
    t0 = time.time()
    try:
        out = (_openrouter(model, prompt) if model.startswith("or:")
               else _ollama_generate(model, prompt, timeout=300))
    except Exception as e:
        return f"[ERROR {e}]", time.time() - t0
    return out, time.time() - t0


def main():
    _load_env()
    # con argumentos: SOLO esos modelos (p. ej. `bakeoff_llm.py qwen2.5:14b mistral-small:24b`
    # con PLENO_OLLAMA_HOST apuntando al servidor de la UV); sin argumentos: lista completa.
    if len(sys.argv) > 1:
        models = sys.argv[1:]
        print(f"modelos por argumento: {models} (host: {os.environ.get('PLENO_OLLAMA_HOST', 'local')})")
    else:
        models = list(MODELS)
        if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            models += OPENROUTER
            print(f"OpenRouter activo: +{len(OPENROUTER)} modelos comerciales")
        else:
            print("(sin clave en .env -> solo modelos locales)")

    pdf = "data/ref/lliria_convocatoria_28may2026.pdf"
    from pypdf import PdfReader
    conv = "\n".join((p.extract_text() or "") for p in PdfReader(pdf).pages)[:6500]

    for m in models:
        print("\n" + "=" * 70 + f"\nMODELO: {m}\n" + "=" * 70, flush=True)

        out, t = _run(m, _ORDEN.format(text=conv))
        pts = [ln.strip(" -·\t") for ln in out.splitlines() if len(ln.strip()) > 8]
        print(f"[A · ORDEN DEL DÍA]  {t:.0f}s · {len(pts)} líneas extraídas")
        for ln in pts[:10]:
            print("    -", ln[:90])

        oe, te = _run(m, _COH.format(text=_COH_ERROR), npredict=120)
        oc, tc = _run(m, _COH.format(text=_COH_CLEAN), npredict=120)
        caught = "mancomunidad" in oe.lower() or ("problema" in oe.lower() and "humana" in oe.lower())
        clean_ok = "ninguno" in oc.lower()
        print(f"[B · COHERENCIA]  error -> {'PILLADO' if caught else 'fallado'} ({te:.0f}s) · "
              f"limpio -> {'OK (NINGUNO)' if clean_ok else 'falso positivo'} ({tc:.0f}s)")
        print(f"    error dice: {oe.replace(chr(10),' ')[:120]}")


if __name__ == "__main__":
    main()
