"""Base de datos por ENTIDAD (Congreso, ayuntamientos, parlamentos).

SQLite ligero (data/plenos.db). Modelo:
  entidad : organismo (Congreso / Ayto. de X / ...)
  miembro : roster de la entidad (nombre, grupo, cargo)  <- de Diario / CSV / NER
  pleno   : sesión (fecha, título, vídeo, diario) ligada a una entidad

Las intervenciones (vectores) siguen en ChromaDB; aquí guardamos el catálogo y el
ROSTER por entidad, que es lo que permite nombrar oradores SIN Diario oficial
(municipios). El roster se llena de tres formas:
  - roster_from_diarios / un roster.json  (Congreso, parlamentos con acta)
  - roster_from_csv                        (lista de concejales, manual)
  - roster_bootstrap_from_transcript       (el NER propone, el usuario confirma)

Uso:  python -m src.db            # inicializa + carga el Congreso desde lo ya existente
"""
from __future__ import annotations

import csv
import json
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

from .config import resolve_path

DB_PATH = "data/plenos.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entidad (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  nombre TEXT NOT NULL,
  tipo TEXT,                       -- congreso | parlamento | ayuntamiento | diputacion
  creada TEXT
);
CREATE TABLE IF NOT EXISTS miembro (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidad_id INTEGER NOT NULL REFERENCES entidad(id),
  nombre TEXT NOT NULL,
  grupo TEXT,
  cargo TEXT,
  n INTEGER DEFAULT 0,             -- nº de intervenciones vistas (confianza)
  fuente TEXT,                     -- diario | csv | ner
  UNIQUE(entidad_id, nombre)
);
CREATE TABLE IF NOT EXISTS pleno (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidad_id INTEGER NOT NULL REFERENCES entidad(id),
  video_id TEXT UNIQUE,
  titulo TEXT,
  fecha TEXT,
  video_url TEXT,
  diario_url TEXT,
  n_segmentos INTEGER,
  indexado TEXT
);
"""


def connect() -> sqlite3.Connection:
    p = resolve_path(DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    try:                       # migración: fiabilidad del ASR (0..1) por pleno
        con.execute("ALTER TABLE pleno ADD COLUMN fiabilidad REAL")
        con.commit()
    except sqlite3.OperationalError:
        pass                   # ya existe
    return con


# ----------------------------------------------------------------- entidades
def upsert_entidad(con, slug: str, nombre: str, tipo: str = "") -> int:
    con.execute(
        "INSERT INTO entidad(slug,nombre,tipo,creada) VALUES(?,?,?,?) "
        "ON CONFLICT(slug) DO UPDATE SET nombre=excluded.nombre, tipo=excluded.tipo",
        (slug, nombre, tipo, date.today().isoformat()),
    )
    con.commit()
    return con.execute("SELECT id FROM entidad WHERE slug=?", (slug,)).fetchone()["id"]


def list_entidades(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM entidad ORDER BY nombre")]


# ----------------------------------------------------------------- roster (miembros)
def set_roster(con, entidad_id: int, rows: list[dict], fuente: str = "") -> int:
    """Inserta/actualiza miembros. rows: [{'name','party','cargo'?,'n'?}]."""
    n = 0
    for r in rows:
        nombre = (r.get("name") or r.get("nombre") or "").strip()
        if not nombre:
            continue
        con.execute(
            "INSERT INTO miembro(entidad_id,nombre,grupo,cargo,n,fuente) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(entidad_id,nombre) DO UPDATE SET "
            "grupo=COALESCE(NULLIF(excluded.grupo,''),miembro.grupo), n=excluded.n, fuente=excluded.fuente",
            (entidad_id, nombre, r.get("party") or r.get("grupo") or "",
             r.get("cargo") or "", int(r.get("n") or 0), fuente or r.get("fuente") or ""),
        )
        n += 1
    con.commit()
    return n


def get_roster(con, entidad_id: int) -> list[dict]:
    """Roster en el formato que espera src.speakers.link_roster: [{'name','party','n'}]."""
    return [{"name": r["nombre"], "party": r["grupo"] or "", "n": r["n"] or 0}
            for r in con.execute(
                "SELECT nombre,grupo,n FROM miembro WHERE entidad_id=? ORDER BY n DESC", (entidad_id,))]


# ----------------------------------------------------------------- plenos
def register_pleno(con, entidad_id: int, video_id: str, titulo: str = "", fecha: str = "",
                   video_url: str = "", diario_url: str = "", n_segmentos: int = 0) -> int:
    con.execute(
        "INSERT INTO pleno(entidad_id,video_id,titulo,fecha,video_url,diario_url,n_segmentos,indexado) "
        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET "
        "titulo=excluded.titulo, fecha=excluded.fecha, n_segmentos=excluded.n_segmentos, indexado=excluded.indexado",
        (entidad_id, video_id, titulo, fecha, video_url, diario_url, n_segmentos, date.today().isoformat()),
    )
    con.commit()
    return con.execute("SELECT id FROM pleno WHERE video_id=?", (video_id,)).fetchone()["id"]


def set_fiabilidad(con, video_id: str, valor: float) -> None:
    """Guarda la fiabilidad del ASR (0..1) de un pleno (recall vs Diario o confianza Whisper)."""
    con.execute("UPDATE pleno SET fiabilidad=? WHERE video_id=?", (float(valor), video_id))
    con.commit()


def list_plenos(con, entidad_id: int | None = None) -> list[dict]:
    q = ("SELECT p.*, e.slug AS entidad_slug, e.nombre AS entidad_nombre "
         "FROM pleno p JOIN entidad e ON e.id=p.entidad_id")
    args = ()
    if entidad_id:
        q += " WHERE p.entidad_id=?"; args = (entidad_id,)
    return [dict(r) for r in con.execute(q + " ORDER BY p.fecha DESC", args)]


def entidad_de_video(con, video_id: str) -> int | None:
    r = con.execute("SELECT entidad_id FROM pleno WHERE video_id=?", (video_id,)).fetchone()
    return r["entidad_id"] if r else None


# ----------------------------------------------------------------- fuentes de roster
def roster_from_csv(path) -> list[dict]:
    """CSV con cabecera: nombre,grupo[,cargo]  (lista de concejales para municipios)."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
            if r.get("nombre"):
                rows.append({"name": r["nombre"], "party": r.get("grupo", ""),
                             "cargo": r.get("cargo", ""), "n": 0})
    return rows


def roster_bootstrap_from_transcript(transcript_path, cfg=None) -> list[dict]:
    """Semi-automático: el NER+embeddings propone los oradores de un pleno (con conteo)
    para que el usuario confirme/edite. No requiere Diario."""
    from collections import Counter
    from .config import load_config
    from .speakers import _detect_events
    cfg = cfg or load_config()
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    _, events, _ = _detect_events(data, cfg)
    cnt, grp = Counter(), {}
    for e in events:
        nm = (e.get("name") or "").strip()
        if not nm or nm.startswith("(") or len(nm) < 3:
            continue
        cnt[nm] += 1
        if e.get("party"):
            grp[nm] = e["party"]
    return [{"name": nm, "party": grp.get(nm, ""), "n": n, "fuente": "ner"}
            for nm, n in cnt.most_common()]


# ----------------------------------------------------------------- arranque: Congreso
def main() -> None:
    con = connect()
    eid = upsert_entidad(con, "congreso", "Congreso de los Diputados", "congreso")

    roster_json = resolve_path("data/roster.json")
    if roster_json.exists():
        rows = json.loads(roster_json.read_text(encoding="utf-8"))
        print("[db] roster Congreso:", set_roster(con, eid, rows, fuente="diario"), "miembros")

    info = resolve_path("data/raw_audio/kO3eztYBvDo.info.json")
    if info.exists():
        meta = json.loads(info.read_text(encoding="utf-8"))
        tr = resolve_path("data/transcripts/kO3eztYBvDo.json")
        nseg = len(json.loads(tr.read_text(encoding="utf-8"))["segments"]) if tr.exists() else 0
        register_pleno(con, eid, meta["id"], titulo=meta.get("title", ""), fecha="2026-01-27",
                       video_url=meta.get("webpage_url", ""),
                       diario_url="https://www.congreso.es/public_oficiales/L15/CONG/DS/PL/DSCD-15-PL-161.PDF",
                       n_segmentos=nseg)
        print("[db] pleno registrado:", meta["id"])

    print("\nentidades:", [e["nombre"] for e in list_entidades(con)])
    print("plenos:", [(p["video_id"], p["fecha"], p["n_segmentos"]) for p in list_plenos(con)])
    print("roster (top 5):", [(m["name"], m["party"]) for m in get_roster(con, eid)[:5]])
    con.close()


if __name__ == "__main__":
    main()
