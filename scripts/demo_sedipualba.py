"""DEMO simple del extra SEDIPUALBA (de punta a punta, en pequeño):

  pregunta -> busca en el manual SECON (texto por página + descripciones de capturas)
           -> respuesta redactada CON CITA (manual, página) -> y la captura como evidencia.

Índice en memoria (BGE-M3 + coseno), sin tocar ChromaDB ni el producto. Es la maqueta del
flujo E+G+H del enunciado con un solo manual.

Uso:  python scripts/demo_sedipualba.py "¿cómo busco un convenio en SECON?"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.bakeoff_llm import _load_env, _openrouter  # noqa: E402  (llamada comercial ya probada)
from src.config import load_config  # noqa: E402
from src.index import get_embedder  # noqa: E402

PDF = Path("data/sedipualba/manuales/Manual_SECON.PDF")
DESCS = Path("data/sedipualba/descripciones.json")

PROMPT = """Pregunta del usuario sobre la plataforma Sedipualb@: {q}

Fragmentos de la documentación (numerados; cada uno indica manual y página):
{ctx}

Responde en español, claro y paso a paso si procede, usando SOLO los fragmentos.
Cita cada afirmación con su número [n]. Al final añade una línea exacta:
FUENTES: <lista de "manual, pág. N" usadas>
Si los fragmentos no bastan, dilo honestamente."""


def build_corpus() -> list[dict]:
    """Fragmentos: texto por página del PDF + descripciones de sus capturas (con página)."""
    import fitz
    out = []
    doc = fitz.open(str(PDF))
    for pno, page in enumerate(doc, start=1):
        txt = " ".join(page.get_text().split())
        if len(txt) > 60:
            out.append({"tipo": "texto", "manual": PDF.name, "page": pno, "text": txt[:1500]})
    for e in json.loads(DESCS.read_text(encoding="utf-8")).values():
        if e["manual"] == PDF.name:
            out.append({"tipo": "captura", "manual": e["manual"], "page": e["page"],
                        "text": e["desc"], "file": e["file"]})
    return out


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else "¿Cómo busco un convenio en SECON?"
    _load_env()
    corpus = build_corpus()
    print(f"Corpus: {len(corpus)} fragmentos "
          f"({sum(1 for c in corpus if c['tipo']=='texto')} de texto, "
          f"{sum(1 for c in corpus if c['tipo']=='captura')} capturas descritas)\n")

    emb = get_embedder(load_config())
    M = emb.encode([c["text"] for c in corpus], normalize_embeddings=True)
    qv = emb.encode([q], normalize_embeddings=True)[0]
    sims = M @ qv
    top = sims.argsort()[::-1][:4]

    ctx_lines, fuentes_img = [], []
    for rank, i in enumerate(top, 1):
        c = corpus[int(i)]
        tag = "captura de pantalla" if c["tipo"] == "captura" else "texto"
        ctx_lines.append(f"[{rank}] ({c['manual']}, pág. {c['page']}, {tag}): {c['text'][:700]}")
        if c["tipo"] == "captura":
            fuentes_img.append((rank, c["page"], c.get("file", "")))
        print(f"  recuperado [{rank}] sim={sims[int(i)]:.2f} · {c['manual']} pág.{c['page']} ({tag})")

    print("\n--- RESPUESTA (gemini-flash, solo con los fragmentos) ---\n")
    out = _openrouter("or:google/gemini-3.5-flash",
                      PROMPT.format(q=q, ctx="\n\n".join(ctx_lines)), timeout=90)
    print(out)
    if fuentes_img:
        print("\n--- EVIDENCIA VISUAL (capturas citables) ---")
        for rank, page, f in fuentes_img:
            print(f"  [{rank}] pág. {page} -> data/sedipualba/images/{f}")


if __name__ == "__main__":
    main()
