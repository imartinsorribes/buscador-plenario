"""Bloque E (extra SEDIPUALBA) — describe las IMÁGENES de los manuales para hacerlas buscables.

Extrae las imágenes de cada PDF (con su página de origen), filtra iconos/logos por tamaño y
genera una DESCRIPCIÓN textual de cada captura con un modelo de visión (gemini-flash vía
OpenRouter, céntimos). La descripción se indexa después como texto normal (espacio BGE-M3
uniforme) con metadatos {manual, página} -> respuesta citable "manual X, pág. Y".

CACHÉ: cada descripción se guarda en data/sedipualba/descripciones.json bajo el sha1 del
CONTENIDO de la imagen -> se paga UNA vez; relanzar la ingesta no repite llamadas (coste 0).

Uso:
  python scripts/ingest_imagenes.py --limit 3          # prueba con 3 imágenes (plantilla)
  python scripts/ingest_imagenes.py                    # todos los manuales (usa caché)
  python scripts/ingest_imagenes.py --manual SECON     # solo los PDF que casen ese nombre
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MANUALES = Path("data/sedipualba/manuales")
IMGDIR = Path("data/sedipualba/images")
CACHE = Path("data/sedipualba/descripciones.json")
MODEL = "google/gemini-3.5-flash"
MIN_W, MIN_H, MIN_KB = 200, 120, 8          # fuera iconos, logos y viñetas

# La plantilla: pedimos una descripción ORIENTADA A BÚSQUEDA (qué pantalla es, qué se hace en
# ella, qué botones/menús se ven), con el texto de la página como contexto para anclar términos.
PROMPT = """Esta imagen es una captura de un manual de la plataforma de administración electrónica
Sedipualb@ (módulos SEGEX, SERES, SECON, SEFACE, SEFYCU...). Contexto de la página del manual:
\"\"\"{context}\"\"\"

Describe la captura en español, en 2-4 frases, PARA QUE SE PUEDA ENCONTRAR BUSCANDO:
- qué pantalla o menú de la aplicación se ve (nombre del módulo si se aprecia),
- qué acción o procedimiento ilustra,
- qué botones, campos o menús concretos aparecen (cita sus textos literales si se leen).
No especules: si algo no se lee, no lo inventes. Devuelve SOLO la descripción."""


def _load_env():
    env = Path(".env")
    if env.exists():
        for ln in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _describe(png_bytes: bytes, context: str, timeout: int = 90) -> str:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Falta OPENROUTER_API_KEY/OPENAI_API_KEY en .env")
    b64 = base64.b64encode(png_bytes).decode()
    payload = {"model": MODEL, "temperature": 0.2, "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT.format(context=context[:600])},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()


def main() -> None:
    import fitz
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="máx. de imágenes NUEVAS a describir")
    ap.add_argument("--manual", default="", help="filtra manuales por subcadena del nombre")
    args = ap.parse_args()
    _load_env()
    IMGDIR.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    pdfs = sorted({p.resolve() for p in list(MANUALES.glob("*.pdf")) + list(MANUALES.glob("*.PDF"))})
    done = skipped = failed = 0
    for pdf in pdfs:
        if args.manual and args.manual.lower() not in pdf.name.lower():
            continue
        doc = fitz.open(str(pdf))
        for pno, page in enumerate(doc, start=1):
            ctx = " ".join(page.get_text().split())
            for i, im in enumerate(page.get_images(full=True)):
                try:
                    raw = doc.extract_image(im[0])
                except Exception:
                    continue
                w, h, data = raw.get("width", 0), raw.get("height", 0), raw["image"]
                if w < MIN_W or h < MIN_H or len(data) < MIN_KB * 1024:
                    continue                       # icono/logo: fuera
                sha = hashlib.sha1(data).hexdigest()
                png = IMGDIR / f"{pdf.stem}__p{pno:02d}__{i}.png"
                if not png.exists():
                    png.write_bytes(data)
                if sha in cache:                   # YA descrita en otra pasada -> coste 0
                    skipped += 1
                    continue
                if args.limit is not None and done >= args.limit:
                    continue
                try:
                    desc = _describe(data, ctx)
                except Exception as e:
                    failed += 1
                    print(f"  [fallo] {png.name}: {str(e)[:70]}")
                    continue
                cache[sha] = {"manual": pdf.name, "page": pno, "file": png.name,
                              "desc": desc, "model": MODEL}
                done += 1
                print(f"  [{done}] {pdf.name} pág.{pno} -> {desc[:110]}…")
        doc.close()
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nDescritas NUEVAS: {done} · en caché (saltadas): {skipped} · fallos: {failed}"
          f"\nCaché: {CACHE} ({len(cache)} descripciones)")


if __name__ == "__main__":
    main()
