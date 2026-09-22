"""Consolida entidades DUPLICADAS de la BD (mismo ayuntamiento con slug distinto).

Causa: el formulario generaba "ayuntamiento-de-chiva" y los datos viejos usaban "chiva".
Arregla la raíz (`server._slug` ya da el slug corto) y FUSIONA lo existente: repunta los plenos
y el roster a la entidad canónica (slug corto), junta las huellas y el orden del día, y borra el
duplicado. Hace COPIA de la BD antes. Idempotente.

Uso:  python scripts/consolidate_entidades.py
"""
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.server import _slug  # noqa: E402  (misma regla de slug que usa el producto)
from src import db, voiceid  # noqa: E402
from src.config import resolve_path  # noqa: E402


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _merge_voiceprints(dst_slug: str, src_slug: str) -> None:
    src = voiceid.load_voiceprints(src_slug)
    if not src:
        return
    dst = voiceid.load_voiceprints(dst_slug)
    for name, entry in src.items():
        if name not in dst:                       # la canónica gana en conflicto
            dst[name] = entry
    voiceid.save_voiceprints(dst_slug, dst)
    p = resolve_path(f"data/voiceprints/{src_slug}.json")
    if p.exists():
        p.unlink()


def _move_orden(dst_slug: str, src_slug: str) -> None:
    src = resolve_path(f"data/ref/orden_{src_slug}.txt")
    dst = resolve_path(f"data/ref/orden_{dst_slug}.txt")
    if src.exists() and not dst.exists():
        src.rename(dst)


def main() -> None:
    dbp = resolve_path(db.DB_PATH)
    backup = dbp.with_suffix(".db.bak")
    shutil.copy(dbp, backup)
    print(f"copia de seguridad -> {backup}")

    con = db.connect()
    ents = [dict(r) for r in con.execute("SELECT * FROM entidad")]
    groups = defaultdict(list)
    for e in ents:
        groups[(e["tipo"], _norm(e["nombre"]))].append(e)

    fused = 0
    for (tipo, _), grp in groups.items():
        if len(grp) < 2:
            continue
        target = _slug(grp[0]["nombre"])
        canon = next((e for e in grp if e["slug"] == target), None)
        if canon is None:                          # ninguna tiene el slug corto -> renombra la mayor
            canon = max(grp, key=lambda e: con.execute(
                "SELECT COUNT(*) c FROM pleno WHERE entidad_id=?", (e["id"],)).fetchone()["c"])
            con.execute("UPDATE entidad SET slug=? WHERE id=?", (target, canon["id"]))
            print(f"  renombrada entidad {canon['slug']} -> {target}")
            canon["slug"] = target
        for dup in grp:
            if dup["id"] == canon["id"]:
                continue
            np = con.execute("UPDATE pleno SET entidad_id=? WHERE entidad_id=?",
                             (canon["id"], dup["id"])).rowcount
            con.execute("UPDATE OR IGNORE miembro SET entidad_id=? WHERE entidad_id=?",
                        (canon["id"], dup["id"]))
            con.execute("DELETE FROM miembro WHERE entidad_id=?", (dup["id"],))
            _merge_voiceprints(canon["slug"], dup["slug"])
            _move_orden(canon["slug"], dup["slug"])
            con.execute("DELETE FROM entidad WHERE id=?", (dup["id"],))
            print(f"  fusionada '{dup['slug']}' ({np} plenos) -> '{canon['slug']}'")
            fused += 1
    con.commit()

    print(f"\n{fused} entidad(es) duplicada(s) fusionada(s). Estado final:")
    for e in db.list_entidades(con):
        n = con.execute("SELECT COUNT(*) c FROM pleno WHERE entidad_id=?", (e["id"],)).fetchone()["c"]
        print(f"  {e['slug']:28} {n} plenos  ({e['nombre']})")
    con.close()


if __name__ == "__main__":
    main()
