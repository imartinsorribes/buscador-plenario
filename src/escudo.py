"""Descarga automática del ESCUDO del ayuntamiento desde Wikimedia Commons (membrete del acta).

Si el municipio aún no tiene `data/ref/escudo_<slug>.png`, busca su escudo en Commons, lo puntúa
por parecido al nombre (tolera variantes: "Escudo de Xiva" para Chiva), descarga el render PNG y
lo guarda. Best-effort: si no hay match claro, no pone nada (el humano puede dejar el PNG a mano).

Uso:  python -m src.escudo chiva "Ayuntamiento de Chiva"
"""
from __future__ import annotations

import difflib
import io
import json
import re
import unicodedata
import urllib.parse
import urllib.request

from .config import resolve_path

_UA = {"User-Agent": "IDAL-R2-escudo/1.0 (proyecto académico; contacto investigacion)"}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def _municipio(nombre: str) -> str:
    """Nombre del municipio sin el prefijo del organismo (Ayuntamiento/Ajuntament/Concello de…)."""
    m = re.sub(r"^\s*(ayuntamiento|ajuntament|concello|udala?)\s+(de\s+la\s+|de\s+|del\s+|d')?",
               "", (nombre or "").lower())
    return m.strip() or (nombre or "")


def _get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _candidates(query: str) -> list[tuple[str, str]]:
    """(título, url del render PNG) de ficheros de Commons que casan la búsqueda."""
    url = ("https://commons.wikimedia.org/w/api.php?action=query&generator=search"
           "&gsrnamespace=6&gsrlimit=10&prop=imageinfo&iiprop=url|mime&iiurlwidth=512"
           "&format=json&gsrsearch=" + urllib.parse.quote(query))
    pages = (_get(url).get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        out.append((p.get("title", ""), ii.get("thumburl") or ii.get("url") or ""))
    return out


def _best_escudo(muni: str) -> str | None:
    nm = _norm(muni)
    seen, best, score = set(), None, 0.0
    queries = [f"intitle:escudo {muni}", f"intitle:escut {muni}", f"escudo {muni}",
               f"intitle:escudo {nm}", f"intitle:escut {nm}"]   # variantes con/sin acentos
    for q in dict.fromkeys(queries):
        try:
            cands = _candidates(q)
        except Exception:
            continue
        for title, thumb in cands:
            if not thumb or thumb in seen:
                continue
            seen.add(thumb)
            t = re.sub(r"[^a-z0-9 ]", " ", _norm(title))
            if "escudo" not in t and "escut" not in t:
                continue
            m = re.search(r"(?:escudo|escut)\s+de\s+(.+?)\s*(?:svg|png|jpg|jpeg)?\s*$", t)
            name = (m.group(1).strip() if m else t)
            s = difflib.SequenceMatcher(None, nm, name).ratio()
            if s > score:
                score, best = s, thumb
    return best if score >= 0.5 else None


def ensure_escudo(slug: str, nombre: str) -> str | None:
    """Devuelve la ruta del escudo del municipio; lo descarga de Commons si aún no está."""
    path = resolve_path(f"data/ref/escudo_{slug}.png")
    if path.exists():
        return str(path)
    url = _best_escudo(_municipio(nombre))
    if not url:
        return None
    try:
        from PIL import Image
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=60) as r:
            img = Image.open(io.BytesIO(r.read())).convert("RGBA")
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), "PNG")               # normaliza a PNG (venga en SVG-render/JPG/PNG)
        return str(path)
    except Exception:
        return None


def main() -> None:
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "chiva"
    nombre = sys.argv[2] if len(sys.argv) > 2 else "Ayuntamiento de Chiva"
    p = ensure_escudo(slug, nombre)
    print(f"{nombre} ({slug}) -> {p or 'no encontrado'}")


if __name__ == "__main__":
    main()
