"""Extra SEDIPUALBA — Bloques E+F+G+H: manuales (texto+capturas) y vídeo tutorial en un índice
multimodal con respuestas citables (manual+página / vídeo+minuto).

Todo se indexa como TEXTO en el mismo espacio BGE-M3 (los fragmentos de los manuales, las
DESCRIPCIONES de las capturas —generadas una vez con visión y cacheadas— y los segmentos del
vídeo tutorial), con metadatos suficientes para citar y ENSEÑAR la fuente: página renderizada
del manual, la propia captura, o el vídeo de YouTube arrancando en el segundo exacto.

Uso:
    python -m src.manuales ingest              # (re)construye el índice con lo que haya
    python -m src.manuales ask "¿cómo busco un convenio?"
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import load_config, resolve_path

MANUALES = "data/sedipualba/manuales"
DESCS = "data/sedipualba/descripciones.json"
VIDEO_TR = "data/sedipualba/transcripts/secoin.json"
VIDEO_ID = "TO3KMwAOkSE"
VIDEO_TITLE = "Tutorial SECOIN (vídeo)"
PAGES_DIR = "data/sedipualba/pages"
COLLECTION = "sedipualba"

_PROMPT = """Pregunta del usuario sobre la plataforma de administración electrónica Sedipualb@: {q}

Fragmentos de la documentación (numerados; cada uno indica su fuente exacta):
{ctx}

Responde claro y COMPLETO, usando SOLO los fragmentos:
- IDIOMA: responde en el MISMO idioma en que está escrita la pregunta del usuario.
  Si la pregunta está en valencià/català, TODA la respuesta debe ir en valencià,
  aunque los fragmentos estén en castellano.
- si el procedimiento tiene pasos, enumera TODOS los que aparezcan en los fragmentos
  (incluidas las alternativas: p. ej. certificado digital Y Cl@ve si constan ambas).
- Cita cada afirmación con su número [n]. No inventes nada que no esté en los fragmentos;
  si falta información para completar algún paso, dilo honestamente al final.
- CÉNTRATE en lo preguntado: no añadas notas al margen ni información de temas
  colindantes que no se han preguntado, aunque aparezcan en los fragmentos.
- Responde en el MISMO idioma de la pregunta (castellano o valencià), aunque los
  fragmentos estén en otro."""


_VER = {"v": None}                                  # versión del índice vista por ESTE proceso


def _collection(cfg=None):
    """Colección del índice. Si otro proceso re-ingestó (cambia data/sedipualba/index.version),
    se limpia la caché de clientes de Chroma y se reabre -> el server ve los cambios SIN reiniciar."""
    import chromadb
    cfg = cfg or load_config()
    vfile = resolve_path("data/sedipualba/index.version")
    v = vfile.read_text(encoding="utf-8") if vfile.exists() else ""
    if _VER["v"] is not None and v != _VER["v"]:
        try:
            chromadb.api.client.SharedSystemClient.clear_system_cache()
            print("[manuales] índice re-ingerido en otro proceso -> recargado sin reiniciar")
        except Exception:
            pass
    _VER["v"] = v
    client = chromadb.PersistentClient(path=str(resolve_path(cfg.vector_db.path)))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def _chunk(text: str, max_chars: int = 1100) -> list[str]:
    """Trocea el texto de una página por frases, en bloques de ~max_chars."""
    sents = re.split(r"(?<=[.:;!?])\s+", text)
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) > max_chars and cur:
            out.append(cur.strip())
            cur = ""
        cur += " " + s
    if cur.strip():
        out.append(cur.strip())
    return out


def _fragments() -> list[dict]:
    """Todos los fragmentos indexables disponibles ahora mismo (manuales + capturas + vídeo)."""
    import fitz
    frags: list[dict] = []
    mdir = resolve_path(MANUALES)
    for pdf in sorted({p.resolve() for p in list(mdir.glob("*.pdf")) + list(mdir.glob("*.PDF"))}):
        doc = fitz.open(str(pdf))
        for pno, page in enumerate(doc, start=1):
            txt = " ".join(page.get_text().split())
            if len(txt) < 60:
                continue
            for j, ch in enumerate(_chunk(txt)):
                frags.append({"id": f"m::{pdf.stem}::p{pno}::c{j}", "text": ch,
                              "meta": {"tipo": "texto", "manual": pdf.name, "page": pno}})
        doc.close()
    dp = resolve_path(DESCS)
    if dp.exists():
        for sha, e in json.loads(dp.read_text(encoding="utf-8")).items():
            frags.append({"id": f"i::{sha[:16]}", "text": e["desc"],
                          "meta": {"tipo": "captura", "manual": e["manual"],
                                   "page": e["page"], "file": e.get("file", "")}})
    # manuales GENERADOS desde vídeos (docs/manual_*.md): el círculo se cierra — también son
    # fuente citable (sección = "página"). Van marcados generado=True para que la BARRERA del
    # generador NO los cuente (esa compara solo contra documentación oficial).
    for md in sorted(resolve_path("docs").glob("manual_*.md")):
        secs = md.read_text(encoding="utf-8").split("\n## ")
        for k, sec in enumerate(secs[1:], 1):
            body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", sec)      # fuera imágenes markdown
            body = " ".join(body.split())
            if len(body) > 120:
                frags.append({"id": f"g::{md.stem}::s{k}", "text": body[:1400],
                              "meta": {"tipo": "texto", "manual": f"{md.stem} (generado)",
                                       "page": k, "generado": True}})
    # VÍDEOS TUTORIALES: todos los transcripts de data/sedipualba/transcripts se indexan
    # por ventanas de ~45-60 s -> el asistente enlaza el MINUTO exacto (no se crean
    # manuales del vídeo: bien indexado basta para quien quiera verlo).
    vistos_vid = set()
    for vt in sorted(resolve_path("data/sedipualba/transcripts").glob("*.json")):
        stem = vt.stem
        if stem == "secoin":                          # legado: mismo vídeo que TO3KMwAOkSE
            vid, title = VIDEO_ID, VIDEO_TITLE
        elif len(stem) == 11:                         # id de YouTube
            vid = stem
            tside = vt.with_name(f"{stem}.title.txt")
            title = tside.read_text(encoding="utf-8").strip() if tside.exists() else "Tutorial (vídeo)"
        else:
            continue
        if vid in vistos_vid:
            continue
        vistos_vid.add(vid)
        segs = json.loads(vt.read_text(encoding="utf-8"))["segments"]
        cur, start, n = "", 0.0, 0
        for s in segs:
            t = (s.get("text") or "").strip()
            if not t:
                continue
            if not cur:
                start = s.get("start", 0.0)
            cur += " " + t
            if len(cur) >= 700:                       # ventanas de ~45-60 s de narración
                frags.append({"id": f"v::{vid}::{n}", "text": cur.strip(),
                              "meta": {"tipo": "video", "video_id": vid,
                                       "title": title, "start": float(start)}})
                cur, n = "", n + 1
        if cur.strip():
            frags.append({"id": f"v::{vid}::{n}", "text": cur.strip(),
                          "meta": {"tipo": "video", "video_id": vid,
                                   "title": title, "start": float(start)}})
    return frags


def ingest(cfg=None) -> dict:
    """(Re)construye el índice 'sedipualba'. Idempotente: borra y re-inserta todo (es pequeño)."""
    from .index import get_embedder
    cfg = cfg or load_config()
    frags = _fragments()
    if not frags:
        return {"indexados": 0}
    emb = get_embedder(cfg)
    vecs = emb.encode([f["text"] for f in frags], batch_size=16, normalize_embeddings=True)
    col = _collection(cfg)
    try:
        col.delete(ids=col.get(include=[])["ids"])   # limpia la colección (rebuild)
    except Exception:
        pass
    col.upsert(ids=[f["id"] for f in frags], documents=[f["text"] for f in frags],
               embeddings=[v.tolist() for v in vecs], metadatas=[f["meta"] for f in frags])
    import time
    resolve_path("data/sedipualba/index.version").write_text(str(time.time()), encoding="utf-8")
    kinds = {}
    for f in frags:
        kinds[f["meta"]["tipo"]] = kinds.get(f["meta"]["tipo"], 0) + 1
    return {"indexados": len(frags), **kinds}


def _llm(prompt: str, cfg) -> str:
    """gemini-flash (mejor calidad/precio medida) con respaldo en el LLM local."""
    import os
    import urllib.request
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:                                        # sin clave -> qwen local
        from .summarize import _ollama_generate
        return _ollama_generate(cfg.llm.model, prompt, timeout=180)
    payload = {"model": "google/gemini-3.5-flash", "temperature": 0.2,
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()


def ask(q: str, k: int = 8, cfg=None, history: list | None = None,
        manual: str | None = None) -> dict:
    """Pregunta -> {respuesta, fuentes[]} con todo lo necesario para citar y enseñar la fuente.

    ``history`` (opcional): turnos previos [{'q','a'},…] para preguntas de SEGUIMIENTO
    («¿y cómo lo firmo?»). Se añade al prompt y, si la pregunta es corta, también enriquece
    la consulta de recuperación con la pregunta anterior (para no buscar sin contexto).
    ``manual`` (opcional): ÁMBITO — restringe la búsqueda de PDF a ese manual (lo coherente
    para el chat de dudas: si se está consultando el manual de SERES, las dudas siguen ahí)."""
    from .index import get_embedder
    cfg = cfg or load_config()
    _load_env()
    col = _collection(cfg)
    if col.count() == 0:
        return {"error": "El índice de manuales está vacío: ejecuta  python -m src.manuales ingest"}
    q_retr = q
    if history and len(q.split()) < 7:               # seguimiento corto -> hereda el tema anterior
        q_retr = history[-1].get("q", "") + " " + q
    qv = get_embedder(cfg).encode([q_retr], normalize_embeddings=True)[0].tolist()
    # prioridad por FUENTE: manual PDF oficial (página citable) > vídeo (minuto) > generado.
    # DOS consultas: una restringida a PDF (garantiza que las páginas del manual entren aunque
    # el vídeo hable mucho del tema) y una libre para vídeo/generados.
    def _pdf_query(where):
        r = col.query(query_embeddings=[qv], n_results=k + 40, where=where)
        return [(d, m, 1.0 - dist) for d, m, dist in
                zip(r["documents"][0], r["metadatas"][0], r["distances"][0])
                if not m.get("generado")]

    glob_pdf = _pdf_query({"tipo": {"$in": ["texto", "captura"]}})
    if manual:
        # ÁMBITO BLANDO: manda el manual en contexto, pero se reservan huecos globales para
        # datos transversales de la plataforma (p. ej. Cl@ve vive en Conceptos, no en SERES).
        # Sin esto, el LLM "sabe" el dato pero no tiene fuente que citar -> cita mal atribuida.
        scoped = _pdf_query({"$and": [{"tipo": {"$in": ["texto", "captura"]}},
                                      {"manual": manual}]})
        resto = [t for t in glob_pdf if t[1].get("manual") != manual]
        pdf_of = (scoped[:max(k - 3, 3)] + resto[:3])[:k]
        if not scoped:                               # ámbito sin resultados -> global
            pdf_of = glob_pdf[:k]
    else:
        pdf_of = glob_pdf[:k]
    res = col.query(query_embeddings=[qv], n_results=k * 2)
    trios = list(zip(res["documents"][0], res["metadatas"][0],
                     [1.0 - x for x in res["distances"][0]]))
    best = max([s for _, _, s in pdf_of + trios] or [0.0])
    # el vídeo y los generados solo entran si son RELEVANTES de verdad (parecido absoluto Y
    # competitivo con la mejor fuente): evita colar minutos de un tutorial de OTRO módulo.
    video = [t for t in trios if t[1]["tipo"] == "video" and t[2] >= 0.52 and t[2] >= best - 0.12]
    genera = [t for t in trios if t[1].get("generado") and t[2] >= 0.55]
    vistos = set()
    elegidos = []
    for d, m, s in pdf_of[:k - 2] + video[:2] + pdf_of[k - 2:] + video[2:] + genera:
        key = json.dumps(m, sort_keys=True)
        if key not in vistos:
            vistos.add(key)
            elegidos.append((d, m))
        if len(elegidos) >= k:
            break
    docs, metas = [d for d, _ in elegidos], [m for _, m in elegidos]

    ctx, fuentes = [], []
    for i, (d, m) in enumerate(zip(docs, metas), 1):
        if m["tipo"] == "video":
            src = f"{m.get('title', 'vídeo')}, minuto {int(m['start'] // 60)}:{int(m['start'] % 60):02d}"
        else:
            src = f"{m['manual']}, pág. {m['page']}" + (" (captura de pantalla)" if m["tipo"] == "captura" else "")
        ctx.append(f"[{i}] ({src}): {d[:1300]}")
        f = {"n": i, "tipo": m["tipo"], "texto": d[:280]}
        if m["tipo"] == "video":
            f.update(video_id=m["video_id"], start=int(m["start"]),
                     url=f"https://youtu.be/{m['video_id']}?t={int(m['start'])}")
        else:
            f.update(manual=m["manual"], page=m["page"], file=m.get("file", ""),
                     generado=bool(m.get("generado")))
        fuentes.append(f)
    prompt = _PROMPT.format(q=q, ctx="\n\n".join(ctx))
    if history:
        hist = "\n".join(f"- Usuario: {h.get('q','')}\n  Asistente: {(h.get('a') or '')[:300]}"
                         for h in history[-3:])
        prompt = ("Conversación previa (solo como contexto para resolver referencias como "
                  "«eso», «y cómo lo firmo»):\n" + hist + "\n\n" + prompt)
    respuesta = _llm(prompt, cfg)
    return {"respuesta": respuesta, "fuentes": fuentes}


def _load_env() -> None:
    import os
    env = resolve_path(".env")
    if env.exists():
        for ln in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                kk, v = ln.split("=", 1)
                os.environ.setdefault(kk.strip(), v.strip().strip('"').strip("'"))


def page_png(manual: str, page: int) -> str | None:
    """Renderiza (y cachea) la página citada del manual -> PNG para enseñarla en la UI."""
    import fitz
    safe = Path(manual).name
    pdf = resolve_path(MANUALES) / safe
    if not pdf.exists():
        return None
    out = resolve_path(PAGES_DIR) / f"{pdf.stem}__p{int(page):02d}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(str(pdf))
        if not (1 <= int(page) <= len(doc)):
            return None
        doc[int(page) - 1].get_pixmap(dpi=110).save(str(out))
        doc.close()
    return str(out)


# ------------------------------------------------- feedback "¿te ha servido?"
def feedback(q: str, util: bool, manual: str = "") -> dict:
    """Métrica viva de utilidad: cada voto se acumula en un JSONL local."""
    import datetime
    p = resolve_path("data/sedipualba/feedback.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                            "q": (q or "")[:300], "util": bool(util),
                            "manual": manual or ""}, ensure_ascii=False) + "\n")
    return feedback_stats()


def feedback_stats() -> dict:
    p = resolve_path("data/sedipualba/feedback.jsonl")
    total = si = 0
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                total += 1
                si += 1 if json.loads(ln).get("util") else 0
            except Exception:
                total -= 1
    return {"total": total, "si": si, "pct": round(100 * si / total) if total else None}


# --------------------------------------------------------- catálogo de manuales
def listado(cfg=None) -> list[str]:
    """Manuales PDF indexados (sin los generados desde vídeo)."""
    col = _collection(cfg or load_config())
    r = col.get(include=["metadatas"])
    return sorted({m.get("manual") for m in r["metadatas"]
                   if m.get("manual") and not m.get("generado") and m.get("tipo") in ("texto", "captura")})


# --------------------------------------- "qué cambió" entre versiones (diff)
def comparar(manual_viejo: str, manual_nuevo: str, cfg=None, umbral: float = 0.75) -> dict:
    """Diff semántico: fragmentos del manual NUEVO sin equivalente en el viejo.
    Extractivo primero (página + extracto literal); la síntesis LLM solo resume
    esos extractos citándolos."""
    import numpy as np
    cfg = cfg or load_config()
    col = _collection(cfg)

    def _lado(man):
        r = col.get(where={"$and": [{"manual": man}, {"tipo": "texto"}]},
                    include=["documents", "metadatas", "embeddings"])
        E = np.asarray(r["embeddings"]) if r["ids"] else np.zeros((0, 1024))
        n = np.linalg.norm(E, axis=1, keepdims=True); n[n == 0] = 1
        return r["documents"], r["metadatas"], E / n

    da, _, Ea = _lado(manual_viejo)
    db_, mb, Eb = _lado(manual_nuevo)
    if not len(da) or not len(db_):
        return {"error": "uno de los manuales no está indexado (¿nombre exacto?)"}
    sims = (Eb @ Ea.T).max(axis=1)                     # mejor pareja en el viejo, por fragmento
    nuevos = [{"page": mb[i].get("page"), "sim": float(sims[i]),
               "texto": db_[i][:420] + ("…" if len(db_[i]) > 420 else "")}
              for i in np.argsort(sims) if sims[i] < umbral][:12]
    nuevos.sort(key=lambda x: (x["page"] or 0))
    resumen = ""
    if nuevos:
        ctx = "\n\n".join(f"[{i+1}] (pág. {n['page']}) {n['texto']}" for i, n in enumerate(nuevos))
        prompt = (f"Fragmentos que aparecen en «{manual_nuevo}» y NO tienen equivalente en "
                  f"«{manual_viejo}» (numerados, con su página):\n\n{ctx}\n\n"
                  "Resume en español, en 3-6 viñetas, QUÉ HAY DE NUEVO según estos fragmentos. "
                  "Cita cada viñeta con su número [n]. No inventes nada que no esté en ellos.")
        try:
            resumen = _llm(prompt, cfg)
        except Exception as e:                                  # noqa: BLE001
            resumen = f"(síntesis no disponible: {e})"
    return {"viejo": manual_viejo, "nuevo": manual_nuevo,
            "n_viejo": len(da), "n_nuevo": len(db_), "nuevos": nuevos, "resumen": resumen}


# ------------------------------------------- búsqueda por PANTALLAZO (visión)
_PANT_PROMPT = """Esta imagen es una captura de pantalla de un usuario trabajando en la plataforma
de administración electrónica Sedipualb@ (módulos SEGEX, SERES, SECON, SEFACE, SEFYCU, SECOIN...).

Describe en español, en 2-4 frases, QUÉ PANTALLA es para poder localizarla en los manuales:
- qué módulo y qué pantalla o menú se ve (cita los textos literales que se lean),
- qué acción o trámite parece estar haciendo el usuario,
- qué botones, campos o pestañas concretos aparecen.
No especules: si algo no se lee, no lo inventes. Devuelve SOLO la descripción."""


def _describir_pantalla(img_bytes: bytes) -> str:
    """Descripción de la captura del usuario con visión (gemini-flash vía OpenRouter),
    cacheada por sha1 del contenido en el MISMO json que la ingesta de manuales."""
    import base64
    import hashlib
    import os
    import urllib.request
    sha = hashlib.sha1(img_bytes).hexdigest()
    cache_p = resolve_path("data/sedipualba/descripciones.json")
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    if sha in cache:                       # la caché de la ingesta guarda dicts {desc, manual…}
        v = cache[sha]
        return v.get("desc", "") if isinstance(v, dict) else v
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("falta la clave de OpenRouter en .env")
    b64 = base64.b64encode(img_bytes).decode()
    payload = {"model": "google/gemini-3.5-flash", "temperature": 0.2,
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": _PANT_PROMPT},
                   {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        desc = json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()
    # mismo formato que la ingesta (dict) para no romper su lectura de la caché
    cache[sha] = {"manual": "", "page": 0, "file": "pantallazo_usuario", "desc": desc}
    cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return desc


def pantallazo(img_bytes: bytes, q: str = "", cfg=None) -> dict:
    """El funcionario sube una captura de DONDE ESTÁ ATASCADO: la visión la describe,
    el match contra las capturas de los manuales identifica la pantalla, y ask()
    (acotado a ese manual) responde el paso siguiente con página citable."""
    from .index import get_embedder
    cfg = cfg or load_config()
    desc = _describir_pantalla(img_bytes)

    emb = get_embedder(cfg)
    col = _collection(cfg)
    qv = emb.encode([desc], normalize_embeddings=True)[0].tolist()
    r = col.query(query_embeddings=[qv], n_results=4, where={"tipo": "captura"})
    pantalla = None
    if r["ids"][0]:
        m, dist = r["metadatas"][0][0], r["distances"][0][0]
        sim = 1.0 - dist
        if sim >= 0.45:                    # por debajo: honestidad antes que adivinar
            pantalla = {"manual": m["manual"], "page": m["page"],
                        "file": m.get("file", ""), "sim": round(sim, 3)}

    pregunta = (q or "").strip() or "¿En qué pantalla estoy y cuál es el paso siguiente?"
    enriquecida = f"{pregunta}\n\n(El usuario está viendo esta pantalla: {desc[:600]})"
    d = ask(enriquecida, cfg=cfg, manual=pantalla["manual"] if pantalla else None)
    d["pantalla"] = pantalla
    d["descripcion"] = desc
    d["pregunta"] = pregunta
    if not pantalla:
        d["nota"] = ("No he reconocido esta pantalla en las capturas de los manuales; "
                     "respondo solo con el texto de la documentación.")
    return d


def main() -> None:
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ingest"
    if cmd == "ingest":
        print(ingest())
    else:
        r = ask(" ".join(sys.argv[2:]) or "¿Cómo busco un convenio en SECON?")
        print(r.get("respuesta", r))
        for f in r.get("fuentes", []):
            print(" ", f)


if __name__ == "__main__":
    main()
