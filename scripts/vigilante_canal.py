"""VIGILANTE del canal: cierra el círculo del autopiloto.

Mira el canal de YouTube del ayuntamiento; si hay un pleno NUEVO lo procesa
(descarga→transcribe→acta) y dispara las alertas a los vecinos suscritos.
Pensado para una tarea programada diaria; si no hay nada nuevo, sale sin ruido.

Uso:
  python scripts/vigilante_canal.py --entidad "Ayuntamiento de Chiva"
  python scripts/vigilante_canal.py --entidad "..." --canal https://www.youtube.com/@AytoChiva
  python scripts/vigilante_canal.py --entidad "..." --dry        (solo mirar, no procesar)

Programarlo (una vez, en PowerShell del usuario):
  schtasks /Create /TN "PlenoVigilanteChiva" /SC DAILY /ST 03:00 /TR ^
    "C:\\Users\\ims\\Desktop\\IDAL\\R2\\.venv\\Scripts\\python.exe C:\\Users\\ims\\Desktop\\IDAL\\R2\\scripts\\vigilante_canal.py --entidad \\"Ayuntamiento de Chiva\\""
"""
import argparse
import subprocess
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ))
sys.path.insert(0, str(_RAIZ / "scripts"))

from backfill_canal import PY, _canal_de_entidad, _listar  # noqa: E402
from app.server import _slug  # noqa: E402
from src.config import resolve_path  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entidad", required=True, help='p. ej. "Ayuntamiento de Chiva"')
    ap.add_argument("--canal", default=None, help="URL del canal (si no, se deduce)")
    ap.add_argument("--limit", type=int, default=1, help="máx. plenos nuevos por pasada")
    ap.add_argument("--dry", action="store_true", help="solo mirar qué haría")
    a = ap.parse_args()

    canal = a.canal or _canal_de_entidad(a.entidad)
    if not canal:
        sys.exit("No pude deducir el canal: pásalo con --canal https://www.youtube.com/@...")
    vids = _listar(canal)                                  # ya filtrados por título de pleno
    hechos = {p.stem for p in resolve_path("data/transcripts").glob("*.json")}
    nuevos = [v for v in vids if v["id"] not in hechos]    # el canal lista del más nuevo al más viejo
    print(f"[vigilante] {a.entidad}: {len(vids)} plenos en el canal, {len(nuevos)} nuevo(s)")
    if not nuevos:
        return
    for v in nuevos[: a.limit]:
        print(f"[vigilante] nuevo pleno: {v['id']}  {v['title'][:70]}")
        if a.dry:
            continue
        r = subprocess.run([PY, "-m", "src.run_pleno",
                            f"https://www.youtube.com/watch?v={v['id']}",
                            "--entidad-slug", _slug(a.entidad), "--entidad", a.entidad,
                            "--titulo", v["title"][:120], "--lang", "auto"], cwd=str(_RAIZ))
        if r.returncode != 0:
            print(f"[vigilante] FALLO al procesar ({r.returncode}); no se envían alertas")
            continue
        from src.alertas import procesar_pleno             # import tardío: no carga modelos en vano
        res = procesar_pleno(v["id"])
        print(f"[vigilante] acta lista · avisos enviados: {res.get('avisos', 0)} "
              f"· temas detectados: {', '.join(res.get('detectados', [])) or 'ninguno'}")


if __name__ == "__main__":
    main()
