"""BACKFILL: procesa en lote los plenos históricos del canal de YouTube de un ayuntamiento.

Lista los vídeos del canal (sin descargarlos), filtra los que parecen PLENOS por el título
(pleno/sesión/plenari), salta los ya procesados, y encadena `src.run_pleno` uno a uno.
Pensado para dejarlo corriendo de noche: cada pleno son ~20-45 min de GPU.

Uso:
  python scripts/backfill_canal.py --canal "https://www.youtube.com/@AytoChiva" --entidad "Ayuntamiento de Chiva" --list
  python scripts/backfill_canal.py --canal ... --entidad "Ayuntamiento de Chiva" --limit 2
  (sin --canal: lo deduce del último pleno procesado de esa entidad)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.server import _slug  # noqa: E402
from src.config import resolve_path  # noqa: E402

PY = sys.executable
_PLENO_KW = ("pleno", "plenari", "sesión", "sesion", "sessió", "sessio")


def _canal_de_entidad(entidad: str) -> str | None:
    """Deduce el canal desde un vídeo ya procesado de la entidad (uploader_url)."""
    from src import db
    con = db.connect()
    for p in db.list_plenos(con):
        if (p["entidad_nombre"] or "").lower() == entidad.lower() and p["video_url"]:
            out = subprocess.run([PY, "-m", "yt_dlp", "--remote-components", "ejs:github",
                                  "--skip-download", "--print", "%(uploader_url)s", p["video_url"]],
                                 capture_output=True, text=True)
            url = (out.stdout or "").strip().splitlines()[-1] if out.stdout else ""
            if url.startswith("http"):
                return url
    return None


def _listar(canal: str) -> list[dict]:
    """Vídeos del canal (flat: solo id+título, no descarga nada)."""
    out = subprocess.run([PY, "-m", "yt_dlp", "--remote-components", "ejs:github",
                          "--flat-playlist", "-J", canal + "/videos"],
                         capture_output=True, text=True)
    data = json.loads(out.stdout or "{}")
    vids = []
    for e in data.get("entries") or []:
        t = (e.get("title") or "")
        if any(k in t.lower() for k in _PLENO_KW):
            vids.append({"id": e.get("id"), "title": t})
    return vids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canal", default=None, help="URL del canal (@usuario o /channel/…)")
    ap.add_argument("--entidad", required=True, help='nombre, p. ej. "Ayuntamiento de Chiva"')
    ap.add_argument("--limit", type=int, default=None, help="máx. de plenos NUEVOS a procesar")
    ap.add_argument("--list", action="store_true", help="solo listar, sin procesar")
    a = ap.parse_args()

    canal = a.canal or _canal_de_entidad(a.entidad)
    if not canal:
        sys.exit("No pude deducir el canal: pásalo con --canal https://www.youtube.com/@...")
    print(f"canal: {canal}")
    vids = _listar(canal)
    hechos = {p.stem for p in resolve_path("data/transcripts").glob("*.json")}
    nuevos = [v for v in vids if v["id"] not in hechos]
    print(f"plenos en el canal: {len(vids)} · ya procesados: {len(vids) - len(nuevos)} · nuevos: {len(nuevos)}\n")
    for v in nuevos:
        print(f"  [nuevo] {v['id']}  {v['title'][:70]}")
    if a.list or not nuevos:
        return

    slug = _slug(a.entidad)
    todo = nuevos[: a.limit] if a.limit else nuevos
    print(f"\nProcesando {len(todo)} pleno(s) en lote (≈20-45 min de GPU cada uno)…")
    for i, v in enumerate(todo, 1):
        print(f"\n===== [{i}/{len(todo)}] {v['title'][:70]} =====", flush=True)
        r = subprocess.run([PY, "-m", "src.run_pleno", f"https://www.youtube.com/watch?v={v['id']}",
                            "--entidad-slug", slug, "--entidad", a.entidad,
                            "--titulo", v["title"][:120], "--lang", "auto"])
        print(f"  -> {'OK' if r.returncode == 0 else f'FALLO ({r.returncode})'}", flush=True)
    print("\nBackfill terminado. Los plenos aparecen en la pestaña Generar (desplegable).")


if __name__ == "__main__":
    main()
