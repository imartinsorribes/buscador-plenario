"""Corpus oficial: ingesta y consulta de los Diarios de Sesiones en JSON.

Cada archivo de ``diarios_congreso_2016-2026/`` sigue el esquema::

    {id, legislatura, fecha, tema_sesion, votaciones, n_intervenciones,
     interventions: [{speaker, party, role, topic, text}, ...]}

Este módulo concentra TODO lo específico del corpus oficial:

  * normaliza oradores y partidos (clave canónica para agrupar entre legislaturas);
  * persiste una fila por intervención en SQLite  -> fichas/agregados EXACTOS;
  * trocea e indexa el texto en una colección propia de ChromaDB -> búsqueda semántica.

La parte cara (embeddings) se hace UNA sola vez. Las cifras de las fichas salen de
SQLite al instante, sin pasar por el LLM ni por el índice vectorial.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------- normalización

def strip_accents(s: str) -> str:
    """Quita tildes/diacríticos para comparaciones robustas."""
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def norm_key(s: str) -> str:
    """Clave de comparación: sin acentos, en minúsculas, sin signos, espacios colapsados."""
    s = strip_accents(s).lower()
    s = re.sub(r"[^0-9a-z\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_ROLE_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def canonical_speaker(raw: str) -> tuple[str, str]:
    """'Sánchez Pérez-Castejón (Candidato...)' -> ('Sánchez Pérez-Castejón', clave).

    Devuelve el nombre legible (sin el cargo entre paréntesis) y su clave de
    agrupación. La clave permite reconocer al mismo orador entre sesiones aunque
    cambie el cargo o el formato.
    """
    disp = _ROLE_PAREN.sub("", (raw or "").strip())
    disp = re.sub(r"\s+", " ", disp).strip()
    return disp, norm_key(disp)


# Reglas (substring sobre la clave normalizada) -> etiqueta canónica del grupo.
# El orden importa: las más específicas primero. Lo que no encaje conserva su
# texto original (sin el prefijo "Grupo Parlamentario"), así nunca se pierde info.
_PARTY_RULES: tuple[tuple[str, str], ...] = (
    ("presidencia", "Presidencia"),
    ("gobierno", "Gobierno"),
    ("mixto", "Grupo Mixto"),
    ("confederal", "Unidas Podemos"),
    ("unidas podemos", "Unidas Podemos"),
    ("izquierda unida", "Unidas Podemos"),
    ("en comu", "Unidas Podemos"),
    ("podemos", "Unidas Podemos"),
    ("sumar", "Sumar"),
    ("socialista", "PSOE"),
    ("popular", "PP"),
    ("vox", "VOX"),
    ("ciudadanos", "Cs"),
    ("esquerra", "ERC"),
    ("republicano", "ERC"),
    ("nacionalista vasco", "PNV"),
    ("eaj", "PNV"),
    ("pnv", "PNV"),
    ("bildu", "EH Bildu"),
    ("euskal herria", "EH Bildu"),
    ("junts", "Junts"),
    ("plural", "Grupo Plural"),
    ("canari", "Coalición Canaria"),
)


def canonical_party(raw: str) -> str:
    """Mapea la etiqueta de grupo (muy variable entre años) a una forma canónica."""
    key = norm_key(raw)
    if not key:
        return ""
    for needle, canon in _PARTY_RULES:
        if needle in key:
            return canon
    cleaned = re.sub(r"^grupo parlamentario\s+", "", (raw or "").strip(), flags=re.I)
    return cleaned.strip() or (raw or "").strip()


# Acrónimos/etiquetas cortas (como las trae el corpus): coincidencia por token exacto,
# para no casar dentro de otras palabras (p. ej. 'pp').
_PARTY_TOKENS = {
    "psoe": "PSOE", "pp": "PP", "vox": "VOX", "cs": "Cs", "erc": "ERC", "pnv": "PNV",
    "bildu": "EH Bildu", "junts": "Junts", "sumar": "Sumar", "podemos": "Unidas Podemos",
    "mixto": "Grupo Mixto", "cup": "CUP", "bng": "BNG", "cc": "Coalición Canaria",
    "upn": "UPN", "pdecat": "Junts",
}


def detect_party(text: str) -> str | None:
    """Detecta la mención de un partido dentro de texto libre (o None)."""
    key = norm_key(text)
    for needle, canon in _PARTY_RULES:
        if needle in key:
            return canon
    tokens = set(key.split())
    for tok, canon in _PARTY_TOKENS.items():
        if tok in tokens:
            return canon
    return None


_MONTHS = {m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto "
    "septiembre octubre noviembre diciembre".split())}
_DATE_RE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", re.IGNORECASE)


def parse_spanish_date(raw: str) -> str | None:
    """'1 de marzo de 2016' -> '2016-03-01' (ISO, para ordenar y filtrar)."""
    m = _DATE_RE.search(raw or "")
    if not m:
        return None
    day, month, year = m.groups()
    mi = _MONTHS.get(strip_accents(month).lower())
    if not mi:
        return None
    return f"{int(year):04d}-{mi:02d}-{int(day):02d}"


# ---------------------------------------------------------------- troceo de texto

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(])")


def split_sentences(text: str) -> list[str]:
    """Divide en frases (heurístico, suficiente para empaquetar fragmentos)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s for s in _SENT_SPLIT.split(text) if s] if text else []


def chunk_text(text: str, max_chars: int = 1200, overlap_sents: int = 1) -> list[str]:
    """Empaqueta frases en trozos de hasta ``max_chars`` con solape de N frases.

    El solape mantiene contexto entre fragmentos vecinos (mejor recuperación).
    Las frases más largas que el tope se trocean en duro para no perder texto.
    """
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for sent in split_sentences(text):
        if len(sent) > max_chars:                       # frase enorme: corte duro
            if cur:
                chunks.append(" ".join(cur))
                cur, cur_len = [], 0
            chunks.extend(sent[i:i + max_chars] for i in range(0, len(sent), max_chars))
            continue
        if cur and cur_len + len(sent) + 1 > max_chars:
            chunks.append(" ".join(cur))
            carry = cur[-overlap_sents:] if overlap_sents else []
            if sum(len(s) + 1 for s in carry) + len(sent) + 1 > max_chars:
                carry = []                       # el solape no puede empujar por encima del tope
            cur = list(carry)
            cur_len = sum(len(s) + 1 for s in cur)
        cur.append(sent)
        cur_len += len(sent) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# ---------------------------------------------------------------- carga del JSON

@dataclass
class Diario:
    """Un pleno ya normalizado y listo para persistir/indexar."""
    pleno_id: str
    legislatura: int
    fecha_raw: str
    fecha_iso: str | None
    tema_sesion: str
    votaciones: list
    interventions: list[dict]   # {idx, speaker, speaker_key, party, party_raw, role, topic, text}


def load_diario(path) -> Diario:
    """Lee un JSON del corpus y devuelve un :class:`Diario` normalizado."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fecha_raw = (data.get("fecha") or "").strip()
    interventions = []
    for i, it in enumerate(data.get("interventions", [])):
        speaker, key = canonical_speaker(it.get("speaker", ""))
        party_raw = (it.get("party") or "").strip()
        text = (it.get("text") or "").strip()
        interventions.append({
            "idx": i,
            "speaker": speaker,
            "speaker_key": key,
            "party": canonical_party(party_raw),
            "party_raw": party_raw,
            "role": (it.get("role") or "").strip(),
            "topic": (it.get("topic") or "").strip(),
            "text": text,
        })
    try:
        leg = int(data.get("legislatura"))
    except (TypeError, ValueError):
        leg = 0
    return Diario(
        pleno_id=str(data.get("id") or Path(path).stem),
        legislatura=leg,
        fecha_raw=fecha_raw,
        fecha_iso=parse_spanish_date(fecha_raw),
        tema_sesion=(data.get("tema_sesion") or "").strip(),
        votaciones=data.get("votaciones") or [],
        interventions=interventions,
    )


# ---------------------------------------------------------------- esquema SQLite

PREVIEW_CHARS = 320

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pleno_meta (
  pleno_id        TEXT PRIMARY KEY,
  legislatura     INTEGER,
  fecha_raw       TEXT,
  fecha_iso       TEXT,
  tema_sesion     TEXT,
  n_intervenciones INTEGER,
  votaciones_json TEXT,
  indexado_chroma INTEGER DEFAULT 0   -- bandera de idempotencia para los embeddings
);
CREATE TABLE IF NOT EXISTS intervencion (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  pleno_id    TEXT NOT NULL,
  idx         INTEGER,
  legislatura INTEGER,
  fecha_iso   TEXT,
  speaker     TEXT,
  speaker_key TEXT,
  party       TEXT,
  party_raw   TEXT,
  role        TEXT,
  topic       TEXT,
  n_chars     INTEGER,
  n_words     INTEGER,
  preview     TEXT
);
CREATE INDEX IF NOT EXISTS ix_int_speaker ON intervencion(speaker_key);
CREATE INDEX IF NOT EXISTS ix_int_party   ON intervencion(party);
CREATE INDEX IF NOT EXISTS ix_int_pleno   ON intervencion(pleno_id);
CREATE INDEX IF NOT EXISTS ix_int_leg     ON intervencion(legislatura);
"""

# Filtro reutilizable para excluir el trámite (Presidencia) de las fichas.
# El trámite se marca con role='presidencia' (y partido vacío); se cubre también el
# caso antiguo en el que el partido era 'Presidencia'.
_NO_PROC = "lower(role) <> 'presidencia' AND party <> 'Presidencia'"


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.commit()


def is_ingested(con: sqlite3.Connection, pleno_id: str) -> tuple[bool, bool]:
    """Devuelve (está_en_SQL, está_en_ChromaDB)."""
    row = con.execute(
        "SELECT indexado_chroma FROM pleno_meta WHERE pleno_id=?", (pleno_id,)
    ).fetchone()
    return (False, False) if row is None else (True, bool(row["indexado_chroma"]))


def clear_pleno(con: sqlite3.Connection, pleno_id: str) -> None:
    con.execute("DELETE FROM intervencion WHERE pleno_id=?", (pleno_id,))
    con.execute("DELETE FROM pleno_meta WHERE pleno_id=?", (pleno_id,))
    con.commit()


def ingest_sql(con: sqlite3.Connection, d: Diario) -> int:
    """Inserta/actualiza pleno + intervenciones. Devuelve nº de intervenciones."""
    con.execute(
        "INSERT INTO pleno_meta(pleno_id,legislatura,fecha_raw,fecha_iso,tema_sesion,"
        "n_intervenciones,votaciones_json,indexado_chroma) VALUES(?,?,?,?,?,?,?,0) "
        "ON CONFLICT(pleno_id) DO UPDATE SET legislatura=excluded.legislatura, "
        "fecha_raw=excluded.fecha_raw, fecha_iso=excluded.fecha_iso, "
        "tema_sesion=excluded.tema_sesion, n_intervenciones=excluded.n_intervenciones, "
        "votaciones_json=excluded.votaciones_json",
        (d.pleno_id, d.legislatura, d.fecha_raw, d.fecha_iso, d.tema_sesion,
         len(d.interventions), json.dumps(d.votaciones, ensure_ascii=False)),
    )
    con.execute("DELETE FROM intervencion WHERE pleno_id=?", (d.pleno_id,))
    con.executemany(
        "INSERT INTO intervencion(pleno_id,idx,legislatura,fecha_iso,speaker,speaker_key,"
        "party,party_raw,role,topic,n_chars,n_words,preview) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(d.pleno_id, it["idx"], d.legislatura, d.fecha_iso, it["speaker"], it["speaker_key"],
          it["party"], it["party_raw"], it["role"], it["topic"],
          len(it["text"]), len(it["text"].split()), it["text"][:PREVIEW_CHARS])
         for it in d.interventions],
    )
    con.commit()
    return len(d.interventions)


# ---------------------------------------------------------------- ChromaDB

def get_corpus_collection(cfg):
    """Colección propia del corpus oficial (separada de la del pipeline de audio)."""
    import chromadb
    from .config import resolve_path
    client = chromadb.PersistentClient(path=str(resolve_path(cfg.vector_db.path)))
    name = getattr(cfg.vector_db, "corpus_collection", "diarios_congreso")
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})


def is_procedural(it: dict) -> bool:
    """Trámite de la mesa (Presidencia): apertura/cierre, turnos, votaciones.

    Se reconoce por el rol ('presidencia') ---así viene en el corpus, con partido
    vacío--- y también por el caso antiguo en que el partido era 'Presidencia'.
    """
    return norm_key(it.get("role", "")) == "presidencia" or it.get("party") == "Presidencia"


def is_substantive(it: dict, min_words: int = 0, skip_procedural: bool = True) -> bool:
    """¿Merece la pena indexar esta intervención para la búsqueda semántica?

    Descarta el trámite de la Presidencia (apertura/cierre, turnos, votaciones) y,
    opcionalmente, las intervenciones por debajo de ``min_words`` (interjecciones,
    agradecimientos…). NO se aplica al SQL: las fichas siguen contando todo.
    """
    if not it["text"]:
        return False
    if skip_procedural and is_procedural(it):
        return False
    if min_words and len(it["text"].split()) < min_words:
        return False
    return True


def build_chunks(d: Diario, max_chars: int, overlap_sents: int,
                 min_words: int = 0, skip_procedural: bool = True) -> list[tuple[str, str, dict]]:
    """(id, texto, metadatos) por cada trozo de cada intervención sustantiva.

    Cita estable: el id es ``pleno:intervención:trozo`` y los metadatos llevan
    orador, partido, tema y legislatura -> filtros baratos en la búsqueda.
    """
    items: list[tuple[str, str, dict]] = []
    for it in d.interventions:
        if not is_substantive(it, min_words, skip_procedural):
            continue
        for ci, chunk in enumerate(chunk_text(it["text"], max_chars, overlap_sents)):
            items.append((
                f"{d.pleno_id}:{it['idx']:03d}:{ci:03d}",
                chunk,
                {
                    "pleno_id": d.pleno_id,
                    "legislatura": d.legislatura,
                    "fecha_iso": d.fecha_iso or "",
                    "speaker": it["speaker"],
                    "party": it["party"],
                    "role": it["role"],
                    "topic": it["topic"],
                    "intervention_idx": it["idx"],
                    "chunk_idx": ci,
                },
            ))
    return items


def ingest_chroma(con, cfg, d: Diario, embedder, col, upsert_batch: int = 512) -> int:
    """Trocea, calcula embeddings e indexa un pleno. Marca el flag al terminar."""
    ch = getattr(cfg, "chunking", None)
    max_chars = getattr(ch, "max_chars", 1200)
    overlap = getattr(ch, "overlap_sents", 1)
    min_words = getattr(ch, "min_words", 0)
    skip_proc = getattr(ch, "skip_procedural", True)
    items = build_chunks(d, max_chars, overlap, min_words, skip_proc)

    col.delete(where={"pleno_id": d.pleno_id})   # evita duplicados al reindexar
    if items:
        ids = [x[0] for x in items]
        docs = [x[1] for x in items]
        metas = [x[2] for x in items]
        embs = embedder.encode(
            docs, batch_size=getattr(cfg.embeddings, "batch_size", 16),
            normalize_embeddings=True, show_progress_bar=False,
        )
        for i in range(0, len(ids), upsert_batch):
            sl = slice(i, i + upsert_batch)
            col.upsert(ids=ids[sl], documents=docs[sl],
                       embeddings=[e.tolist() for e in embs[sl]], metadatas=metas[sl])

    con.execute("UPDATE pleno_meta SET indexado_chroma=1 WHERE pleno_id=?", (d.pleno_id,))
    con.commit()
    return len(items)


# ---------------------------------------------------------------- fichas (SQL)

def resolve_speaker(con, name: str) -> list[dict]:
    """Resuelve un nombre libre a oradores canónicos.

    Coincidencia por tokens: basta con que algún apellido (token de >=3 letras)
    aparezca en el nombre oficial. Ordena por nº de tokens casados y, a igualdad,
    por frecuencia. Así 'Pedro Sánchez' encuentra a 'Sánchez Pérez-Castejón'.
    """
    qtokens = [t for t in norm_key(name).split() if len(t) >= 3]
    if not qtokens:
        return []
    rows = con.execute(
        "SELECT speaker, MIN(speaker_key) AS key, COUNT(*) AS n "
        "FROM intervencion GROUP BY speaker"
    ).fetchall()
    scored = []
    for r in rows:
        hits = sum(1 for t in qtokens if t in r["key"])
        if hits:
            scored.append((hits, r["n"], r["speaker"]))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [{"speaker": s, "n": n, "match": h} for h, n, s in scored]


def speaker_ficha(con, speaker: str) -> dict:
    base = "FROM intervencion WHERE speaker=?"
    head = con.execute(
        f"SELECT COUNT(*) n, COUNT(DISTINCT pleno_id) plenos, "
        f"MIN(fecha_iso) desde, MAX(fecha_iso) hasta, SUM(n_words) palabras {base}",
        (speaker,)).fetchone()
    parties = con.execute(
        f"SELECT party, COUNT(*) n {base} AND party<>'' GROUP BY party ORDER BY n DESC",
        (speaker,)).fetchall()
    topics = con.execute(
        f"SELECT topic, COUNT(*) n {base} AND topic<>'' GROUP BY topic ORDER BY n DESC LIMIT 8",
        (speaker,)).fetchall()
    plenos = con.execute(
        f"SELECT DISTINCT pleno_id, fecha_iso {base} ORDER BY fecha_iso DESC LIMIT 8",
        (speaker,)).fetchall()
    return {
        "speaker": speaker,
        "intervenciones": head["n"], "plenos": head["plenos"],
        "desde": head["desde"], "hasta": head["hasta"], "palabras": head["palabras"] or 0,
        "partidos": [(r["party"], r["n"]) for r in parties],
        "temas": [(r["topic"], r["n"]) for r in topics],
        "plenos_recientes": [(r["pleno_id"], r["fecha_iso"]) for r in plenos],
    }


def party_ficha(con, party: str, include_procedural: bool = False) -> dict:
    proc = "" if include_procedural else f"AND {_NO_PROC}"
    base = f"FROM intervencion WHERE party=? {proc}"
    head = con.execute(
        f"SELECT COUNT(*) n, COUNT(DISTINCT pleno_id) plenos, COUNT(DISTINCT speaker) oradores, "
        f"MIN(fecha_iso) desde, MAX(fecha_iso) hasta, SUM(n_words) palabras {base}",
        (party,)).fetchone()
    speakers = con.execute(
        f"SELECT speaker, COUNT(*) n {base} GROUP BY speaker ORDER BY n DESC LIMIT 10",
        (party,)).fetchall()
    topics = con.execute(
        f"SELECT topic, COUNT(*) n {base} AND topic<>'' GROUP BY topic ORDER BY n DESC LIMIT 10",
        (party,)).fetchall()
    return {
        "partido": party,
        "intervenciones": head["n"], "plenos": head["plenos"], "oradores": head["oradores"],
        "desde": head["desde"], "hasta": head["hasta"], "palabras": head["palabras"] or 0,
        "oradores_top": [(r["speaker"], r["n"]) for r in speakers],
        "temas": [(r["topic"], r["n"]) for r in topics],
    }


def pleno_ficha(con, pleno_id: str) -> dict | None:
    meta = con.execute("SELECT * FROM pleno_meta WHERE pleno_id=?", (pleno_id,)).fetchone()
    if meta is None:
        return None
    parties = con.execute(
        "SELECT party, COUNT(*) n FROM intervencion WHERE pleno_id=? AND party<>'' "
        "GROUP BY party ORDER BY n DESC", (pleno_id,)).fetchall()
    speakers = con.execute(
        f"SELECT speaker, COUNT(*) n, SUM(n_words) w FROM intervencion "
        f"WHERE pleno_id=? AND {_NO_PROC} GROUP BY speaker ORDER BY w DESC LIMIT 10",
        (pleno_id,)).fetchall()
    topics = con.execute(
        "SELECT DISTINCT topic FROM intervencion WHERE pleno_id=? AND topic<>''",
        (pleno_id,)).fetchall()
    votaciones = json.loads(meta["votaciones_json"] or "[]")
    votos = [
        {"a_favor": v.get("a_favor"), "en_contra": v.get("en_contra"),
         "abstenciones": v.get("abstenciones")}
        for v in votaciones if isinstance(v, dict)
    ]
    return {
        "pleno_id": pleno_id, "fecha": meta["fecha_raw"], "legislatura": meta["legislatura"],
        "tema_sesion": meta["tema_sesion"], "intervenciones": meta["n_intervenciones"],
        "reparto_partidos": [(r["party"], r["n"]) for r in parties],
        "oradores_principales": [(r["speaker"], r["n"], r["w"] or 0) for r in speakers],
        "temas": [r["topic"] for r in topics],
        "n_votaciones": len(votaciones),
        "votaciones": votos,
    }


_PLENO_ID_RE = re.compile(r"^DSCD-(\d+)-PL-(\d+)$")


def diario_url(pleno_id: str) -> str | None:
    """URL oficial del Diario de Sesiones en congreso.es para un pleno.

    El Congreso publica cada sesión en una ruta predecible a partir del id:
    p. ej. DSCD-14-PL-128 -> https://www.congreso.es/public_oficiales/L14/CONG/DS/PL/DSCD-14-PL-128.PDF
    """
    m = _PLENO_ID_RE.match(pleno_id or "")
    if not m:
        return None
    return (f"https://www.congreso.es/public_oficiales/L{m.group(1)}"
            f"/CONG/DS/PL/{pleno_id}.PDF")


def evolution_by_legislature(con, kind: str, key: str) -> list[dict]:
    """Evolución agregada de un orador o partido, legislatura a legislatura (exacto, SQL).

    ``kind`` = 'candidato' (``key`` = nombre canónico del orador) o 'partido'.
    Por cada legislatura devuelve intervenciones, plenos, periodo de fechas y temas top.
    Excluye el trámite de Presidencia. Se apoya en los índices de speaker/party y legislatura.
    """
    field = "speaker" if kind == "candidato" else "party"
    rows = con.execute(
        f"SELECT legislatura, COUNT(*) n, COUNT(DISTINCT pleno_id) plenos, "
        f"       MIN(fecha_iso) fmin, MAX(fecha_iso) fmax "
        f"FROM intervencion WHERE {field}=? AND {_NO_PROC} "
        f"GROUP BY legislatura ORDER BY legislatura", (key,)).fetchall()
    out = []
    for r in rows:
        temas = con.execute(
            f"SELECT topic, COUNT(*) c FROM intervencion "
            f"WHERE {field}=? AND legislatura=? AND topic<>'' AND {_NO_PROC} "
            f"GROUP BY topic ORDER BY c DESC LIMIT 3", (key, r["legislatura"])).fetchall()
        out.append({"legislatura": r["legislatura"], "n": r["n"], "plenos": r["plenos"],
                    "fecha_min": r["fmin"], "fecha_max": r["fmax"],
                    "temas": [t["topic"] for t in temas]})
    return out


def list_parties(con) -> list[tuple[str, int]]:
    rows = con.execute(
        f"SELECT party, COUNT(*) n FROM intervencion WHERE party<>'' AND {_NO_PROC} "
        "GROUP BY party ORDER BY n DESC").fetchall()
    return [(r["party"], r["n"]) for r in rows]


def latest_pleno(con, leg: int | None = None) -> str | None:
    """Id del pleno más reciente (opcionalmente dentro de una legislatura)."""
    cond = "fecha_iso IS NOT NULL AND fecha_iso<>''"
    params: tuple = ()
    if leg is not None:
        cond += " AND legislatura=?"
        params = (leg,)
    row = con.execute(
        f"SELECT pleno_id FROM pleno_meta WHERE {cond} ORDER BY fecha_iso DESC LIMIT 1",
        params).fetchone()
    return row["pleno_id"] if row else None


def earliest_pleno(con, leg: int | None = None) -> str | None:
    """Id del pleno más antiguo (opcionalmente dentro de una legislatura)."""
    cond = "fecha_iso IS NOT NULL AND fecha_iso<>''"
    params: tuple = ()
    if leg is not None:
        cond += " AND legislatura=?"
        params = (leg,)
    row = con.execute(
        f"SELECT pleno_id FROM pleno_meta WHERE {cond} ORDER BY fecha_iso ASC LIMIT 1",
        params).fetchone()
    return row["pleno_id"] if row else None


def pleno_by_number(con, leg: int | None, num: int) -> str | None:
    """Resuelve 'pleno N (de la legislatura L)' al id real (DSCD-L-PL-N)."""
    if leg is not None:
        candidate = f"DSCD-{leg}-PL-{num}"
        if con.execute("SELECT 1 FROM pleno_meta WHERE pleno_id=? LIMIT 1",
                       (candidate,)).fetchone():
            return candidate
        row = con.execute(
            "SELECT pleno_id FROM pleno_meta WHERE legislatura=? AND pleno_id LIKE ? LIMIT 1",
            (leg, f"%-PL-{num}")).fetchone()
        return row["pleno_id"] if row else None
    # sin legislatura: solo si la numeración es inequívoca en todo el corpus
    rows = con.execute(
        "SELECT pleno_id FROM pleno_meta WHERE pleno_id LIKE ?", (f"%-PL-{num}",)).fetchall()
    return rows[0]["pleno_id"] if len(rows) == 1 else None


def prune_stats(con, min_words: int = 0, skip_procedural: bool = True) -> dict:
    """Cuánto se PODARÍA del índice con un umbral dado (sin reindexar, solo SQL).

    Las palabras podadas son buena aproximación de la reducción de fragmentos/embeddings.
    """
    total = con.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(n_words),0) w FROM intervencion").fetchone()
    cond = []
    if skip_procedural:
        cond.append("(lower(role)='presidencia' OR party='Presidencia')")
    if min_words:
        cond.append(f"n_words < {int(min_words)}")
    where = " WHERE " + " OR ".join(cond) if cond else " WHERE 0"
    pruned = con.execute(
        f"SELECT COUNT(*) c, COALESCE(SUM(n_words),0) w FROM intervencion{where}").fetchone()
    return {"total_interv": total["c"], "total_words": total["w"],
            "pruned_interv": pruned["c"], "pruned_words": pruned["w"]}


def resolve_party(con, text: str) -> str:
    """Resuelve texto libre a una etiqueta de partido REAL del corpus.

    Funciona para cualquier grupo presente en los datos, esté o no en las reglas:
      1) si la forma canónica existe tal cual entre las etiquetas guardadas, la usa;
      2) si no, casa por subcadena o por tokens contra las etiquetas reales
         (p. ej. 'Compromís' encuentra 'Plural-Compromís').
    Si nada casa, devuelve la mejor forma canónica como último recurso.
    """
    canon = canonical_party(text)
    if canon and con.execute(
            "SELECT 1 FROM intervencion WHERE party=? LIMIT 1", (canon,)).fetchone():
        return canon

    qkey = norm_key(text)
    qtokens = [t for t in qkey.split() if len(t) >= 3]
    best = None  # (score, n, label)
    for label, n in list_parties(con):
        lk = norm_key(label)
        score = 100 if qkey and qkey in lk else sum(1 for t in qtokens if t in lk)
        if score and (best is None or (score, n) > (best[0], best[1])):
            best = (score, n, label)
    return best[2] if best else canon
