"""Buscador inteligente: ficha exacta (SQLite) + fragmentos relevantes (ChromaDB) -> LLM.

Recapitula la información clave de un CANDIDATO, un PARTIDO o un PLENO. Las cifras
salen de SQLite (exactas, instantáneas). Si además se da una pregunta, recupera los
fragmentos más relevantes filtrando por esa entidad y se los pasa a un LLM para que
responda SOLO con ese contexto pequeño: rápido, barato y fiel (no lee todo el corpus).

Uso:
    python -m src.recap repl                   # sesión interactiva (no recarga modelos)
    python -m src.recap ask "¿Opinión de los candidatos de Vox sobre el aborto?"
    python -m src.recap tema "aborto"          # resumen equilibrado entre grupos
    python -m src.recap candidato "Pedro Sánchez" -q "¿qué dijo sobre vivienda?"
    python -m src.recap partido VOX --temas
    python -m src.recap pleno DSCD-11-PL-2 -q "¿qué se debatió?"
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import dataclass, field

from . import diarios
from .config import load_config
from .db import connect


@dataclass
class Recap:
    """Resultado de una recapitulación: ficha estructurada + fragmentos + (opcional) pregunta."""
    kind: str                       # 'candidato' | 'partido' | 'pleno'
    title: str
    ficha: dict
    fragments: list = field(default_factory=list)
    question: str | None = None
    note: str = ""


# ----------------------------------------------------------------- recuperación

def _where(**filters):
    """Construye un filtro de ChromaDB válido (uno o varios campos con $and)."""
    items = [{k: v} for k, v in filters.items() if v not in (None, "")]
    if not items:
        return None
    return items[0] if len(items) == 1 else {"$and": items}


# --- generación LLM (Ollama) con keep_alive para no recargar el modelo entre consultas
import os as _os

_LLM_HOST = _os.environ.get("PLENO_OLLAMA_HOST", "http://localhost:11434")


def _llm(prompt: str, cfg, num_predict: int = 400, timeout: int = 600) -> str:
    """Llama a Ollama manteniendo el modelo en memoria (keep_alive) y acotando la salida.
    Si el host remoto (túnel de la UV) no responde, DEGRADA al Ollama local en vez de
    devolver un 500: la búsqueda sigue funcionando con el modelo pequeño."""
    def _call(host: str, model: str) -> str:
        payload = {
            "model": model, "prompt": prompt, "stream": False, "think": False,
            "keep_alive": getattr(cfg.llm, "keep_alive", "30m"),
            "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": num_predict},
        }
        req = urllib.request.Request(
            host + "/api/generate", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "").strip()

    local = "http://localhost:11434"
    try:
        return _call(_LLM_HOST, cfg.llm.model)
    except (urllib.error.URLError, TimeoutError) as e:
        if _LLM_HOST.rstrip("/") == local:
            raise
        modelo_local = _os.environ.get("PLENO_LLM_LOCAL", "qwen2.5:3b")
        print(f"[recap] LLM remoto no responde ({e}); degrado a local {modelo_local}", flush=True)
        return _call(local, modelo_local)


# --- caché del reranker: se carga UNA vez por proceso (clave para reusar entre consultas)
_RERANKER: dict = {}


def _get_reranker(cfg):
    rk = getattr(cfg, "reranker", None)
    if not (rk and getattr(rk, "enabled", False)):
        return None
    ce = _RERANKER.get(rk.model)
    if ce is None:
        from sentence_transformers import CrossEncoder
        ce = _RERANKER[rk.model] = CrossEncoder(rk.model, device=cfg.embeddings.device)
    return ce


def retrieve(question: str, cfg, where, final_k: int, pool: int | None = None, col=None) -> list[dict]:
    """Top-k fragmentos del corpus para la pregunta, filtrados por entidad.

    ``pool`` permite ampliar el nº de candidatos que se traen y reordenan (útil para
    el resumen por temas, que luego reparte los fragmentos entre grupos).
    ``col`` permite consultar otra colección (p. ej. el índice multimodal) reusando
    todo el motor (reranker, compresión).
    """
    from .index import get_embedder
    col = col if col is not None else diarios.get_corpus_collection(cfg)
    n_results = pool or getattr(cfg.retrieval, "top_k", 20)
    q_emb = get_embedder(cfg).encode([question], normalize_embeddings=True)[0].tolist()
    res = col.query(query_embeddings=[q_emb], n_results=n_results, where=where)

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res.get("distances", [[None] * len(docs)])[0]
    hits = [{"text": d, "meta": m, "distance": dist}
            for d, m, dist in zip(docs, metas, dists)]

    rk = getattr(cfg, "reranker", None)
    if rk and getattr(rk, "enabled", False) and hits:
        ce = _get_reranker(cfg)
        for h, score in zip(hits, ce.predict([(question, h["text"]) for h in hits])):
            h["rerank"] = float(score)
        hits.sort(key=lambda h: h["rerank"], reverse=True)

    hits = hits[:final_k]
    if getattr(cfg.retrieval, "focus", True):
        hits = _focus_hits(q_emb, hits, cfg, getattr(cfg.retrieval, "focus_sents", 3))
    return hits


def _focus_hits(q_emb, hits: list[dict], cfg, max_sents: int = 3) -> list[dict]:
    """Compresión extractiva: deja en cada fragmento solo las frases afines a la pregunta.

    Filtra reproches al rival, vocativos a la presidencia y alusiones a terceros, que
    no se parecen al tema. Reutiliza el embedder ya cargado (sin coste de LLM). El texto
    íntegro queda en ``text_full`` por si se necesita.
    """
    if max_sents <= 0 or not hits:
        return hits
    import numpy as np
    from .index import get_embedder

    sents_per_hit = [diarios.split_sentences(h["text"]) for h in hits]
    flat = [s for sents in sents_per_hit for s in sents]
    if not flat:
        return hits
    mat = get_embedder(cfg).encode(flat, normalize_embeddings=True)
    q = np.asarray(q_emb, dtype=mat.dtype)

    pos = 0
    for h, sents in zip(hits, sents_per_hit):
        n = len(sents)
        if n > max_sents:
            sims = mat[pos:pos + n] @ q
            keep = sorted(sorted(range(n), key=lambda i: sims[i], reverse=True)[:max_sents])
            h["text_full"] = h["text"]
            h["text"] = " ".join(sents[i] for i in keep)
        pos += n
    return hits


# ----------------------------------------------------------------- construcción

def build_recap(kind: str, value: str, cfg=None, con=None,
                question: str | None = None, final_k: int | None = None,
                leg: int | None = None) -> Recap:
    """Construye la recapitulación de una entidad (resolviendo el nombre si hace falta).

    ``leg`` limita los fragmentos recuperados a una legislatura concreta (metadato de
    ChromaDB); coste nulo y, de hecho, reduce el espacio de búsqueda.
    """
    cfg = cfg or load_config()
    con = con or connect()
    diarios.ensure_schema(con)
    final_k = final_k or getattr(cfg.retrieval, "final_k", 5)
    leg_note = f" · fragmentos limitados a la legislatura {leg}" if leg else ""

    if kind == "candidato":
        matches = diarios.resolve_speaker(con, value)
        if not matches:
            return Recap(kind, value, {}, note=f"Sin coincidencias para «{value}» en el corpus.")
        speaker = matches[0]["speaker"]
        note = ""
        if len(matches) > 1:
            note = "Otras coincidencias: " + ", ".join(
                f"{m['speaker']} ({m['n']})" for m in matches[1:6])
        ficha = diarios.speaker_ficha(con, speaker)
        frags = retrieve(question, cfg, _where(speaker=speaker, legislatura=leg), final_k) if question else []
        return Recap(kind, speaker, ficha, frags, question, (note + leg_note).strip())

    if kind == "partido":
        party = diarios.resolve_party(con, value)
        ficha = diarios.party_ficha(con, party)
        if not ficha["intervenciones"]:
            disponibles = ", ".join(p for p, _ in diarios.list_parties(con)[:12])
            return Recap(kind, party, ficha,
                         note=f"Sin datos para «{value}». Partidos disponibles: {disponibles}")
        note = f"(«{value}» → «{party}»)" if diarios.norm_key(value) != diarios.norm_key(party) else ""
        frags = retrieve(question, cfg, _where(party=party, legislatura=leg), final_k) if question else []
        return Recap(kind, party, ficha, frags, question, (note + leg_note).strip())

    if kind == "pleno":
        pid = value
        low = diarios.norm_key(value)
        if _NEWEST_RE.search(low):
            pid = diarios.latest_pleno(con) or value
        elif _OLDEST_RE.search(low):
            pid = diarios.earliest_pleno(con) or value
        ficha = diarios.pleno_ficha(con, pid)
        if ficha is None:
            return Recap(kind, value, {}, note=f"No tengo indexado el pleno «{pid}».")
        frags = retrieve(question, cfg, _where(pleno_id=pid), final_k) if question else []
        return Recap(kind, pid, ficha, frags, question)

    raise ValueError(f"kind desconocido: {kind!r}")


# expresiones que piden una lectura temporal por legislaturas
_EVOL_RE = re.compile(r"\b(evolucion|evolucionad|ha cambiad|han cambiad|a lo largo|"
                      r"con el tiempo|por legislatura|entre legislaturas|a traves de las legislaturas)")

_EVOLUTION_PROMPT = """Sujeto: {subject}
Tema: {topic}

Fragmentos del Diario de Sesiones agrupados POR LEGISLATURA (numerados):
{blocks}

Eres un analista parlamentario imparcial. Usando ÚNICAMENTE estos fragmentos, describe en
prosa NEUTRAL cómo ha evolucionado la posición de {subject} sobre «{topic}» a lo largo de
las legislaturas: recórrelas en orden, señalando continuidades y cambios de una a otra.
Atribuye cada idea a su legislatura, cita los fragmentos con su número [n], y si en alguna
legislatura no consta nada, indícalo. No añadas información externa, no valores y no inventes."""


def build_evolution(kind: str, value: str, cfg=None, con=None,
                    topic: str | None = None, per_leg_k: int = 3) -> tuple[Recap, str]:
    """Evolución de un candidato o partido por legislatura.

    Devuelve (Recap, resumen). La ficha (``ficha['evolucion']``) trae los agregados exactos
    por legislatura desde SQL; si se da un ``topic``, además recupera unos pocos fragmentos
    de cada legislatura (filtro entidad+legislatura) y el LLM redacta la evolución citando.
    Eficiencia: una consulta pequeña por legislatura (suelen ser 2-4) y una sola llamada al LLM.
    """
    cfg = cfg or load_config()
    con = con or connect()
    diarios.ensure_schema(con)
    per_leg_k = per_leg_k or getattr(cfg.retrieval, "final_k", 5)

    if kind == "candidato":
        matches = diarios.resolve_speaker(con, value)
        if not matches:
            return Recap("evolucion", value, {}, note=f"Sin coincidencias para «{value}»."), ""
        subject, field = matches[0]["speaker"], "speaker"
    else:
        subject, field = diarios.resolve_party(con, value), "party"

    evo = diarios.evolution_by_legislature(con, kind, subject)
    if not evo:
        return Recap("evolucion", subject, {}, note="Sin actividad registrada en el corpus."), ""

    # Un fragmento (al menos) por CADA legislatura en que la entidad intervino, para poder
    # comparar. Con tema: se recupera por ese tema; sin tema: un fragmento representativo
    # usando el asunto más frecuente de esa legislatura. Coste: una consulta pequeña por
    # legislatura (suelen ser 2-4) y una única llamada al LLM con todos los bloques.
    frags: list[dict] = []
    blocks: list[str] = []
    idx = 1
    for row in evo:
        leg = row["legislatura"]
        query = topic or (row["temas"][0] if row["temas"] else subject)
        k = per_leg_k if topic else 1
        hits = retrieve(query, cfg, _where(**{field: subject, "legislatura": leg}), k)
        if hits:
            lines = []
            for h in hits:
                lines.append(f"[{idx}] {h['text'].strip()}")
                frags.append(h)
                idx += 1
            blocks.append(f"Legislatura {leg}:\n" + "\n".join(lines))
        elif topic:                                   # deja constancia de la legislatura vacía
            blocks.append(f"Legislatura {leg}: (sin intervenciones sobre «{topic}»)")

    recap = Recap("evolucion", subject, {"evolucion": evo}, frags, topic or "evolución")
    summary = ""
    if blocks and getattr(cfg.llm, "enabled", False):
        tema_lbl = topic or "su actividad y posiciones"
        summary = _llm(_EVOLUTION_PROMPT.format(subject=subject, topic=tema_lbl,
                                                blocks="\n\n".join(blocks)), cfg, num_predict=600)
    return recap, summary


# ----------------------------------------------------------------- respuesta LLM

_ANSWER_PROMPT = """Tema o pregunta: {question}

Fragmentos del Diario de Sesiones (numerados):
{fragments}

Eres un analista parlamentario imparcial. Usando ÚNICAMENTE los fragmentos anteriores,
redacta un resumen COHERENTE y NEUTRAL (en prosa, no una lista):
- Sintetiza las ideas y posturas; no te limites a repetir o enumerar los fragmentos.
- Atribuye cada postura a quien la sostiene (orador o grupo).
- Si hay posiciones o matices distintos, recógelos; no homogeneices ni tomes partido.
- No añadas información externa, no valores y no inventes.
- Cita con su número los fragmentos en que te apoyas, p. ej. [1][3].
- Si todos los fragmentos son de un mismo grupo o persona, adviértelo al final: el
  resumen refleja solo esa fuente, no el conjunto del debate.
Si los fragmentos no permiten resumir, responde: «No consta en los fragmentos recuperados.»"""


def answer(recap: Recap, cfg=None) -> str:
    """Redacta un resumen fiel a partir de los fragmentos (requiere llm.enabled)."""
    cfg = cfg or load_config()
    if not recap.question or not recap.fragments or not getattr(cfg.llm, "enabled", False):
        return ""
    fragments = "\n\n".join(
        f"[{i}] ({h['meta'].get('speaker', '?')} · {h['meta'].get('party', '')} · "
        f"{h['meta'].get('pleno_id', '?')}): {h['text'][:800]}"
        for i, h in enumerate(recap.fragments, 1))
    return _llm(_ANSWER_PROMPT.format(question=recap.question, fragments=fragments), cfg)


# ----------------------------------------------------------------- resumen de un tema

_OVERVIEW_PROMPT = """Tema: {subject}

Fragmentos del Diario de Sesiones AGRUPADOS POR GRUPO PARLAMENTARIO (numerados):
{context}

Eres un analista parlamentario imparcial. Usando ÚNICAMENTE estos fragmentos, redacta un
resumen EQUILIBRADO de las posturas sobre el tema:
- Una síntesis breve por grupo parlamentario, con lo esencial de su posición.
- Contrasta las posiciones de forma neutral (coincidencias y discrepancias), sin tomar partido.
- Atribuye cada afirmación a su grupo y cítala con su número [n]. No opines ni añadas nada externo.
- No inventes posturas de grupos que no aparezcan en los fragmentos.
Cierra con una frase neutra sobre el grado de consenso o discrepancia observado."""


def topic_overview(subject: str, cfg=None, con=None, pool: int = 30,
                   per_party_k: int = 3, max_parties: int = 6,
                   leg: int | None = None) -> tuple[list[dict], str]:
    """Resumen equilibrado de un tema contrastando los grupos.

    Recupera un conjunto amplio del tema SIN filtrar por partido, reparte los mejores
    fragmentos entre los grupos que de verdad intervienen y deja que el LLM redacte una
    síntesis multilateral. Devuelve (grupos, texto_LLM); el texto va vacío sin LLM.
    ``leg`` limita el resumen a una legislatura concreta.
    """
    cfg = cfg or load_config()
    con = con or connect()
    diarios.ensure_schema(con)

    hits = retrieve(subject, cfg, _where(legislatura=leg), final_k=pool, pool=pool)
    by_party: dict[str, list] = {}
    for h in hits:
        by_party.setdefault(h["meta"].get("party") or "—", []).append(h)
    ordered = sorted(by_party.items(), key=lambda kv: len(kv[1]), reverse=True)[:max_parties]
    groups = [{"party": p, "fragments": frs[:per_party_k]} for p, frs in ordered]

    if not groups or not getattr(cfg.llm, "enabled", False):
        return groups, ""

    lines, idx = [], 1
    for g in groups:
        lines.append(f"\n## {g['party']}")
        for h in g["fragments"]:
            m = h["meta"]
            lines.append(f"[{idx}] ({m.get('speaker', '?')} · {m.get('pleno_id', '?')}): "
                         f"{h['text'][:700]}")
            idx += 1
    return groups, _llm(
        _OVERVIEW_PROMPT.format(subject=subject, context="\n".join(lines)), cfg)


# ----------------------------------------------------------------- por temáticas

def _entity_where(kind: str, value: str) -> dict:
    """Filtro de ChromaDB que aísla a la entidad de la recapitulación."""
    field = {"candidato": "speaker", "partido": "party", "pleno": "pleno_id"}[kind]
    return {field: value}


def _topics_of(recap: Recap) -> list[str]:
    """Temáticas de la entidad, ordenadas por relevancia, según la ficha."""
    temas = recap.ficha.get("temas", [])
    if recap.kind == "pleno":                 # en un pleno 'temas' es lista de cadenas
        return [t for t in temas if t]
    return [t for t, _ in temas if t]         # en candidato/partido es [(tema, n), ...]


def collect_by_topic(cfg, where_base: dict, topics: list[str],
                     per_topic_k: int = 4, pool_factor: int = 3) -> list[dict]:
    """Agrupa fragmentos del corpus por temática (filtrado exacto, sin LLM).

    Por cada tema recupera de ChromaDB los fragmentos de la entidad en ese tema y
    se queda con los ``per_topic_k`` más sustanciosos (los más largos del lote).
    """
    col = diarios.get_corpus_collection(cfg)
    groups = []
    for topic in topics:
        where = {"$and": [where_base, {"topic": topic}]}
        res = col.get(where=where, limit=max(per_topic_k * pool_factor, per_topic_k),
                      include=["documents", "metadatas"])
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        pairs = sorted(zip(docs, metas), key=lambda dm: len(dm[0]), reverse=True)[:per_topic_k]
        if pairs:
            groups.append({"topic": topic, "n": len(docs),
                           "fragments": [{"text": d, "meta": m} for d, m in pairs]})
    return groups


def _thematic_context(groups: list[dict], max_chars: int = 600) -> str:
    """Contexto agrupado por temática con numeración global para citar."""
    lines, idx = [], 1
    for g in groups:
        lines.append(f"\n## {g['topic']}")
        for fr in g["fragments"]:
            m = fr["meta"]
            lines.append(f"[{idx}] ({m.get('speaker', '?')} · {m.get('pleno_id', '?')}): "
                         f"{fr['text'][:max_chars]}")
            idx += 1
    return "\n".join(lines)


_TOPIC_PROMPT = """Entidad: {title} (tipo: {kind})

Fragmentos del Diario de Sesiones AGRUPADOS POR TEMÁTICA (cada fragmento va numerado):
{context}

Eres un analista parlamentario. Redacta en español un RESUMEN POR TEMÁTICAS: por cada
temática del listado, una o dos frases que sinteticen de forma neutral y fiel lo que
dicen sus fragmentos. Usa SOLO esa información (no inventes ni opines), respeta el orden
de las temáticas y cita los fragmentos empleados con su número [n]. Si una temática no
aporta contenido claro, indícalo en una línea."""


def summarize_by_topic(recap: Recap, cfg=None, max_topics: int = 6,
                       per_topic_k: int = 4) -> tuple[list[dict], str]:
    """Resumen por temáticas de la entidad. Devuelve (grupos, texto_LLM).

    El texto del LLM va vacío si ``llm.enabled`` es falso o si no hay material; en ese
    caso los ``grupos`` siguen sirviendo para mostrar los fragmentos agrupados por tema.
    """
    cfg = cfg or load_config()
    groups = collect_by_topic(cfg, _entity_where(recap.kind, recap.title),
                              _topics_of(recap)[:max_topics], per_topic_k)
    if not groups or not getattr(cfg.llm, "enabled", False):
        return groups, ""
    prompt = _TOPIC_PROMPT.format(title=recap.title, kind=recap.kind,
                                  context=_thematic_context(groups))
    return groups, _llm(prompt, cfg)


# ----------------------------------------------------------------- lenguaje natural

# Expresiones temporales y de número de pleno (deterministas, no dependen del LLM).
_NUM_RE = re.compile(r"\b(?:pleno|sesion)\s+(?:n[ºo]?\s*)?(\d{1,4})\b")
_LEG_RE = re.compile(r"\blegislatura\s+(\d{1,2})\b")
_NEWEST_RE = re.compile(r"\b(ultim[oa]|mas reciente|reciente|mas nuev[oa])\b")
_OLDEST_RE = re.compile(r"\b(primer[oa]?|mas antigu[oa]|mas viej[oa]|inicial)\b")


def _route_temporal(query: str) -> dict:
    """Extrae {orden, num, leg} de la pregunta (último/primero, nº de pleno, legislatura)."""
    k = diarios.norm_key(query)
    num = _NUM_RE.search(k)
    leg = _LEG_RE.search(k)
    orden = "reciente" if _NEWEST_RE.search(k) else ("antiguo" if _OLDEST_RE.search(k) else None)
    return {"orden": orden,
            "num": int(num.group(1)) if num else None,
            "leg": int(leg.group(1)) if leg else None}


def _resolve_temporal_pleno(query: str, con) -> str | None:
    """Resuelve la pregunta a un id de pleno si menciona nº+legislatura o último/primero."""
    t = _route_temporal(query)
    if t["num"] is not None:
        pid = diarios.pleno_by_number(con, t["leg"], t["num"])
        if pid:
            return pid
    if t["orden"] == "reciente":
        return diarios.latest_pleno(con, t["leg"])
    if t["orden"] == "antiguo":
        return diarios.earliest_pleno(con, t["leg"])
    return None


_ROUTER_PROMPT = """Eres un enrutador de consultas para un buscador de Diarios de Sesiones del Congreso.
A partir de la pregunta del usuario, extrae los filtros y devuélvelos en JSON con estas
claves EXACTAS (usa null cuando no aplique):
  "partido"   : grupo/partido mencionado (p. ej. "Vox", "PSOE"); null si no se cita
  "candidato" : nombre de una persona concreta; null si solo se habla de un grupo
  "pleno"     : identificador de sesión tipo "DSCD-11-PL-2"; null si no aparece
  "tema"      : el asunto concreto sobre el que se pregunta (p. ej. "aborto", "vivienda")

Partidos disponibles: {parties}.
Devuelve SOLO el JSON, sin explicaciones y sin ```.

Pregunta: {query}"""

_KEYS = ("partido", "candidato", "pleno", "tema")


def _extract_json(text: str) -> dict | None:
    """Extrae el primer objeto JSON del texto del LLM, tolerante a ruido/```."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return {k: (data.get(k) or None) for k in _KEYS}


def _route_heuristic(query: str) -> dict:
    """Enrutado sin LLM: detecta partido y pleno por reglas; el tema es el texto."""
    m = re.search(r"DSCD-\d+-PL-\d+", query, re.IGNORECASE)
    tema = query.split(":", 1)[-1] if ":" in query else query
    tema = tema.strip(" ¿?¡!.\t\n")
    return {
        "partido": diarios.detect_party(query),
        "candidato": None,
        "pleno": m.group(0).upper() if m else None,
        "tema": tema or None,
    }


# ----------------------------------------------------------------- guardarraíl

_MSG_OFFTOPIC = (
    "Solo puedo responder preguntas relacionadas con la actividad política y "
    "parlamentaria del Congreso (leyes, debates, posturas de los grupos, sesiones…). "
    "Tu pregunta no parece encajar en ese ámbito, así que no puedo responderla."
)
_MSG_OPINION = (
    "No puedo responder a ese tipo de pregunta: me pides una valoración o un "
    "posicionamiento sobre un partido o un político. Mi función es resumir de forma "
    "neutral lo que se dijo en los Diarios de Sesiones, citando las fuentes, no emitir "
    "juicios. Puedes reformularla de forma neutral, p. ej.: «¿qué se ha dicho sobre la "
    "corrupción del partido X?»."
)

# Patrones que piden al modelo TOMAR PARTIDO o juzgar (siempre se bloquean).
_PARTISAN_PATTERNS = [
    r"(mas|menos) (corrupto|corrupta|honesto|honrado|honrada|mentiroso|mentirosa|"
    r"ladron|ladrona|incompetente|fiable|creible|culpable|peligroso|peligrosa)",
    r"(mejor|peor) (partido|grupo|lider|politic[oa]|president[ea])",
    r"que (partido|grupo|politic[oa]) es (el |la )?(mas|mejor|peor)",
    r"(a|por) quien (deberia |hay que |habria que )?(votar|votaria)",
    r"que (partido|grupo) (deberia |habria que )?votar",
    r"quien (miente|tiene razon|es mejor|es peor|es el mejor|es el peor|es mas)",
    r"\b(que opinas|que piensas|en tu opinion|tu opinion|que te parece|crees que es)\b",
]

# Señales de que la pregunta SÍ es de ámbito político/parlamentario.
_POLITICAL_HINTS = (
    "polit gobierno congreso senado pleno diput minist president partido grupo "
    "ley leyes decreto presupuest enmienda mocion investidura parlament vot escaño "
    "oposicion coalicion constitucion reforma referendum amnistia legislatura sesion "
    "sanidad vivienda educacion inmigracion migra refugiad aborto pension impuesto "
    "fiscal autonomi estado nacion estatuto comparecencia interpelacion proposicion "
    "debate empleo paro salario energia clima ambiente igualdad genero violencia "
    "terrorismo seguridad independencia catalun euskadi otan ucrania europe okupa "
    "corrupcion economia deficit deuda subvencion"
).split()


def _looks_partisan(question: str) -> bool:
    k = diarios.norm_key(question)
    return any(re.search(p, k) for p in _PARTISAN_PATTERNS)


def _looks_political(question: str) -> bool:
    k = diarios.norm_key(question)
    if diarios.detect_party(question):
        return True
    return any(h in k for h in _POLITICAL_HINTS)


_CLASSIFY_PROMPT = """Clasifica la siguiente consulta de un usuario en EXACTAMENTE una etiqueta:

- POLITICA_OK: trata de política o de la actividad parlamentaria (leyes, debates, posturas
  que defienden los grupos, sesiones, gestión pública) y se puede responder de forma neutral.
- FUERA_DE_TEMA: no trata de política ni de la actividad parlamentaria.
- OPINION_PARTIDISTA: pide valorar, juzgar, rankear o tomar partido sobre partidos o
  políticos (cuál es el mejor/peor/más corrupto, a quién votar, quién tiene razón).

Responde SOLO con la etiqueta, sin nada más.

Consulta: {q}"""


def _classify_llm(question: str, cfg) -> str:
    out = _llm(_CLASSIFY_PROMPT.format(q=question), cfg, num_predict=12).upper()
    for label in ("OPINION_PARTIDISTA", "FUERA_DE_TEMA", "POLITICA_OK"):
        if label in out:
            return label
    return "POLITICA_OK"   # ante la duda, no bloquear el tema


def guard_query(question: str, cfg) -> tuple[str, str]:
    """Decide si la pregunta es admisible. Devuelve (veredicto, mensaje).

    veredicto: 'ok' | 'off_topic' | 'opinion'. El mensaje va vacío salvo rechazo.

    Estrategia (robusta frente a modelos pequeños poco fiables):
      1. Patrón claro de posicionamiento partidista -> se bloquea SIEMPRE.
      2. Si hay señal política evidente (un partido o vocabulario parlamentario) y no es
         partidista -> se ACEPTA, sin molestar al LLM (evita falsos rechazos del tipo
         '¿qué opina VOX sobre la inmigración?').
      3. Solo cuando no hay ninguna señal política se recurre al LLM (si está activo) para
         distinguir tema de fuera-de-tema; sin LLM, se considera fuera de tema.
    """
    if _looks_partisan(question):
        return "opinion", _MSG_OPINION
    if _looks_political(question):
        return "ok", ""
    if getattr(cfg.llm, "enabled", False):
        label = _classify_llm(question, cfg)
        if label == "OPINION_PARTIDISTA":
            return "opinion", _MSG_OPINION
        if label == "POLITICA_OK":
            return "ok", ""
        return "off_topic", _MSG_OFFTOPIC
    return "off_topic", _MSG_OFFTOPIC


def route_query(query: str, cfg, con) -> dict:
    """Convierte la pregunta libre en filtros {partido, candidato, pleno, tema}.

    Usa el LLM si está activado (más fino: entiende 'los de Vox', sinónimos…) y, si no,
    cae a un enrutado heurístico para que la función siga operativa sin LLM.
    """
    if getattr(cfg.llm, "enabled", False):
        parties = ", ".join(p for p, _ in diarios.list_parties(con)[:20]) or "—"
        parsed = _extract_json(_llm(
            _ROUTER_PROMPT.format(parties=parties, query=query), cfg, num_predict=200))
        if parsed:
            return parsed
    return _route_heuristic(query)


def ask(query: str, cfg=None, con=None, final_k: int | None = None) -> tuple[dict, Recap, str]:
    """Flujo completo en lenguaje natural: estructura la query -> busca -> responde.

    Devuelve (filtros_interpretados, recap, respuesta_LLM). El LLM interviene dos veces:
    primero para estructurar la pregunta y después para redactar la respuesta fiel.
    Antes de nada, un guardarraíl rechaza lo que no sea política o lo que pida un
    posicionamiento del modelo sobre un partido/político.
    """
    cfg = cfg or load_config()
    con = con or connect()
    diarios.ensure_schema(con)
    final_k = final_k or getattr(cfg.retrieval, "final_k", 5)

    verdict, msg = guard_query(query, cfg)
    if verdict != "ok":
        return {"rechazo": verdict}, Recap("rechazo", query, {}, [], query, note=msg), ""

    parsed = route_query(query, cfg, con)
    subject = parsed.get("tema") or query

    # ¿pide la evolución por legislaturas de un partido o candidato?
    if _EVOL_RE.search(diarios.norm_key(query)) and (parsed.get("candidato") or parsed.get("partido")):
        kind = "candidato" if parsed.get("candidato") else "partido"
        topic = parsed.get("tema")
        recap, summary = build_evolution(kind, parsed[kind], cfg, con, topic)
        parsed["evolucion"] = True
        return parsed, recap, summary

    pid = _resolve_temporal_pleno(query, con) or parsed.get("pleno")
    if pid:
        parsed["pleno"] = pid

    # legislatura suelta ("en la legislatura 14"): filtra la recuperación a esa legislatura.
    # No se aplica si ya hay un pleno concreto (ese pleno ya fija su legislatura).
    leg = None if parsed.get("pleno") else _route_temporal(query)["leg"]
    if leg:
        parsed["legislatura"] = leg

    if parsed.get("pleno"):
        recap = build_recap("pleno", parsed["pleno"], cfg, con, subject, final_k)
    elif parsed.get("candidato"):
        recap = build_recap("candidato", parsed["candidato"], cfg, con, subject, final_k, leg=leg)
    elif parsed.get("partido"):
        recap = build_recap("partido", parsed["partido"], cfg, con, subject, final_k, leg=leg)
    else:                                            # sin entidad: búsqueda global
        frags = retrieve(subject, cfg, _where(legislatura=leg), final_k) if subject else []
        recap = Recap("global", subject, {}, frags, subject,
                      note=(f"Fragmentos limitados a la legislatura {leg}." if leg else ""))

    recap.question = subject                         # answer() responde sobre el tema
    return parsed, recap, answer(recap, cfg)


# ----------------------------------------------------------------- presentación

def _rows(pairs, sep=" · ") -> str:
    return sep.join(f"{name} ({n})" for name, n in pairs) or "—"


def format_ficha(recap: Recap) -> str:
    f = recap.ficha
    out = ["=" * 70]
    if recap.kind == "evolucion" and f.get("evolucion"):
        out.append(f"EVOLUCIÓN POR LEGISLATURA · {recap.title}")
        for r in f["evolucion"]:
            temas = ", ".join(r["temas"]) or "—"
            out.append(
                f"  Legislatura {r['legislatura']}: {r['n']} intervenciones · "
                f"{r['plenos']} plenos · {r['fecha_min'] or '?'} → {r['fecha_max'] or '?'}")
            out.append(f"      Temas: {temas}")
    elif recap.kind == "candidato" and f:
        out += [
            f"CANDIDATO/A · {f['speaker']}",
            f"  Intervenciones: {f['intervenciones']}  ·  Plenos: {f['plenos']}  ·  "
            f"Palabras: {f['palabras']:,}",
            f"  Periodo: {f['desde'] or '?'} → {f['hasta'] or '?'}",
            f"  Grupo(s): {_rows(f['partidos'])}",
            f"  Temas frecuentes: {_rows(f['temas'])}",
            f"  Plenos recientes: " + ", ".join(f"{p} ({d or '?'})" for p, d in f['plenos_recientes']),
        ]
    elif recap.kind == "partido" and f.get("intervenciones"):
        out += [
            f"PARTIDO · {f['partido']}",
            f"  Intervenciones: {f['intervenciones']}  ·  Plenos: {f['plenos']}  ·  "
            f"Oradores: {f['oradores']}  ·  Palabras: {f['palabras']:,}",
            f"  Periodo: {f['desde'] or '?'} → {f['hasta'] or '?'}",
            f"  Oradores principales: {_rows(f['oradores_top'])}",
            f"  Temas frecuentes: {_rows(f['temas'])}",
        ]
    elif recap.kind == "pleno" and f:
        oradores = " · ".join(f"{s} ({n})" for s, n, _ in f["oradores_principales"]) or "—"
        out += [
            f"PLENO · {f['pleno_id']}  (legislatura {f['legislatura']}, {f['fecha']})",
            f"  Tema: {f['tema_sesion']}",
            f"  Intervenciones: {f['intervenciones']}  ·  Votaciones: {f['n_votaciones']}",
            f"  Reparto por grupo: {_rows(f['reparto_partidos'])}",
            f"  Oradores principales: {oradores}",
            f"  Temas: " + (", ".join(f["temas"]) or "—"),
        ]
        for i, v in enumerate(f.get("votaciones", []), 1):
            out.append(f"  Votación {i}: {v.get('a_favor', '?')} a favor · "
                       f"{v.get('en_contra', '?')} en contra · {v.get('abstenciones', '?')} abstenciones")
    else:
        out.append(f"{recap.kind.upper()} · {recap.title}")
    out.append("=" * 70)
    return "\n".join(out)


def _print_fragments_and_answer(recap: Recap, cfg, precomputed: str | None = None) -> None:
    """Imprime los fragmentos recuperados y la respuesta del LLM (o un aviso)."""
    if not recap.fragments:
        print("\nSin fragmentos: ¿has indexado el corpus? "
              "(python scripts/ingest_diarios.py --dir ...)")
        return
    print(f"\nFragmentos relevantes para «{recap.question}»:")
    for i, h in enumerate(recap.fragments, 1):
        m = h["meta"]
        pid = m.get("pleno_id", "")
        fecha = m.get("fecha_iso", "")
        cab = f"\n[{i}] {m.get('speaker', '?')} · {m.get('party', '')} · {pid}"
        if fecha:
            cab += f" · {fecha}"
        print(cab)
        url = diarios.diario_url(pid)
        if url:
            print(f"    Diario oficial: {url}")
        print("    " + h["text"][:300].strip() + "…")
    resp = precomputed if precomputed is not None else answer(recap, cfg)
    if resp:
        print("\nRespuesta (LLM, solo con los fragmentos):\n" + resp)
    else:
        print("\n(LLM desactivado: pon `llm.enabled: true` en config.yaml para la respuesta redactada.)")


def _print_thematic(recap: Recap, cfg, max_topics: int) -> None:
    groups, resumen = summarize_by_topic(recap, cfg, max_topics=max_topics)
    if not groups:
        print("\nSin material por temáticas: ¿has indexado el corpus? "
              "(python scripts/ingest_diarios.py --dir ...)")
        return
    print("\nMaterial agrupado por temáticas:")
    for g in groups:
        print(f"\n▸ {g['topic']}  ({g['n']} fragmentos)")
        for fr in g["fragments"][:2]:
            print("    · " + fr["text"][:200].strip() + "…")
    if resumen:
        print("\nResumen por temáticas (LLM, solo con los fragmentos):\n" + resumen)
    else:
        print("\n(LLM desactivado: pon `llm.enabled: true` en config.yaml para el resumen redactado.)")


def _emit_partidos(cfg, con) -> None:
    rows = diarios.list_parties(con)
    print(f"{len(rows)} partidos en el corpus:")
    for party, n in rows:
        print(f"  {party:34} {n:>7} intervenciones")


def _emit_tema(subject, cfg, con, per_grupo=3, max_grupos=6, leg=None) -> None:
    verdict, msg = guard_query(subject, cfg)
    if verdict != "ok":
        print(msg)
        return
    groups, resumen = topic_overview(subject, cfg, con,
                                     per_party_k=per_grupo, max_parties=max_grupos, leg=leg)
    if not groups:
        print("\nSin material sobre el tema: ¿has indexado los embeddings? "
              "(python scripts/ingest_diarios.py --dir ... --embed-only)")
        return
    cab = f"Tema: {subject}" + (f" (legislatura {leg})" if leg else "")
    print(cab + "\nGrupos que intervienen sobre el tema:")
    for g in groups:
        print(f"\n▸ {g['party']}  ({len(g['fragments'])} fragmentos)")
        for h in g["fragments"][:1]:
            print("    · " + h["text"][:180].strip() + "…")
    if resumen:
        print("\nResumen equilibrado por grupos (LLM, solo con los fragmentos):\n" + resumen)
    else:
        print("\n(LLM desactivado: pon `llm.enabled: true` en config.yaml para el resumen redactado.)")


def _emit_ask(query, cfg, con, k=None) -> None:
    parsed, recap, resp = ask(query, cfg, con, final_k=k)
    if "rechazo" in parsed:                          # guardarraíl: pregunta no admisible
        print(recap.note)
        return
    shown = {key: val for key, val in parsed.items() if val}
    print("Consulta interpretada:", shown or "(búsqueda global)")
    if recap.ficha:
        print(format_ficha(recap))
    if recap.note:
        print(recap.note)
    if recap.kind == "evolucion":
        if recap.fragments:
            _print_fragments_and_answer(recap, cfg, precomputed=resp)
        elif recap.question:
            print("\n(Sin fragmentos para ese tema en las legislaturas del sujeto.)")
        return
    _print_fragments_and_answer(recap, cfg, precomputed=resp)


def _emit_evolution(kind, value, cfg, con, topic=None, per_leg=3) -> None:
    if topic:
        verdict, msg = guard_query(topic, cfg)
        if verdict != "ok":
            print(msg)
            return
    recap, summary = build_evolution(kind, value, cfg, con, topic, per_leg)
    print(format_ficha(recap))
    if recap.note:
        print(recap.note)
    if recap.fragments:
        _print_fragments_and_answer(recap, cfg, precomputed=summary)
    elif topic:
        print("\n(Sin fragmentos para ese tema en las legislaturas del sujeto.)")


def _emit_structured(kind, value, cfg, con, query=None, k=None, temas=False, max_temas=6, leg=None) -> None:
    if query:
        verdict, msg = guard_query(query, cfg)
        if verdict != "ok":
            print(msg)
            return
    recap = build_recap(kind, value, cfg, con, question=query, final_k=k, leg=leg)
    print(format_ficha(recap))
    if recap.note:
        print(recap.note)
    if temas and recap.ficha:
        _print_thematic(recap, cfg, max_temas)
    if recap.question:
        _print_fragments_and_answer(recap, cfg)


def _repl(cfg, con) -> None:
    """Modo interactivo: carga los modelos UNA vez y atiende muchas consultas seguidas."""
    print("Cargando modelos (una sola vez)…", flush=True)
    from .index import get_embedder
    get_embedder(cfg)
    _get_reranker(cfg)
    print("Listo. Escribe tu consulta y pulsa Enter. Comandos: 'tema: <asunto>', "
          "'partidos', 'salir'.\nCualquier otra cosa se interpreta como pregunta libre (ask).")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in ("salir", "exit", "quit"):
            break
        low = q.lower()
        try:
            if low == "partidos":
                _emit_partidos(cfg, con)
            elif low.startswith("tema:"):
                _emit_tema(q.split(":", 1)[1].strip(), cfg, con)
            else:
                _emit_ask(q, cfg, con)
        except Exception as exc:                     # no tumbar la sesión por un fallo puntual
            print(f"[error] {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Buscador inteligente del corpus de Diarios.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # modo interactivo (recomendado para muchas consultas: no recarga modelos)
    sub.add_parser("repl", help="sesión interactiva; carga los modelos una sola vez")

    # consulta en lenguaje natural: el LLM la estructura por sí solo
    p_ask = sub.add_parser("ask", help="pregunta libre; el LLM la estructura (partido/candidato/pleno/tema)")
    p_ask.add_argument("query")
    p_ask.add_argument("-k", type=int, default=None, help="nº de fragmentos a recuperar")

    # listar los partidos realmente presentes en el corpus
    sub.add_parser("partidos", help="lista los partidos disponibles en el corpus")

    # resumen equilibrado de un tema contrastando los grupos
    p_tema = sub.add_parser("tema", help="resumen neutral de un tema contrastando los grupos")
    p_tema.add_argument("subject")
    p_tema.add_argument("--per-grupo", type=int, default=3, help="fragmentos por grupo")
    p_tema.add_argument("--max-grupos", type=int, default=6, help="nº máximo de grupos")
    p_tema.add_argument("--leg", type=int, default=None, help="limitar a una legislatura")

    # evolución por legislatura de un candidato o partido
    p_evo = sub.add_parser("evolucion", help="evolución por legislatura de un candidato o partido")
    p_evo.add_argument("kind", choices=["candidato", "partido"])
    p_evo.add_argument("value", help="nombre del candidato o partido")
    p_evo.add_argument("-q", "--query", default=None, help="tema para describir la evolución de la postura")
    p_evo.add_argument("--per-leg", type=int, default=3, help="fragmentos por legislatura")

    # fichas estructuradas (deterministas)
    for kind in ("candidato", "partido", "pleno"):
        p = sub.add_parser(kind, help=f"ficha de {kind}")
        p.add_argument("value", help="nombre del candidato/partido o id del pleno")
        p.add_argument("-q", "--query", default=None, help="pregunta para la búsqueda semántica")
        p.add_argument("-k", type=int, default=None, help="nº de fragmentos a recuperar")
        p.add_argument("--temas", action="store_true", help="resumen por temáticas de la entidad")
        p.add_argument("--max-temas", type=int, default=6, help="nº máximo de temáticas a resumir")
        p.add_argument("--leg", type=int, default=None, help="limitar los fragmentos a una legislatura")

    args = ap.parse_args()
    cfg = load_config()
    con = connect()

    if args.cmd == "repl":
        _repl(cfg, con)
    elif args.cmd == "partidos":
        _emit_partidos(cfg, con)
    elif args.cmd == "tema":
        _emit_tema(args.subject, cfg, con, args.per_grupo, args.max_grupos, leg=args.leg)
    elif args.cmd == "ask":
        _emit_ask(args.query, cfg, con, k=args.k)
    elif args.cmd == "evolucion":
        _emit_evolution(args.kind, args.value, cfg, con, topic=args.query, per_leg=args.per_leg)
    else:                                            # candidato / partido / pleno
        _emit_structured(args.cmd, args.value, cfg, con, query=args.query,
                         k=args.k, temas=args.temas, max_temas=args.max_temas, leg=args.leg)
    con.close()


if __name__ == "__main__":
    main()
