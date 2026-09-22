"""Alertas ciudadanas: un vecino se suscribe a TEMAS de un catálogo cerrado y, cuando
su ayuntamiento trata uno en un pleno, recibe un correo con las citas literales
(quién lo dijo), el minuto exacto del vídeo y el acta.

Decisiones de diseño (ver dossier):
- Catálogo CERRADO de temas, nunca texto libre: la detección es calibrable y es
  imposible por construcción suscribirse a una persona (privacidad por diseño).
- Detección semántica con BGE-M3 (frases-ancla -> centroide por tema), sin regex.
- Todo extractivo: el correo solo lleva citas literales con su orador etiquetado.
- Doble opt-in y baja en un clic. Sin SMTP configurado, los correos van a la
  "bandeja de demostración" (tabla alerta_envio) que la pestaña Alertas enseña.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import os
import uuid

import numpy as np

from . import db
from .config import load_config, resolve_path
from .index import get_collection, get_embedder

# --------------------------------------------------------------------- catálogo
# Cada tema lleva frases-ancla en el registro real de un pleno municipal; el
# centroide de sus embeddings define el tema. Añadir un tema = añadir anclas.
TEMAS: dict[str, list[str]] = {
    "vivienda": [
        "el precio del alquiler y el acceso a la vivienda",
        "promoción de vivienda pública y vivienda protegida",
        "desahucios y ayudas al alquiler para familias vulnerables",
    ],
    "urbanismo y obras": [
        "licencias de obra y planeamiento urbanístico",
        "obras en calles y aceras del municipio",
        "el plan general de ordenación urbana y la recalificación de terrenos",
    ],
    "impuestos y tasas": [
        "la subida o bajada del IBI y de los impuestos municipales",
        "las tasas por recogida de basura y por servicios municipales",
        "bonificaciones fiscales para vecinos y comercios",
    ],
    "presupuestos": [
        "la aprobación del presupuesto municipal del ejercicio",
        "modificaciones de crédito y remanente de tesorería",
        "la liquidación del presupuesto y el plan de ajuste",
    ],
    "fiestas y cultura": [
        "las fiestas patronales y la programación cultural",
        "subvenciones a las comisiones de fiestas y asociaciones culturales",
        "actividades culturales, conciertos y la feria del municipio",
    ],
    "deportes": [
        "las instalaciones deportivas y el polideportivo municipal",
        "subvenciones a los clubes deportivos del municipio",
        "escuelas deportivas y actividades para jóvenes",
    ],
    "educación": [
        "los colegios públicos y las escuelas infantiles del municipio",
        "becas y ayudas escolares para las familias",
        "el mantenimiento de los centros educativos",
    ],
    "medio ambiente": [
        "la protección del medio ambiente y los espacios naturales",
        "arbolado, parques y jardines del municipio",
        "eficiencia energética y energías renovables en edificios municipales",
    ],
    "agua y residuos": [
        "el servicio municipal de agua potable y el alcantarillado",
        "la recogida de basuras y la gestión de residuos",
        "la limpieza viaria del municipio",
    ],
    "movilidad y tráfico": [
        "el tráfico, los aparcamientos y las zonas peatonales",
        "el transporte público y los autobuses del municipio",
        "carriles bici y seguridad vial en las calles",
    ],
    "seguridad": [
        "la policía local y la seguridad ciudadana",
        "robos y vandalismo en el municipio",
        "protección civil y emergencias",
    ],
    "servicios sociales": [
        "las ayudas sociales a familias vulnerables",
        "la atención a mayores y la dependencia",
        "servicios sociales municipales e inclusión",
    ],
    "empleo": [
        "planes de empleo y bolsas de trabajo municipales",
        "el fomento del empleo local y ayudas a la contratación",
        "cursos de formación para desempleados",
    ],
    "sanidad": [
        "el centro de salud y la atención sanitaria en el municipio",
        "la petición de más médicos y pediatras",
        "salud pública y campañas de prevención",
    ],
    "participación ciudadana": [
        "los presupuestos participativos y las consultas a los vecinos",
        "el reglamento de participación ciudadana",
        "asociaciones de vecinos y consejos de barrio",
    ],
}

# Umbral de similitud tema-fragmento (coseno BGE-M3), calibrado con plenos reales
# (scripts/calibrar_alertas.py, jul-2026): los positivos verdaderos midieron 0.57-0.64
# (p. ej. vivienda 0.640 en el pleno del alquiler) y el ruido quedó en 0.45-0.56.
# _MIN_CHARS filtra interjecciones ("El miércoles, el miércoles." daba 0.55 por azar).
UMBRAL = 0.57
_MIN_CHARS = 120
_MIN_CHUNKS = 1
_TOP_CITAS = 3

# Suscripción especial: recibir TODOS los plenos nuevos (boletín), sin filtro de tema.
# El correo lleva además el índice de temas detectados con su minuto.
TODOS = "todos los plenos"

_CENT = {"m": None}                                    # centroides cacheados (proceso)


# ------------------------------------------------------------------- embeddings
def _centroides(cfg) -> dict[str, np.ndarray]:
    if _CENT["m"] is None:
        emb = get_embedder(cfg)
        m = {}
        for tema, frases in TEMAS.items():
            v = emb.encode(frases, normalize_embeddings=True).mean(axis=0)
            m[tema] = v / np.linalg.norm(v)
        _CENT["m"] = m
    return _CENT["m"]


def _chunks_pleno(video_id: str, cfg) -> list[dict]:
    """Fragmentos del pleno con orador, segundo y embedding.
    Primero intenta el índice (embeddings gratis); si el pleno no está indexado
    (p. ej. municipios), trocea el transcript y embebe al vuelo."""
    col = get_collection(cfg)
    r = col.get(where={"video_id": video_id}, include=["metadatas", "documents", "embeddings"])
    if r["ids"]:
        out = []
        for doc, m, e in zip(r["documents"], r["metadatas"], r["embeddings"]):
            out.append({"text": doc, "speaker": (m.get("speaker") or "").strip(),
                        "party": "", "start": float(m.get("start") or 0),
                        "emb": np.asarray(e) / (np.linalg.norm(e) or 1)})
        return out

    import json
    p = resolve_path(f"data/transcripts/{video_id}.json")
    if not p.exists():
        return []
    segs = json.loads(p.read_text(encoding="utf-8")).get("segments", [])
    # troceo propio para conservar name/party (el etiquetado humano o por huella)
    chunks, cur, cur_len = [], [], 0
    def _emit(c):
        who = (c[0].get("name") or "").strip() or (c[0].get("speaker") or "").strip()
        chunks.append({"text": " ".join(s["text"].strip() for s in c),
                       "speaker": who, "party": (c[0].get("party") or "").strip(),
                       "start": float(c[0]["start"])})
    for s in segs:
        t = (s.get("text") or "").strip()
        if not t:
            continue
        if cur and (s.get("speaker") != cur[0].get("speaker") or cur_len + len(t) > 900):
            _emit(cur); cur, cur_len = [], 0
        cur.append(s); cur_len += len(t) + 1
    if cur:
        _emit(cur)
    if not chunks:
        return []
    emb = get_embedder(cfg)
    vecs = emb.encode([c["text"] for c in chunks], normalize_embeddings=True)
    for c, v in zip(chunks, vecs):
        c["emb"] = v
    return chunks


def detectar(video_id: str, temas: list[str] | None = None,
             cfg=None, umbral: float | None = None) -> dict[str, list[dict]]:
    """{tema: [citas]} con las citas (texto, orador, segundo, sim) que superan el
    umbral en este pleno, mejores primero. Solo temas del catálogo."""
    cfg = cfg or load_config()
    umbral = umbral if umbral is not None else UMBRAL
    temas = [t for t in (temas or TEMAS) if t in TEMAS]
    chunks = [c for c in _chunks_pleno(video_id, cfg) if len(c["text"]) >= _MIN_CHARS]
    if not chunks:
        return {}
    M = np.stack([c["emb"] for c in chunks])
    cent = _centroides(cfg)
    out = {}
    for tema in temas:
        sims = M @ cent[tema]
        idx = [i for i in np.argsort(-sims) if sims[i] >= umbral]
        if len(idx) >= _MIN_CHUNKS:
            # las mejores _TOP_CITAS por relevancia, pero presentadas en orden de
            # tiempo: lo que el vecino quiere es DÓNDE EMPIEZA a tratarse su tema
            top = sorted(idx[:_TOP_CITAS], key=lambda i: chunks[i]["start"])
            out[tema] = [{"text": chunks[i]["text"], "speaker": chunks[i]["speaker"],
                          "party": chunks[i]["party"], "start": chunks[i]["start"],
                          "sim": float(sims[i])} for i in top]
    return out


# ------------------------------------------------------------ BD de suscripción
_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerta_sub (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidad_id INTEGER NOT NULL REFERENCES entidad(id),
  email TEXT NOT NULL,
  tema TEXT NOT NULL,
  confirmado INTEGER DEFAULT 0,
  token TEXT,
  creada TEXT,
  UNIQUE(entidad_id, email, tema)
);
CREATE TABLE IF NOT EXISTS alerta_envio (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidad_id INTEGER,
  video_id TEXT,
  email TEXT,
  temas TEXT,
  asunto TEXT,
  html TEXT,
  tipo TEXT,
  enviada TEXT
);
"""


def _con():
    con = db.connect()
    con.executescript(_SCHEMA)
    return con


def suscribir(email: str, entidad_id: int, temas: list[str]) -> dict:
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return {"error": "correo no válido"}
    temas = [t for t in temas if t in TEMAS or t == TODOS]
    if not temas:
        return {"error": "elige al menos un tema del catálogo"}
    token = uuid.uuid4().hex
    ahora = _dt.date.today().isoformat()
    con = _con()
    for t in temas:
        con.execute(
            "INSERT INTO alerta_sub(entidad_id,email,tema,confirmado,token,creada) "
            "VALUES(?,?,?,0,?,?) ON CONFLICT(entidad_id,email,tema) "
            "DO UPDATE SET token=excluded.token",
            (entidad_id, email, t, token, ahora))
    con.commit()
    ent = next((e for e in db.list_entidades(con) if e["id"] == entidad_id), {})
    html_conf = _render_confirmacion(ent.get("nombre", ""), temas, token)
    asunto = "Confirma tu suscripción a las alertas del pleno"
    _guardar_envio(con, entidad_id, "", email, ", ".join(temas), asunto, html_conf, "confirmacion")
    con.close()
    _smtp_send(email, asunto, html_conf)
    return {"ok": True, "temas": temas, "token": token}


def confirmar(token: str) -> dict:
    con = _con()
    fila = con.execute(
        "SELECT email, entidad_id, GROUP_CONCAT(tema, '|') AS temas FROM alerta_sub "
        "WHERE token=? GROUP BY email, entidad_id", (token,)).fetchone()
    # solo la PRIMERA confirmación dispara la bienvenida (reabrir el enlace no reenvía)
    n = con.execute("UPDATE alerta_sub SET confirmado=1 WHERE token=? AND confirmado=0",
                    (token,)).rowcount
    con.commit(); con.close()
    if fila and n > 0:
        import threading
        threading.Thread(target=_bienvenida, daemon=True,
                         args=(fila["email"], fila["entidad_id"],
                               fila["temas"].split("|"), token)).start()
    return {"ok": fila is not None, "confirmadas": n}


def _bienvenida(email: str, entidad_id: int, temas: list[str], token: str) -> None:
    """Al confirmar: correo inmediato con lo último que se dijo de sus temas en el
    pleno más reciente ya procesado (si no se trataron, bienvenida simple)."""
    try:
        cfg = load_config()
        con = _con()
        ent = next((e for e in db.list_entidades(con) if e["id"] == entidad_id), {})
        recientes = con.execute(
            "SELECT * FROM pleno WHERE entidad_id=? ORDER BY id DESC LIMIT 3",
            (entidad_id,)).fetchall()
        pleno, mios = None, {}
        for r in recientes:                        # el más nuevo con transcript y temas
            h = detectar(r["video_id"], None if TODOS in temas else temas, cfg)
            if h:
                pleno, mios = dict(r), h
                break
        if pleno:
            asunto, html_ = _render_aviso(ent.get("nombre", ""), pleno, mios, token,
                                          modo="bienvenida")
            _guardar_envio(con, entidad_id, pleno["video_id"], email,
                           ", ".join(mios), asunto, html_, "bienvenida")
        else:
            asunto = "Suscripción activada"
            b = f"{_base_url()}/api/alertas/baja?token={token}"
            html_ = f"""<div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;color:#222">
<h2 style="font-weight:normal">Suscripción activada · {_html.escape(ent.get('nombre', ''))}</h2>
<p>Te avisaremos cuando el pleno trate: <b>{_html.escape(', '.join(temas))}</b>.</p>
<p style="color:#777;font-size:13px"><a href="{b}" style="color:#777">Darse de baja</a> ·
Tus datos no salen del ayuntamiento.</p></div>"""
            _guardar_envio(con, entidad_id, "", email, ", ".join(temas), asunto, html_, "bienvenida")
        con.close()
        _smtp_send(email, asunto, html_)
    except Exception as e:                                  # noqa: BLE001
        print(f"[alertas] bienvenida falló: {e}")


def baja(token: str) -> dict:
    con = _con()
    n = con.execute("DELETE FROM alerta_sub WHERE token=?", (token,)).rowcount
    con.commit(); con.close()
    return {"ok": n > 0, "eliminadas": n}


def suscripciones(entidad_id: int) -> list[dict]:
    con = _con()
    rows = con.execute(
        "SELECT email, tema, confirmado FROM alerta_sub WHERE entidad_id=? ORDER BY email, tema",
        (entidad_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def bandeja(entidad_id: int | None = None, limit: int = 30) -> list[dict]:
    con = _con()
    q = "SELECT id,entidad_id,video_id,email,temas,asunto,html,tipo,enviada FROM alerta_envio"
    args: tuple = ()
    if entidad_id:
        q += " WHERE entidad_id=?"; args = (entidad_id,)
    rows = con.execute(q + " ORDER BY id DESC LIMIT ?", args + (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ el correo
def _hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def _base_url() -> str:
    return os.environ.get("PLENO_BASE_URL", "http://localhost:8000").rstrip("/")


def _render_confirmacion(entidad: str, temas: list[str], token: str) -> str:
    lis = "".join(f"<li>{_html.escape(t)}</li>" for t in temas)
    u = f"{_base_url()}/api/alertas/confirmar?token={token}"
    b = f"{_base_url()}/api/alertas/baja?token={token}"
    return f"""<div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;color:#222">
<h2 style="font-weight:normal">Alertas del pleno · {_html.escape(entidad)}</h2>
<p>Has pedido recibir un aviso cuando el pleno trate estos temas:</p>
<ul>{lis}</ul>
<p><a href="{u}" style="background:#7a1f2b;color:#fff;padding:10px 18px;text-decoration:none">Confirmar suscripción</a></p>
<p style="color:#777;font-size:13px">Si no lo pediste tú, ignora este correo.
Podrás darte de baja en un clic desde cualquier aviso. Tus datos no salen del ayuntamiento.
<a href="{b}" style="color:#777">Darse de baja</a></p></div>"""


def _render_aviso(entidad: str, pleno: dict, hallazgos: dict[str, list[dict]],
                  token: str, modo: str = "aviso") -> tuple[str, str]:
    """(asunto, html). Solo citas literales: nada de resúmenes generados.
    modo: aviso (tema suscrito) | bienvenida (al confirmar) | todos (boletín)."""
    temas_txt = ", ".join(hallazgos)
    fecha = pleno.get("fecha") or pleno.get("titulo") or ""
    vid = pleno.get("video_id", "")
    vurl = (pleno.get("video_url") or "").strip()
    if not vurl and len(vid) == 11 and all(c.isalnum() or c in "_-" for c in vid):
        # los plenos descargados de YouTube usan el id del vídeo como video_id;
        # los del corpus del Congreso (DSCD-…) no tienen vídeo enlazable
        vurl = f"https://www.youtube.com/watch?v={vid}"
    bloques = []
    for tema, citas in hallazgos.items():
        # el dato principal para el vecino: el minuto donde EMPIEZA a tratarse el tema
        ini = citas[0]["start"]
        salto = ""
        if vurl:
            sep = "&" if "?" in vurl else "?"
            salto = f' — <a href="{vurl}{sep}t={int(ini)}s" style="color:#7a1f2b">ir a ese momento del vídeo</a>'
        cabecera = (f"<p style='margin:2px 0 8px'>Se empieza a tratar en el minuto "
                    f"<b>{_hms(ini)}</b>{salto}.</p>")
        filas = []
        for c in citas:
            quien = _html.escape(c["speaker"] or "orador sin identificar")
            if c.get("party"):
                quien += f" ({_html.escape(c['party'])})"
            txt = _html.escape(c["text"][:320]) + ("…" if len(c["text"]) > 320 else "")
            link = ""
            if vurl:
                sep = "&" if "?" in vurl else "?"
                link = f' · <a href="{vurl}{sep}t={int(c["start"])}s" style="color:#7a1f2b">ver en el vídeo</a>'
            filas.append(f"""<blockquote style="margin:10px 0;padding:10px 14px;background:#f7f4ef;border-left:3px solid #7a1f2b">
«{txt}»<br><span style="color:#777;font-size:13px">{quien} · minuto {_hms(c['start'])}{link}</span></blockquote>""")
        bloques.append(f"<h3 style='font-weight:normal;margin:18px 0 4px'>{_html.escape(tema).capitalize()}</h3>"
                       + cabecera + "".join(filas))
    acta = f"{_base_url()}/api/acta?video={vid}&fmt=pdf"
    b = f"{_base_url()}/api/alertas/baja?token={token}"
    if modo == "bienvenida":
        asunto = f"Suscripción activada — lo último sobre {temas_txt}"
        intro = ("Tu suscripción está activa. Para empezar, esto es lo último que se trató "
                 "sobre tus temas en el pleno más reciente:")
    elif modo == "todos":
        asunto = f"Nuevo pleno de tu ayuntamiento — {fecha}"
        intro = ("Se ha publicado el acta de un nuevo pleno. Índice de temas tratados, "
                 "con el minuto donde empieza cada uno:" if hallazgos else
                 "Se ha publicado el acta de un nuevo pleno.")
    else:
        asunto = f"El pleno habló de {temas_txt} — {fecha}"
        intro = "En este pleno se trataron temas a los que estás suscrito. Citas literales:"
    html_ = f"""<div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;color:#222">
<p style="color:#7a1f2b;font-size:12px;letter-spacing:.08em;text-transform:uppercase">Alertas del pleno · {_html.escape(entidad)}</p>
<h2 style="font-weight:normal">{_html.escape(pleno.get('titulo') or vid)}</h2>
<p>{intro}</p>
{''.join(bloques)}
<p style="margin-top:18px"><a href="{acta}" style="background:#7a1f2b;color:#fff;padding:10px 18px;text-decoration:none">Leer el acta completa (PDF)</a></p>
<p style="color:#777;font-size:13px">Recibes este correo porque confirmaste la suscripción.
<a href="{b}" style="color:#777">Darse de baja</a> · Tus datos no salen del ayuntamiento.</p></div>"""
    return asunto, html_


def _guardar_envio(con, entidad_id, video_id, email, temas, asunto, html_, tipo):
    con.execute(
        "INSERT INTO alerta_envio(entidad_id,video_id,email,temas,asunto,html,tipo,enviada) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (entidad_id, video_id, email, temas, asunto, html_, tipo,
         _dt.datetime.now().isoformat(timespec="seconds")))
    con.commit()


def _smtp_send(to: str, asunto: str, html_: str) -> bool:
    """Envío real solo si hay SMTP configurado; si no, la bandeja demo ya lo guarda."""
    host = os.environ.get("PLENO_SMTP_HOST")
    if not host:
        return False
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(html_, "html", "utf-8")
    msg["Subject"] = asunto
    msg["From"] = os.environ.get("PLENO_SMTP_FROM", "alertas@ayuntamiento.local")
    msg["To"] = to
    with smtplib.SMTP(host, int(os.environ.get("PLENO_SMTP_PORT", "587"))) as s:
        s.starttls()
        user = os.environ.get("PLENO_SMTP_USER")
        if user:
            s.login(user, os.environ.get("PLENO_SMTP_PASS", ""))
        s.send_message(msg)
    return True


# ------------------------------------------------------------------ orquestador
def procesar_pleno(video_id: str, cfg=None) -> dict:
    """Tras procesar un pleno: detecta temas, cruza con las suscripciones confirmadas
    de su entidad y genera un correo por vecino (agrupando sus temas)."""
    cfg = cfg or load_config()
    con = _con()
    eid = db.entidad_de_video(con, video_id)
    if not eid:
        con.close()
        return {"error": "el pleno no tiene entidad registrada"}
    pleno = con.execute("SELECT * FROM pleno WHERE video_id=?", (video_id,)).fetchone()
    pleno = dict(pleno) if pleno else {"video_id": video_id, "titulo": video_id}
    ent = next((e for e in db.list_entidades(con) if e["id"] == eid), {})
    subs = con.execute(
        "SELECT email, tema, token FROM alerta_sub WHERE entidad_id=? AND confirmado=1",
        (eid,)).fetchall()
    if not subs:
        con.close()
        return {"avisos": 0, "detectados": [], "nota": "sin suscripciones confirmadas"}

    temas_suscritos = sorted({r["tema"] for r in subs})
    # si alguien quiere TODOS los plenos, el índice de su boletín cubre el catálogo entero
    hallazgos = detectar(video_id, None if TODOS in temas_suscritos else temas_suscritos, cfg)
    enviados = []
    por_email: dict[str, dict] = {}
    for r in subs:
        por_email.setdefault(r["email"], {"temas": [], "token": r["token"]})
        por_email[r["email"]]["temas"].append(r["tema"])
    for email, info in por_email.items():
        boletin = TODOS in info["temas"]
        if boletin:                                # todos los plenos: índice compacto (1 cita/tema)
            mios = {t: c[:1] for t, c in hallazgos.items()}
        else:
            mios = {t: hallazgos[t] for t in info["temas"] if t in hallazgos}
            if not mios:
                continue
        # antiduplicado: si el acta se regenera (p. ej. tras etiquetar voces) no se
        # reenvía el aviso a quien ya lo recibió por este pleno (incluida la bienvenida)
        ya = con.execute("SELECT 1 FROM alerta_envio WHERE video_id=? AND email=? "
                         "AND tipo IN ('aviso','bienvenida')",
                         (video_id, email)).fetchone()
        if ya:
            continue
        asunto, html_ = _render_aviso(ent.get("nombre", ""), pleno, mios, info["token"],
                                      modo="todos" if boletin else "aviso")
        _guardar_envio(con, eid, video_id, email,
                       TODOS if boletin else ", ".join(mios), asunto, html_, "aviso")
        _smtp_send(email, asunto, html_)
        enviados.append({"email": email, "temas": [TODOS] if boletin else list(mios)})
    con.close()
    return {"avisos": len(enviados), "detectados": sorted(hallazgos), "enviados": enviados}
