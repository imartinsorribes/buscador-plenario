"""Bloque D — UI web (FastAPI + página Tailwind, SIN Streamlit).

Sirve un buscador semántico sobre los plenos indexados y devuelve, por cada
resultado, el orador (nombre + partido), el minuto y el enlace. El frontend lleva
un reproductor de YouTube embebido que SALTA AL MINUTO EXACTO del fragmento.

Reusa src/search.py (Bloque C). Arrancar:
    uvicorn app.server:app --port 8000        (o:  python -m app.server)
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Body, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src import alertas, db
from src.config import load_config, resolve_path
from src.search import search

app = FastAPI(title="Buscador Plenario Inteligente")
_cfg = load_config()
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_JOBS: dict = {}                                  # trabajos de generación en curso

# Pestaña Ciudadano: dashboard estático del compañero ("El Congreso, en datos") servido como
# recurso (index.html + plotly.min.js) y embebido por iframe en la UI. Datos embebidos, sin backend.
_CIUDADANO_DIR = _ROOT / "app_completa_ENVIAR"
if _CIUDADANO_DIR.exists():
    app.mount("/ciudadano-app", StaticFiles(directory=str(_CIUDADANO_DIR), html=True), name="ciudadano")

# Pestaña Manuales (extra SEDIPUALBA): capturas extraídas de los manuales, servidas para el
# panel de fuentes (la evidencia visual de cada respuesta).
_SEDI_IMG = _ROOT / "data" / "sedipualba" / "images"
_SEDI_IMG.mkdir(parents=True, exist_ok=True)
app.mount("/sedipualba-img", StaticFiles(directory=str(_SEDI_IMG)), name="sedipualba-img")


@app.get("/api/manuales/ask")
def manuales_ask(q: str):
    """Pregunta sobre los manuales/tutorial de SEDIPUALBA -> respuesta con citas verificables."""
    if not q.strip():
        return JSONResponse({"error": "escribe una pregunta"}, status_code=400)
    try:
        from src.manuales import ask
        return ask(q)
    except Exception as e:                                  # noqa: BLE001
        return JSONResponse({"error": f"El buscador de manuales falló: {str(e)[:120]}"}, status_code=500)


@app.post("/api/manuales/ask")
def manuales_ask_conv(payload: dict = Body(...)):
    """Igual que el GET pero CONVERSACIONAL: acepta historial para preguntas de seguimiento."""
    q = (payload.get("q") or "").strip()
    if not q:
        return JSONResponse({"error": "escribe una pregunta"}, status_code=400)
    try:
        from src.manuales import ask
        return ask(q, history=payload.get("history") or None,
                   manual=(payload.get("manual") or "").strip() or None)
    except Exception as e:                                  # noqa: BLE001
        return JSONResponse({"error": f"El buscador de manuales falló: {str(e)[:120]}"}, status_code=500)


@app.get("/api/manuales/pagina")
def manuales_pagina(manual: str, page: int):
    """Página del manual citada, renderizada a PNG (cacheada) para comprobar la fuente."""
    from src.manuales import page_png
    p = page_png(manual, page)
    if not p:
        return JSONResponse({"error": "página no encontrada"}, status_code=404)
    return FileResponse(p, media_type="image/png")


# ------------------------------------------------ añadir un manual en PDF (desde la pestaña)
def _run_ingesta_manual(job: str, pdf_name: str) -> None:
    """Ingesta en 2 fases: texto YA (buscable al momento) y capturas descritas después."""
    try:
        from src.manuales import ingest
        cfg = load_config()
        cfg.embeddings.device = "cpu"                 # no pelear por la GPU con las consultas
        _JOBS[job].update(stage="indexando el texto", step=1)
        r1 = ingest(cfg)
        _JOBS[job].update(texto=r1.get("texto", 0), stage="describiendo capturas (visión)", step=2)
        # descripciones de imágenes (cacheadas por hash: solo paga las nuevas) + re-ingest
        p = subprocess.run([sys.executable, "scripts/ingest_imagenes.py", "--manual", Path(pdf_name).stem],
                           cwd=str(_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"Descritas NUEVAS:\s*(\d+)", p.stdout or "")
        _JOBS[job]["capturas"] = int(m.group(1)) if m else 0
        _JOBS[job].update(stage="re-indexando con las capturas", step=3)
        r2 = ingest(cfg)
        _JOBS[job].update(done=True, step=4, stage="listo", indexados=r2.get("indexados", 0))
    except Exception as e:                                  # noqa: BLE001
        _JOBS[job].update(done=True, error=str(e)[:150])


@app.post("/api/manuales/subir")
async def manuales_subir(manual: UploadFile = File(...)):
    """Sube un manual en PDF: se guarda, se indexa (texto al momento; capturas en 2ª fase) y
    queda buscable SIN reiniciar (recarga en caliente del índice)."""
    data = await manual.read()
    if not data.startswith(b"%PDF"):
        return JSONResponse({"error": "el archivo no es un PDF"}, status_code=400)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(manual.filename or "manual.pdf").name)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    dest = _ROOT / "data" / "sedipualba" / "manuales" / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        import fitz
        npages = len(fitz.open(str(dest)))
    except Exception:
        dest.unlink(missing_ok=True)
        return JSONResponse({"error": "PDF ilegible"}, status_code=400)
    job = uuid.uuid4().hex[:8]
    _JOBS[job] = {"stage": "en cola", "step": 0, "done": False, "error": "",
                  "manual": safe, "paginas": npages}
    threading.Thread(target=_run_ingesta_manual, daemon=True, args=(job, safe)).start()
    return {"job": job, "manual": safe, "paginas": npages}


# ------------------------------------------------ crear manual desde un vídeo (con barrera)
def _run_gen_manual(job: str, url: str, titulo: str, force: bool, solo: bool = False) -> None:
    cmd = [sys.executable, "scripts/generar_manual.py", url]
    if titulo:
        cmd += ["--titulo", titulo]
    if force:
        cmd += ["--force"]
    if solo:                                  # indexar el vídeo por minutos, SIN redactar manual
        cmd += ["--solo-indexar"]
    try:
        p = subprocess.Popen(cmd, cwd=str(_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            ln = line.strip()
            m = re.match(r"\[(\d)/4\]\s*(.+)", ln)
            if m:
                _JOBS[job].update(step=int(m.group(1)), stage=m.group(2))
            if ln.startswith("cobertura por manuales"):
                _JOBS[job]["cobertura"] = ln.split(":", 1)[1].strip()
            if ln.startswith("YA EXISTE"):
                _JOBS[job]["barrera"] = True
            if ln.startswith("Manuales que lo cubren:"):
                _JOBS[job]["cubierto_por"] = ln.split(":", 1)[1].strip()
            if re.match(r"\[\d+\]\s.*(GENERADO|REMITIDO)", ln):
                _JOBS[job]["caps"] = _JOBS[job].get("caps", 0) + 1
            m = re.search(r"-> docs[/\\]manual_([A-Za-z0-9_-]+)\.md", ln)
            if m:
                _JOBS[job]["vid"] = m.group(1)
            m = re.search(r"id=([A-Za-z0-9_-]{11})", ln)
            if m:
                _JOBS[job]["vid"] = m.group(1)
        p.wait()
        if p.returncode == 0:
            _JOBS[job].update(done=True, stage="terminado")
        else:
            _JOBS[job].update(done=True, error=f"falló (código {p.returncode})")
    except Exception as e:                                  # noqa: BLE001
        _JOBS[job].update(done=True, error=str(e)[:150])


@app.post("/api/manuales/generar")
def manuales_generar(payload: dict = Body(...)):
    """Crea un manual ilustrado desde un vídeo tutorial de YouTube — salvo que los manuales
    existentes ya cubran su contenido (la BARRERA anti-duplicados)."""
    url = (payload.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "indica la URL del vídeo"}, status_code=400)
    job = uuid.uuid4().hex[:8]
    _JOBS[job] = {"stage": "en cola", "step": 0, "done": False, "error": "", "barrera": False}
    threading.Thread(target=_run_gen_manual, daemon=True,
                     args=(job, url, (payload.get("titulo") or "").strip(),
                           bool(payload.get("force")))).start()
    return {"job": job}


@app.post("/api/manuales/indexar-video")
def manuales_indexar_video(payload: dict = Body(...)):
    """Indexa un vídeo tutorial por minutos (transcribe y lo hace buscable; el asistente
    enlaza el momento exacto). NO redacta manual: bien indexado basta."""
    url = (payload.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "indica la URL del vídeo"}, status_code=400)
    job = uuid.uuid4().hex[:8]
    _JOBS[job] = {"stage": "en cola", "step": 0, "done": False, "error": ""}
    threading.Thread(target=_run_gen_manual, daemon=True,
                     args=(job, url, (payload.get("titulo") or "").strip(), False, True)).start()
    return {"job": job}


@app.get("/api/manuales/generar/status")
def manuales_generar_status(job: str):
    return _JOBS.get(job, {"error": "trabajo no encontrado", "done": True})


@app.get("/api/manuales/doc")
def manuales_doc(vid: str, fmt: str = "pdf"):
    """Descarga el manual generado (pdf o markdown)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", vid)
    p = _ROOT / "docs" / f"manual_{safe}.{ 'pdf' if fmt == 'pdf' else 'md' }"
    if not p.exists():
        return JSONResponse({"error": "manual no encontrado"}, status_code=404)
    media = "application/pdf" if fmt == "pdf" else "text/markdown; charset=utf-8"
    return FileResponse(str(p), filename=p.name, media_type=media)


# ---------------------------------------------- manuales: utilidades añadidas
@app.post("/api/manuales/feedback")
def manuales_feedback(payload: dict = Body(...)):
    """Voto '¿te ha servido?' -> métrica viva de utilidad (JSONL local)."""
    from src.manuales import feedback
    return feedback(payload.get("q", ""), bool(payload.get("util")), payload.get("manual", ""))


@app.get("/api/manuales/feedback/stats")
def manuales_feedback_stats():
    from src.manuales import feedback_stats
    return feedback_stats()


@app.get("/api/manuales/lista")
def manuales_lista():
    from src.manuales import listado
    return {"manuales": listado(_cfg)}


@app.get("/api/manuales/diff")
def manuales_diff(viejo: str, nuevo: str):
    """Qué hay de nuevo entre dos versiones de un manual (diff semántico + síntesis)."""
    from src.manuales import comparar
    r = comparar(viejo, nuevo, _cfg)
    if r.get("error"):
        return JSONResponse(r, status_code=400)
    return r


@app.post("/api/manuales/ficha")
def manuales_ficha(payload: dict = Body(...)):
    """Ficha PDF imprimible de una respuesta: pregunta + respuesta + páginas citadas."""
    from src.manuales import page_png
    q = (payload.get("q") or "").strip()
    resp = (payload.get("respuesta") or "").strip()
    if not q or not resp:
        return JSONResponse({"error": "faltan la pregunta o la respuesta"}, status_code=400)
    md = [f"# Ficha rápida · Sedipualb@", "", f"**Pregunta:** {q}", "", resp, ""]
    vistos = set()
    for f in (payload.get("fuentes") or [])[:8]:
        man, page = f.get("manual"), f.get("page")
        if not man or not page or (man, page) in vistos:
            continue
        vistos.add((man, page))
        png = page_png(man, int(page))
        if png:
            md += [f"## Fuente: {man} · pág. {page}", f"![p]({png})", ""]
        if len(vistos) >= 4:
            break
    tmp = Path(tempfile.mkdtemp(prefix="ficha_"))
    (tmp / "ficha.md").write_text("\n".join(md), encoding="utf-8")
    p = subprocess.run([sys.executable, "scripts/md_to_pdf.py", str(tmp / "ficha.pdf"),
                        str(tmp / "ficha.md")], cwd=str(_ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not (tmp / "ficha.pdf").exists():
        detalle = (p.stderr or p.stdout or "").strip()[-200:]
        return JSONResponse({"error": f"no se pudo componer el PDF: {detalle}"}, status_code=500)
    return FileResponse(str(tmp / "ficha.pdf"), filename="ficha_sedipualba.pdf",
                        media_type="application/pdf")


@app.post("/api/manuales/pantallazo")
async def manuales_pantallazo(file: UploadFile = File(...), q: str = Form("")):
    """Sube una captura de DONDE ESTÁS ATASCADO: identifica la pantalla en los manuales
    y responde el paso siguiente. La visión se paga una vez (caché por hash)."""
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        return JSONResponse({"error": "imagen demasiado grande (máx. 8 MB)"}, status_code=400)
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8"):
        return JSONResponse({"error": "sube una imagen PNG o JPG"}, status_code=400)
    from src.manuales import pantallazo
    try:
        return pantallazo(data, q, _cfg)
    except Exception as e:                                  # noqa: BLE001
        return JSONResponse({"error": f"no se pudo analizar la captura: {e}"}, status_code=500)


# ---------------------------------------------------------- alertas ciudadanas
@app.get("/api/alertas/temas")
def alertas_temas():
    """Catálogo cerrado de temas (nunca texto libre: privacidad por diseño)."""
    return {"temas": list(alertas.TEMAS), "todos": alertas.TODOS}


@app.post("/api/alertas/suscribir")
def alertas_suscribir(payload: dict = Body(...)):
    try:
        eid = int(payload.get("entidad") or 0)
    except (TypeError, ValueError):
        eid = 0
    if not eid:
        return JSONResponse({"error": "elige tu municipio"}, status_code=400)
    r = alertas.suscribir(payload.get("email", ""), eid, payload.get("temas") or [])
    if r.get("error"):
        return JSONResponse(r, status_code=400)
    return r


def _pagina_simple(msg: str) -> HTMLResponse:
    return HTMLResponse(
        "<body style='font-family:Georgia,serif;max-width:520px;margin:80px auto;color:#222'>"
        f"<h2 style='font-weight:normal'>{msg}</h2>"
        "<p style='color:#777'>Puedes cerrar esta pestaña.</p></body>")


@app.get("/api/alertas/confirmar")
def alertas_confirmar(token: str):
    ok = alertas.confirmar(token).get("ok")
    return _pagina_simple("Suscripción confirmada. Recibirás un aviso cuando el pleno "
                          "trate tus temas." if ok else "Enlace no válido o ya usado.")


@app.get("/api/alertas/baja")
def alertas_baja(token: str):
    ok = alertas.baja(token).get("ok")
    return _pagina_simple("Baja completada. No recibirás más avisos."
                          if ok else "Enlace no válido o ya usado.")


@app.post("/api/alertas/procesar")
def alertas_procesar(payload: dict = Body(...)):
    """Genera los avisos de un pleno ya procesado (también lo hace solo al acabar
    un acta; este endpoint alimenta la bandeja de demostración)."""
    vid = (payload.get("video") or "").strip()
    if not vid:
        return JSONResponse({"error": "indica el pleno"}, status_code=400)
    return alertas.procesar_pleno(vid, _cfg)


@app.get("/api/alertas/bandeja")
def alertas_bandeja(entidad: int | None = None):
    return {"correos": alertas.bandeja(entidad)}


@app.get("/api/alertas/subs")
def alertas_subs(entidad: int):
    return {"subs": alertas.suscripciones(entidad)}


def _audio_path(video: str):
    for ext in (".wav", ".m4a", ".mp4", ".mp3"):
        p = resolve_path(f"data/raw_audio/{video}{ext}")
        if p.exists():
            return str(p)
    return None


def _entidad_slug(video: str):
    con = db.connect()
    eid = db.entidad_de_video(con, video)
    slug = next((e["slug"] for e in db.list_entidades(con) if e["id"] == eid), None) if eid else None
    con.close()
    return slug


@app.get("/api/buscar")
def buscar(q: str, k: int = 8, video: str | None = None):
    """Búsqueda semántica -> fragmentos con orador, minuto y deep-link."""
    if not q or not q.strip():
        return {"hits": []}
    hits = search(q, _cfg, final_k=max(k * 3, 24), video=video)
    out = []
    for h in hits:
        m = h["meta"]
        sp = (m.get("speaker") or "").strip()
        if sp.lower() in {"", "presidencia", "(sin identificar)"}:
            continue   # fuera el trámite (Presidencia) y los oradores sin identificar
        score = h.get("rerank")
        if score is None and h.get("distance") is not None:
            score = 1.0 - h["distance"]
        out.append({
            "text": h["text"],
            "speaker": (m.get("speaker") or "").strip(),
            "title": m.get("title") or "",
            "video_id": m.get("video_id") or "",
            "start": int(m.get("start") or 0),
            "youtube_link": m.get("youtube_link") or "",
            "score": round(float(score), 3) if score is not None else None,
        })
        if len(out) >= k:
            break
    return {"hits": out}


@app.get("/api/entidades")
def entidades():
    """Organismos dados de alta (Congreso, ayuntamientos, …)."""
    con = db.connect()
    out = db.list_entidades(con)
    con.close()
    return {"entidades": out}


@app.get("/api/plenos")
def plenos(entidad: int | None = None):
    """Catálogo de plenos (filtrable por entidad) para el desplegable."""
    con = db.connect()
    rows = db.list_plenos(con, entidad)
    con.close()
    return {"plenos": [{"video_id": p["video_id"], "title": p["titulo"], "fecha": p["fecha"],
                        "entidad": p["entidad_nombre"], "fiabilidad": p["fiabilidad"]} for p in rows]}


@app.get("/api/acta")
def acta(video: str, fmt: str = "pdf"):
    """Genera (si hace falta) y descarga el acta en PDF, texto o WORD (.docx editable)."""
    from src.acta import build_acta
    tr = resolve_path(f"data/transcripts/{video}.json")
    if not tr.exists():
        return JSONResponse({"error": "transcripción no encontrada"}, status_code=404)
    txt_path, pdf_path = build_acta(str(tr), video_id=video)
    if fmt == "docx":                                  # Word editable para la secretaria
        from src.acta_docx import build_docx
        path = Path(build_docx(video))
        return FileResponse(str(path), filename=path.name,
                            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if fmt == "transcripcion":                          # transcripción ORIGINAL del ASR (auditoría)
        path = _build_transcripcion(video)
        return FileResponse(str(path), filename=path.name, media_type="text/plain; charset=utf-8")
    path = pdf_path if fmt == "pdf" else txt_path
    return FileResponse(str(path), filename=path.name,
                        media_type="application/pdf" if fmt == "pdf" else "text/plain; charset=utf-8")


def _build_transcripcion(video: str) -> Path:
    """Transcripción ORIGINAL literal del ASR (sin editar, con minuto), para revisar errores."""
    import json
    tr = resolve_path(f"data/transcripts/{video}.json")
    data = json.loads(tr.read_text(encoding="utf-8"))

    def hms(s):
        s = int(s or 0)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"

    out_lines = ["TRANSCRIPCIÓN ORIGINAL (texto literal del reconocimiento de voz, SIN editar).",
                 "Para revisión: comprueba aquí si hubo algún error de transcripción.", "",
                 f"Pleno: {video}", "=" * 60, ""]
    for s in sorted(data.get("segments", []), key=lambda x: x.get("start", 0)):
        t = (s.get("text") or "").strip()
        if t:
            out_lines.append(f"[{hms(s.get('start', 0))}]  {t}")
    path = resolve_path(f"data/actas/{video}.transcripcion.txt")
    path.write_text("\n".join(out_lines), encoding="utf-8")
    return path


def _enriquece_actas(data: dict) -> dict:
    """Añade a cada fragmento del corpus el enlace a su acta: el DIARIO OFICIAL del
    Congreso (URL determinista en congreso.es por legislatura e id) o, si es un pleno
    procesado por nosotros, el acta generada localmente."""
    try:
        for f in data.get("fragmentos") or []:
            pid = (f.get("pleno") or "").strip()
            partes = pid.split("-")
            if pid.startswith("DSCD-") and len(partes) >= 3:
                f["acta_url"] = f"https://www.congreso.es/public_oficiales/L{partes[1]}/CONG/DS/PL/{pid}.PDF"
                f["acta_label"] = "Diario oficial"
            elif pid and resolve_path(f"data/transcripts/{pid}.json").exists():
                f["acta_url"] = f"/api/acta?video={pid}&fmt=pdf"
                f["acta_label"] = "acta (PDF)"
    except Exception:                                   # noqa: BLE001
        pass
    return data


@app.get("/api/buscar-corpus")
def buscar_corpus(q: str):
    """Proxy a la BÚSQUEDA INTELIGENTE del corpus oficial (servicio del compañero en :8100).
    Lo servimos desde nuestro origen para la pestaña Buscar (sin CORS)."""
    import json as _json
    import urllib.parse
    import urllib.request
    if not q.strip():
        return {"error": "escribe una consulta"}
    url = "http://localhost:8100/api/buscar?q=" + urllib.parse.quote(q)
    try:
        with urllib.request.urlopen(url, timeout=180) as r:   # 1ª consulta lenta (carga modelos)
            return _enriquece_actas(_json.loads(r.read().decode("utf-8")))
    except Exception:
        # AUTO-RESURRECCIÓN: si el :8100 se cayó, se relanza y se reintenta una vez.
        # Si está VIVO pero devuelve 5xx (proceso zombi de otra sesión, con entorno viejo),
        # relanzarlo sin más no sirve: el puerto sigue ocupado -> primero se mata al zombi.
        import socket
        import time as _t
        try:
            zpid = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-NetTCPConnection -LocalPort 8100 -State Listen).OwningProcess"],
                capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
            if zpid and zpid[0].strip().isdigit():
                subprocess.run(["taskkill", "/F", "/PID", zpid[0].strip()],
                               capture_output=True, timeout=10)
                _t.sleep(1)
        except Exception:                                   # noqa: BLE001
            pass
        _launch_buscador()
        for _ in range(20):
            s = socket.socket(); s.settimeout(0.5)
            ok = s.connect_ex(("127.0.0.1", 8100)) == 0
            s.close()
            if ok:
                break
            _t.sleep(1)
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return _enriquece_actas(_json.loads(r.read().decode("utf-8")))
        except Exception as e:
            return JSONResponse(
                {"error": "El buscador del corpus no responde (ni tras relanzarlo). "
                          "Revisa prueba_buscador\\prueba_buscador. (" + str(e)[:80] + ")"},
                status_code=503)


@app.get("/api/audio")
def audio(video: str, request: Request):
    """Sirve el audio LOCAL del pleno (con soporte de Range para saltar al segundo exacto).
    Reproducir las muestras desde aquí es más fiable que el embed de YouTube y es local-first."""
    path = _audio_path(video)
    if not path:
        return JSONResponse({"error": "audio no encontrado"}, status_code=404)
    p = Path(path)
    size = p.stat().st_size
    media = {".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
             ".mp3": "audio/mpeg"}.get(p.suffix.lower(), "application/octet-stream")
    rng = request.headers.get("range") or request.headers.get("Range")
    if rng and rng.startswith("bytes="):
        a, _, b = rng.split("=", 1)[1].partition("-")
        start = int(a) if a else 0
        end = int(b) if b else size - 1
        end = min(end, size - 1)
        start = min(start, end)
        length = end - start + 1

        def stream():
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(262144, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                    yield chunk
        return StreamingResponse(stream(), status_code=206, media_type=media, headers={
            "Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes",
            "Content-Length": str(length)})
    return FileResponse(str(p), media_type=media, headers={"Accept-Ranges": "bytes"})


@app.get("/api/clusters")
def clusters(video: str):
    """Voces (clusters de diarización) de un pleno, con nombre sugerido y muestras para que el
    secretario las ETIQUETE (paso humano, sin biometría). El 'quién' robusto para municipios."""
    import json
    from collections import defaultdict
    tr = resolve_path(f"data/transcripts/{video}.json")
    if not tr.exists():
        return JSONResponse({"error": "transcripción no encontrada"}, status_code=404)
    segs = sorted(json.loads(tr.read_text(encoding="utf-8"))["segments"], key=lambda s: s.get("start", 0))
    byc: dict[str, list] = defaultdict(list)
    for s in segs:
        if s.get("speaker"):
            byc[s["speaker"]].append(s)
    out = []
    for spk, ss in byc.items():
        # NADA de adivinar: la tarjeta sale vacía. El nombre/grupo lo pone el humano o lo sugiere
        # una HUELLA registrada (vía /api/voicesuggest). No se infiere del texto/anuncios.
        # 3 muestras más largas (mejor audio para reconocer la voz), pero EN ORDEN CRONOLÓGICO
        samples = sorted(sorted(ss, key=lambda s: -(s.get("end", 0) - s.get("start", 0)))[:3],
                         key=lambda s: s.get("start", 0))
        out.append({
            "cluster": spk,
            "suggested": "",
            "party": "",
            "is_chair": False,
            "n": len(ss),
            "cruce": sum(1 for s in ss if s.get("overlap")),   # turnos con solape (discusión)
            "secs": int(sum((s.get("end", 0) - s.get("start", 0)) for s in ss)),
            "samples": [{"start": int(s.get("start", 0)), "text": (s.get("text") or "").strip()[:220]}
                        for s in samples],
        })
    out.sort(key=lambda c: -c["secs"])
    return {"video": video, "clusters": out}


@app.get("/api/voicesuggest")
def voicesuggest(video: str):
    """Sugerencias por VOZ (lento: ECAPA sobre el audio). Se llama APARTE para que la lista de
    voces salga al instante y las sugerencias se rellenen después. {cluster: {name,party,sim,n}}."""
    import json
    tr = resolve_path(f"data/transcripts/{video}.json")
    if not tr.exists():
        return {"voices": {}}
    try:
        from src import voiceid
        slug, aud = _entidad_slug(video), _audio_path(video)
        if not (slug and aud and voiceid.load_voiceprints(slug)):
            return {"voices": {}}
        segs = json.loads(tr.read_text(encoding="utf-8"))["segments"]
        return {"voices": voiceid.suggest_from_voiceprints(aud, segs, slug)}
    except Exception:
        return {"voices": {}}


@app.post("/api/clusters")
def save_clusters(video: str, background: BackgroundTasks, payload: dict = Body(...)):
    """Aplica los nombres a TODO el pleno y regenera el acta AL INSTANTE; las huellas de voz se
    guardan en SEGUNDO PLANO (en plenos largos eso tardaba minutos y parecía colgado)."""
    import json
    tr = resolve_path(f"data/transcripts/{video}.json")
    if not tr.exists():
        return JSONResponse({"error": "transcripción no encontrada"}, status_code=404)
    labels = payload.get("labels", {})        # {cluster: {"name","party","chair"?}}
    data = json.loads(tr.read_text(encoding="utf-8"))
    for s in data["segments"]:
        lab = labels.get(s.get("speaker"))
        if lab is None:
            continue
        if lab.get("chair"):
            s["name"], s["party"] = "Presidencia", ""
        else:
            nm = (lab.get("name") or "").strip()
            s["name"] = nm or "(sin identificar)"
            s["party"] = (lab.get("party") or "").strip()
    tr.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    from src.acta import build_acta
    build_acta(str(tr), video_id=video)

    # cobertura = % del tiempo de palabra atribuido a un concejal concreto. Es la métrica de
    # fiabilidad honesta de un acta a ciegas (sin Diario que comparar).
    def _dur(s):
        return max((s.get("end", 0) - s.get("start", 0)), 0.0)
    total = sum(_dur(s) for s in data["segments"]) or 1.0
    named = sum(_dur(s) for s in data["segments"]
                if (s.get("name") or "") not in ("", "(sin identificar)", "Presidencia"))
    cobertura = round(named / total, 3)
    try:
        con = db.connect()
        db.set_fiabilidad(con, video, cobertura)
        con.close()
    except Exception:
        pass

    # huellas de voz: en SEGUNDO PLANO (ECAPA sobre el audio puede tardar en plenos largos).
    # SOLO se guarda la huella de las voces con CONSENTIMIENTO (save=true), con nombre REAL (nunca
    # "Voz N" -> eso es que no se identificó) y que no sean el moderador.
    from src import voiceid as _vid
    enroll_labs = {cl: lab for cl, lab in labels.items()
                   if lab.get("save", True) and not lab.get("chair")
                   and not _vid._is_auto_name(lab.get("name") or "")}
    slug, aud = _entidad_slug(video), _audio_path(video)
    if slug and aud and enroll_labs:
        def _enroll(audio=aud, segs=data["segments"], labs=enroll_labs, ent=slug):
            try:
                from src import voiceid
                voiceid.enroll_clusters(audio, segs, labs, ent)
            except Exception:
                pass
        background.add_task(_enroll)
    return {"ok": True, "labeled": len(labels), "enrolled": len(enroll_labs), "cobertura": cobertura}


def _slug(s: str) -> str:
    # slug CORTO y estable: quita el prefijo del tipo de organismo ("Ayuntamiento de", "Ajuntament
    # de", "Concello de"…) para que "Ayuntamiento de Chiva" -> "chiva" (no "ayuntamiento-de-chiva").
    # Así el registro de voces y la generación caen SIEMPRE en el mismo slug (sin duplicar entidades).
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^\s*(ayuntamiento|ajuntament|concello|udala?)\s+(de\s+la\s+|de\s+|del\s+|d')?", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "entidad"


# ---------------------------------------------------------------- registro de voces (local por municipio)
# Pre-registro de la huella de voz de cada concejal: se guarda en data/voiceprints/<slug>.json, el
# MISMO fichero (y slug) que usa el pleno -> al generar un acta de esa entidad, suggest_from_voiceprints
# la reconoce sola. Está SECCIONADO por municipio: cada entidad tiene su propio fichero, no se mezclan.
def _blob_to_wav(data: bytes):
    """Convierte el audio del micro o un archivo (ffmpeg detecta el formato) a wav mono 16 kHz."""
    from src import voiceid
    tmp = Path(tempfile.gettempdir()) / f"voz_{uuid.uuid4().hex}"
    src, dst = tmp.with_suffix(".bin"), tmp.with_suffix(".wav")
    src.write_bytes(data)
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
                   check=True, capture_output=True)
    wav = voiceid._load_audio(str(dst))
    return str(dst), wav.shape[1] / 16000.0


def _enroll_vectors(path: str, dur: float):
    """Vectores de huella de una grabación. Si es larga (la persona lee las frases del tirón),
    la trocea en ventanas de ~8 s -> VARIAS huellas (multi-vector) de una sola grabación; si es
    corta, una sola. Más huellas variadas = reconocimiento más robusto."""
    from src import voiceid
    wav = voiceid._load_audio(path)
    if dur <= 11:
        v = voiceid._embed_spans(wav, [(0.0, dur)])
        return [v] if v is not None else []
    out, t, win = [], 0.0, 8.0
    while t < dur - 2.0:                          # ignora el resto final de < 2 s
        v = voiceid._embed_spans(wav, [(t, min(t + win, dur))])
        if v is not None:
            out.append(v)
        t += win
    return out


def _clarity(vps: dict, nm: str) -> dict:
    """Nitidez de la huella de una persona, para saber si hay que REPETIR. Dos señales:
    - consistencia: coseno medio entre las propias frases (dispersas = ruido/micros distintos).
    - separación: parecido con la persona MÁS cercana ya registrada (para no confundir voces).
    Devuelve nivel (clara/mejorable/repetir/parcial) + mensaje."""
    import numpy as np

    from src import voiceid
    vecs = voiceid._vecs_of(vps.get(nm, {}))
    out = {"n": len(vecs), "consistency": None, "near": None, "near_name": "",
           "level": "parcial", "msg": "", "warn": ""}
    if not vecs:
        out["level"] = "vacio"
        return out
    M = np.array(vecs)
    if len(vecs) >= 2:
        S = M @ M.T
        iu = np.triu_indices(len(vecs), 1)
        out["consistency"] = round(float(np.mean(S[iu])), 3)
    best, bn = -1.0, ""
    for m in vps:                                   # persona registrada más cercana (≠ ella misma)
        if m == nm:
            continue
        ov = voiceid._vecs_of(vps[m])
        if ov:
            s = float(np.max(M @ np.array(ov).T))
            if s > best:
                best, bn = s, m
    if best >= 0:
        out["near"], out["near_name"] = round(best, 3), bn
    c = out["consistency"]
    if len(vecs) < 2:
        out["level"], out["msg"] = "parcial", "Añade 2-3 frases para fijar la huella."
    elif c < 0.50:
        out["level"], out["msg"] = "repetir", "Frases poco consistentes (¿ruido, micros distintos o muy cortas?). Repite con el mismo micrófono."
    elif c < 0.60:
        out["level"], out["msg"] = "mejorable", "Huella aceptable; añade otra frase para más nitidez."
    else:
        out["level"] = "clara"
        out["msg"] = "Huella clara." + ("" if len(vecs) >= 3 else " Con 3 frases queda aún mejor.")
    if out["near"] is not None and out["near"] >= 0.55:   # posible confusión con otra persona
        out["warn"] = f"Se parece mucho a «{bn}» ({out['near']}). ¿Misma persona o voces parecidas?"
    return out


@app.get("/api/voces")
def voces(entidad: str):
    """Voces registradas de un ayuntamiento (solo las de ESA entidad) con su nitidez."""
    from src import voiceid
    slug = _slug(entidad)
    vps = voiceid.load_voiceprints(slug)
    return {"slug": slug, "people": [
        {"name": n, "party": vps[n].get("party", ""),
         "n_frases": len(voiceid._vecs_of(vps[n])), "n_plenos": int(vps[n].get("n", 1)),
         "clarity": _clarity(vps, n)}
        for n in vps if voiceid._vecs_of(vps[n])]}


@app.post("/api/voces/enroll")
async def voces_enroll(entidad: str = Form(...), name: str = Form(...),
                       party: str = Form(""), audio: UploadFile = File(...)):
    """Registra la huella de voz de una persona (una grabación, puede dar varias huellas)."""
    from src import voiceid
    nm = name.strip()
    if not nm:
        return JSONResponse({"error": "indica el nombre y apellidos"}, status_code=400)
    if voiceid._is_auto_name(nm):
        return JSONResponse({"error": "pon un nombre real (no «Voz N»)"}, status_code=400)
    slug = _slug(entidad)
    path, dur = _blob_to_wav(await audio.read())
    if dur < 1.0:
        return JSONResponse({"error": "grabación demasiado corta, di unos segundos"}, status_code=400)
    new = _enroll_vectors(path, dur)               # 1 huella si es corta, varias si es larga
    if not new:
        return JSONResponse({"error": "no se pudo procesar el audio"}, status_code=400)
    vps = voiceid.load_voiceprints(slug)
    vecs = voiceid._cap(voiceid._vecs_of(vps.get(nm, {})) + new)
    vps[nm] = {"vecs": [x.tolist() for x in vecs], "n": int(vps.get(nm, {}).get("n", 0)) + 1,
               "party": (party.strip() or vps.get(nm, {}).get("party", ""))}
    voiceid.save_voiceprints(slug, vps)
    return {"name": nm, "n_frases": len(vecs), "added": len(new), "dur": round(dur, 1),
            "clarity": _clarity(vps, nm)}


@app.post("/api/voces/delete")
def voces_delete(entidad: str = Form(...), name: str = Form(...)):
    from src import voiceid
    slug = _slug(entidad)
    vps = voiceid.load_voiceprints(slug)
    vps.pop(name, None)
    voiceid.save_voiceprints(slug, vps)
    return {"ok": True}


@app.post("/api/voces/edit")
def voces_edit(entidad: str = Form(...), name: str = Form(...),
               new_name: str = Form(...), party: str = Form("")):
    """Corrige una voz ya registrada: cambia el nombre y/o el grupo (mantiene las huellas)."""
    from src import voiceid
    slug = _slug(entidad)
    vps = voiceid.load_voiceprints(slug)
    if name not in vps:
        return JSONResponse({"error": "voz no encontrada"}, status_code=404)
    nn = (new_name or "").strip() or name
    if voiceid._is_auto_name(nn):
        return JSONResponse({"error": "pon un nombre real (no «Voz N»)"}, status_code=400)
    entry = vps.pop(name)
    entry["party"] = party.strip()
    if nn != name and nn in vps:                       # ya existe ese nombre -> fusiona las huellas
        vecs = voiceid._cap(voiceid._vecs_of(vps[nn]) + voiceid._vecs_of(entry))
        vps[nn] = {"vecs": [v.tolist() for v in vecs],
                   "n": int(vps[nn].get("n", 1)) + int(entry.get("n", 1)),
                   "party": party.strip() or vps[nn].get("party", "")}
    else:
        vps[nn] = entry
    voiceid.save_voiceprints(slug, vps)
    return {"ok": True, "name": nn}


_STAGES = {"[1/5]": ("Descargando el vídeo", 1), "[2/5]": ("Transcribiendo (voz a texto)", 2),
           "[3/5]": ("Separando las voces", 3), "[4/5]": ("Asignando nombres", 4),
           "[5/5]": ("Generando el acta", 5)}


def _run_generar(job, url, slug, entidad, fecha, titulo, orden=""):
    # --lang auto: detección de idioma por fragmento (plenos municipales bilingües valencià/castellà)
    cmd = [sys.executable, "-m", "src.run_pleno", url, "--entidad-slug", slug, "--entidad", entidad,
           "--lang", "auto"]
    if fecha:
        cmd += ["--fecha", fecha]
    if titulo:
        cmd += ["--titulo", titulo]
    if orden.strip():                              # orden del día oficial pegado en la UI
        op = _ROOT / "data" / "ref" / f"orden_{slug}.txt"
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(orden, encoding="utf-8")
        cmd += ["--orden", str(op)]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", cwd=str(_ROOT))
        for line in p.stdout:
            for k, (name, step) in _STAGES.items():
                if k in line:
                    _JOBS[job].update(stage=name, step=step)
            dm = re.search(r"\[download\]\s+([\d.]+)%", line)      # progreso de yt-dlp
            if dm:
                _JOBS[job]["pct"] = float(dm.group(1))
            du = re.search(r"\[dur\]\s+(\d+)", line)               # duración -> ETA transcripción
            if du:
                _JOBS[job]["eta_min"] = max(1, round(int(du.group(1)) / 300))
            mm = re.search(r"id=([A-Za-z0-9_-]{6,})", line)
            if mm:
                _JOBS[job]["video_id"] = mm.group(1)
        p.wait()
        if p.returncode == 0:
            _JOBS[job].update(stage="Acta lista", step=6, done=True)
            vid = _JOBS[job].get("video_id")
            if vid:
                try:               # alertas ciudadanas: avisa a los suscriptores del municipio
                    _JOBS[job]["alertas"] = alertas.procesar_pleno(vid, _cfg).get("avisos", 0)
                except Exception:
                    pass
        else:
            _JOBS[job].update(error=f"La generación falló (código {p.returncode}). "
                              "Comprueba el enlace y que yt-dlp/ffmpeg estén disponibles.", done=True)
    except Exception as e:                                  # noqa: BLE001
        _JOBS[job].update(error=str(e), done=True)


@app.post("/api/generar")
def generar(payload: dict = Body(...)):
    """Genera un acta desde un enlace de YouTube (descarga→transcribe→diariza→nombra→acta),
    en SEGUNDO PLANO. Devuelve un job que se consulta en /api/generar/status."""
    url = (payload.get("url") or "").strip()
    entidad = (payload.get("entidad") or "").strip()
    if not url or not entidad:
        return JSONResponse({"error": "Indica el enlace de YouTube y el ayuntamiento."}, status_code=400)
    job = uuid.uuid4().hex[:8]
    _JOBS[job] = {"stage": "En cola", "step": 0, "video_id": "", "done": False, "error": "",
                  "pct": 0, "eta_min": 0}
    threading.Thread(target=_run_generar, daemon=True, args=(
        job, url, _slug(entidad), entidad, (payload.get("fecha") or "").strip(),
        (payload.get("titulo") or "").strip(), (payload.get("orden") or ""))).start()
    return {"job": job}


@app.get("/api/generar/status")
def generar_status(job: str):
    return _JOBS.get(job, {"error": "Trabajo no encontrado.", "done": True})


def _yt_id(url: str) -> str:
    """Extrae el id de 11 caracteres de un enlace de YouTube (o lo devuelve si ya es el id)."""
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})", url or "")
    if m:
        return m.group(1)
    m = re.fullmatch(r"\s*([A-Za-z0-9_-]{11})\s*", url or "")
    return m.group(1) if m else ""


@app.get("/api/check")
def check_exists(url: str):
    """¿Este pleno ya está transcrito? Avisa antes de regenerar para no duplicar el trabajo."""
    vid = _yt_id(url)
    exists = bool(vid) and resolve_path(f"data/transcripts/{vid}.json").exists()
    return {"video_id": vid, "exists": exists}


def _orden_llm(text: str) -> str | None:
    """Extrae el orden del día con el LLM local (robusto a cualquier formato de convocatoria,
    valencià o castellà). Devuelve None si el LLM está apagado o falla (-> respaldo por reglas)."""
    try:
        from src.summarize import _ollama_generate
        cfg = load_config()
        if not getattr(cfg.llm, "enabled", False):
            return None
        prompt = ("Texto de la convocatoria de un pleno municipal (valenciano o castellano). Devuelve "
                  "EXCLUSIVAMENTE la lista de asuntos del ORDEN DEL DÍA del pleno, uno por línea, con el "
                  "TÍTULO COMPLETO de cada punto (el que suele ir en MAYÚSCULAS tras el número de "
                  "expediente; p. ej. 'DICTAMEN RELATIVO A…', 'APROBACIÓN DE…', 'MOCIÓN…'). Si solo hay "
                  "un punto, devuelve solo ese. IGNORA todo lo demás: el preámbulo legal, y las cláusulas "
                  "de la resolución de alcaldía como 'Convocar…', 'Notificar…', 'Comunicar…', 'Publicar…'. "
                  "NO escribas frases de introducción. NO pongas numeración ni el número de expediente. "
                  "Empieza directamente por el primer título.\n\nTEXTO:\n" + text[:6500])
        out = _ollama_generate(cfg.llm.model, prompt, timeout=150)
        bad = re.compile(r"(?i)aqu[ií] tienes|orden del d[ií]a|los puntos del|^claro|^aquí está|:\s*$")
        pts = []
        for ln in out.splitlines():
            ln = ln.strip().lstrip("-•*").strip()
            ln = re.sub(r"^\s*(?:\d{1,2}|primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|"
                        r"octavo|noveno|d[eé]cimo)[.)\-º\s]+", "", ln, flags=re.I).strip()
            if len(ln) >= 8 and not bad.search(ln):
                pts.append(ln)
        return "\n".join(pts[:40]) if pts else None
    except Exception:
        return None


def _orden_from_text(text: str) -> str:
    """Saca el orden del día de una convocatoria (texto del PDF). Primero con el LLM local
    (robusto); si está apagado/falla, respaldo por reglas (localiza el encabezado y parte los
    puntos numerados). El usuario siempre puede revisar/editar el resultado en la UI."""
    # quita el pie de página recurrente de la sede electrónica (se repite en cada página)
    text = "\n".join(ln for ln in text.splitlines() if not re.search(
        r"(?i)documento firmado electr|autenticidad de este|\bcsv\b|sede\.\w+\.\w+", ln))
    by_llm = _orden_llm(text)
    if by_llm:
        return by_llm
    mh = re.search(r"orden del d[ií]a|ordre del dia", text, re.I)
    seg = text[mh.end():] if mh else text
    seg = re.split(r"(?i)\n\s*(?:el alcalde-?president|la alcaldesa|fdo\.?\s*:|firmado\s*:)", seg)[0]
    parts = re.split(r"\n\s*(?:\d{1,2}\s*[.)\-º]|primero|segundo|tercero|cuarto|quinto|sexto|"
                     r"s[eé]ptimo|octavo|noveno|d[eé]cimo)[.)\-\s]+", seg, flags=re.I)
    # cada punto: hasta ~200 car. (en una convocatoria es el título entero; en un acta corta el cuerpo)
    pts = [" ".join(p.split())[:200].strip() for p in parts[1:] if len(p.strip()) >= 10]
    return "\n".join(pts[:40]) if len(pts) >= 2 else " ".join(seg.split())[:2000]


@app.post("/api/extract-orden")
async def extract_orden(request: Request):
    """Recibe una convocatoria en PDF (cuerpo crudo) y devuelve el orden del día extraído."""
    data = await request.body()
    if not data:
        return JSONResponse({"error": "No se recibió el PDF."}, status_code=400)
    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(p.get_text() for p in doc)
    except Exception as e:                                  # noqa: BLE001
        return JSONResponse({"error": f"No se pudo leer el PDF: {e}"}, status_code=400)
    return {"orden": _orden_from_text(text)}


@app.get("/sync", response_class=HTMLResponse)
def sync(video: str):
    """Visor 'acta + vídeo' sincronizado (se sirve por http para que el vídeo se incruste)."""
    from src.sync_viewer import build_html
    tr = resolve_path(f"data/transcripts/{video}.json")
    if not tr.exists():
        return HTMLResponse("<p>Transcripción no encontrada.</p>", status_code=404)
    return HTMLResponse(build_html(str(tr), video))


@app.get("/", response_class=HTMLResponse)
def index():
    return (_HERE / "index.html").read_text(encoding="utf-8")


def _launch_buscador() -> None:
    """Arranca el servicio del buscador del compañero en :8100 si no está ya levantado, para que
    la pestaña Buscar funcione sin tener que lanzarlo a mano. No bloquea ni rompe si falta."""
    import socket
    s = socket.socket()
    s.settimeout(0.4)
    try:
        if s.connect_ex(("127.0.0.1", 8100)) == 0:
            print("[buscador] ya activo en :8100")
            return
    finally:
        s.close()
    bdir = _ROOT / "prueba_buscador" / "prueba_buscador"
    if not (bdir / "src" / "api.py").exists():
        print("[buscador] prueba_buscador no encontrado · la pestaña Buscar pedirá arrancarlo a mano")
        return
    try:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", "8100"],
            cwd=str(bdir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print("[buscador] lanzado en :8100 (búsqueda del corpus del Congreso)")
    except Exception as e:                                  # noqa: BLE001
        print(f"[buscador] no se pudo lanzar ({e}); arráncalo a mano si usas la pestaña Buscar")


@app.on_event("startup")
def _on_startup() -> None:
    _launch_buscador()
    try:      # calienta chroma en el hilo principal: la 1ª init desde un hilo (alertas) es racy
        from src.index import get_collection
        get_collection(_cfg)
    except Exception as e:                                  # noqa: BLE001
        print(f"[chroma] aviso: no se pudo precalentar ({e})")


def main() -> None:
    import uvicorn
    # 0.0.0.0 = accesible desde otros equipos de la MISMA red local (para la presentación: cada
    # uno se conecta a http://<IP-de-este-PC>:8000). El buscador (:8100) sigue en localhost: solo
    # lo llama nuestro server vía proxy, no se expone. OJO: solo en una red de CONFIANZA.
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
