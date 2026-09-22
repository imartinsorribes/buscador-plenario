"""Genera un MANUAL escrito a partir de un vídeo tutorial (idea del equipo, jul 2026).

Invierte el flujo: transcripción del tutorial (Bloque A) -> CAPÍTULOS por cambio semántico
(BGE-M3, sin regex: se corta donde el parecido entre bloques consecutivos cae) -> un redactor
LLM (gemini-flash, coste único de céntimos) convierte cada capítulo en una sección de manual
(título + explicación + pasos), citando el rango de minutos del vídeo como fuente verificable.
Si el vídeo toca varios módulos, los capítulos permiten trocearlo en varios manuales.

Salida: docs/manual_<video>_generado.md (+ PDF con scripts/md_to_pdf.py).

Uso:  python scripts/video_a_manual.py           # usa el tutorial SECOIN ya transcrito
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.bakeoff_llm import _load_env, _openrouter  # noqa: E402
from src.config import load_config  # noqa: E402
from src.index import get_embedder  # noqa: E402

TRANSCRIPT = "data/sedipualba/transcripts/secoin.json"
VIDEO_ID = "TO3KMwAOkSE"
TITULO = "SECOIN (Control Interno) — Manual generado del vídeo tutorial"
WIN_CHARS = 700          # ventana de narración (~45-60 s)
MIN_WIN = 3              # capítulo mínimo (~2-3 min): evita microcapítulos

_SECCION = """Eres un redactor técnico. Este es un fragmento de la transcripción (automática, hablada)
de un tutorial en vídeo de la plataforma Sedipualb@ (módulo SECOIN, control interno municipal):
\"\"\"{text}\"\"\"

Redacta con ello UNA sección de manual de usuario en markdown:
- empieza con un título breve y descriptivo en una línea '## <título>',
- después 1-2 frases de contexto y los PASOS o ideas clave en lista,
- SOLO con lo que dice el fragmento (es lenguaje hablado: límpialo, no lo inventes),
- omite muletillas, saludos y digresiones del narrador.
Devuelve solo el markdown de la sección."""


def _windows(segments):
    """Ventanas consecutivas de ~WIN_CHARS con su rango temporal."""
    wins, cur, t0, t1 = [], "", None, 0.0
    for s in segments:
        t = (s.get("text") or "").strip()
        if not t:
            continue
        if t0 is None:
            t0 = s.get("start", 0.0)
        cur += " " + t
        t1 = s.get("end", s.get("start", 0.0))
        if len(cur) >= WIN_CHARS:
            wins.append({"text": cur.strip(), "start": t0, "end": t1})
            cur, t0 = "", None
    if cur.strip():
        wins.append({"text": cur.strip(), "start": t0 or 0.0, "end": t1})
    return wins


def _chapters(wins, emb):
    """Corta en capítulos donde cae el parecido entre ventanas consecutivas (cambio de tema)."""
    M = emb.encode([w["text"] for w in wins], normalize_embeddings=True)
    sims = np.array([float(M[i] @ M[i + 1]) for i in range(len(M) - 1)])
    thr = sims.mean() - 0.9 * sims.std()          # corte = caída clara respecto a lo normal
    cuts = [i + 1 for i, s in enumerate(sims) if s < thr]
    # respeta un tamaño mínimo de capítulo
    bounds, last = [0], 0
    for c in cuts:
        if c - last >= MIN_WIN:
            bounds.append(c)
            last = c
    bounds.append(len(wins))
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def _mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def main() -> None:
    _load_env()
    segs = json.loads(Path(TRANSCRIPT).read_text(encoding="utf-8"))["segments"]
    wins = _windows(segs)
    emb = get_embedder(load_config())
    chaps = _chapters(wins, emb)
    print(f"{len(wins)} ventanas -> {len(chaps)} capítulos")

    out = [f"# {TITULO}", "",
           f"Documento GENERADO automáticamente a partir del vídeo tutorial "
           f"(https://youtu.be/{VIDEO_ID}). Cada sección cita el tramo del vídeo del que sale: "
           f"la fuente es verificable al minuto.", ""]
    for k, (a, b) in enumerate(chaps, 1):
        text = " ".join(w["text"] for w in wins[a:b])
        t0, t1 = wins[a]["start"], wins[b - 1]["end"]
        try:
            md = _openrouter("or:google/gemini-3.5-flash", _SECCION.format(text=text[:7000]), timeout=90)
        except Exception as e:
            print(f"  [{k}] fallo LLM: {str(e)[:60]}")
            continue
        if not md.strip().startswith("#"):
            md = f"## Sección {k}\n\n" + md
        md += (f"\n\n*Fuente: vídeo tutorial, min {_mmss(t0)}–{_mmss(t1)} — "
               f"https://youtu.be/{VIDEO_ID}?t={int(t0)}*")
        out.append(md)
        out.append("")
        first = md.splitlines()[0].lstrip('# ')
        print(f"  [{k}] {_mmss(t0)}-{_mmss(t1)}  {first[:70]}")
    dest = Path("docs/manual_secoin_generado.md")
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"\n-> {dest}  (PDF: python scripts/md_to_pdf.py docs/manual_secoin_generado.pdf {dest})")


if __name__ == "__main__":
    main()
