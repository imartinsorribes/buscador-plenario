"""Genera un ACTA FORMAL del pleno (texto libre + PDF) desde la transcripción ya
diarizada y con nombres (Bloque B). El PDF imita el DIARIO DE SESIONES del Congreso
(XV legislatura): membrete, ORDEN DEL DÍA y cuerpo a dos columnas.

Esto es el segundo entregable de la herramienta de transcripción: de un vídeo de pleno
salen (a) la transcripción buscable y (b) un acta presentable en .txt y .pdf.

Uso:  python -m src.acta data/transcripts/<id>.json [--video <id>]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .config import resolve_path


def _hms(t) -> str:
    t = int(t or 0)
    return f"{t // 3600}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _nint(n: int) -> str:
    return "1 intervención" if n == 1 else f"{n} intervenciones"


_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_larga(fecha: str) -> str:
    """Normaliza la fecha a '27 de enero de 2026' (admite ISO 2026-01-27 o 27/01/2026).
    Si no reconoce el formato, la deja tal cual (p.ej. ya viene escrita en largo)."""
    m = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", fecha or "")
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*", fecha or "")
        if not m:
            return fecha or ""
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    return f"{d} de {_MESES[mo - 1]} de {y}" if 1 <= mo <= 12 else (fecha or "")


def _yt_url(video_id: str | None, sec: float) -> str | None:
    """URL de YouTube al segundo `sec` (para enlazar los tiempos del PDF al vídeo). None si el
    id no parece de YouTube (11 caracteres [A-Za-z0-9_-])."""
    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return None
    return f"https://www.youtube.com/watch?v={video_id}&t={int(sec)}s"


def _find_escudo(entidad: str) -> str | None:
    """Busca el escudo de la entidad en data/ref/escudo_<clave>.png (clave = palabra del nombre,
    p.ej. 'chiva', 'lliria', 'congreso'). Si está, se pinta en el membrete (como el Diario oficial)."""
    import unicodedata
    refdir = resolve_path("data/ref")
    if not refdir.exists():
        return None
    slug = "".join(c for c in unicodedata.normalize("NFKD", (entidad or "").lower())
                   if c.isalnum() or c == " ")
    for f in sorted(refdir.glob("escudo_*.png")):
        key = f.stem[len("escudo_"):]
        if key and key in slug:
            return str(f)
    return None


def _speaker_label(s: dict) -> str:
    """Nombre presentable del orador: usa name/party (Bloque B), NO la etiqueta de diarización."""
    nm = (s.get("name") or "").strip()
    pt = (s.get("party") or "").strip()
    if nm == "(miembro del Gobierno)":
        return "Gobierno"
    if nm in ("", "(sin identificar)"):
        return "Orador sin identificar"
    if nm == "Presidencia":
        return "Presidencia"
    return f"{nm} ({pt})" if pt else nm


def interventions(segs: list[dict]) -> list[dict]:
    """Agrupa segmentos consecutivos del mismo orador en intervenciones. Cuenta el solape
    (segmentos con `overlap`) para poder marcar las intervenciones con cruce de voces."""
    out: list[dict] = []
    for s in sorted(segs, key=lambda x: x.get("start", 0.0)):
        who = _speaker_label(s)
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        ov = 1 if s.get("overlap") else 0
        if out and out[-1]["who"] == who:
            out[-1]["text"] += " " + txt
            out[-1]["end"] = s.get("end", out[-1]["end"])
            out[-1]["nseg"] += 1
            out[-1]["nov"] += ov
        else:
            out.append({"who": who, "start": s.get("start", 0.0), "end": s.get("end", 0.0),
                        "text": txt, "nseg": 1, "nov": ov})
    return out


def _cruce(iv: dict) -> bool:
    """¿La intervención tiene cruce de voces significativo? (>30% de sus segmentos solapados)."""
    return iv.get("nov", 0) > 0 and iv["nov"] / max(iv.get("nseg", 1), 1) > 0.30


def _talk_stats(segs: list[dict]) -> dict:
    """Tiempo total hablado por orador y por partido (segundos). Para las estadísticas del acta."""
    by_who: dict[str, float] = {}
    by_party: dict[str, float] = {}
    for s in segs:
        d = max(0.0, float(s.get("end", 0) or 0) - float(s.get("start", 0) or 0))
        if d <= 0:
            continue
        by_who[_speaker_label(s)] = by_who.get(_speaker_label(s), 0.0) + d
        pt = (s.get("party") or "").strip()
        if pt:
            by_party[pt] = by_party.get(pt, 0.0) + d
    total = sum(by_who.values()) or 1.0
    return {"speaker": sorted(by_who.items(), key=lambda x: -x[1]),
            "party": sorted(by_party.items(), key=lambda x: -x[1]),
            "total": total}


_PUNTO_RE = re.compile(
    r"\bpunto\s+(?:n[uú]mero\s+|n[º°]\.?\s*)?"
    r"(\d{1,2}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|"
    r"primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)\b", re.I)


def detect_points(segs: list[dict]) -> list[dict]:
    """Detecta los puntos del orden del día por el anuncio del que preside ('punto número uno/dos…')
    y extrae un título aproximado. Devuelve [{start, title}] en orden. Vacío si no hay anuncios."""
    ss = sorted(segs, key=lambda x: x.get("start", 0.0))
    pts: list[dict] = []
    for idx, s in enumerate(ss):
        t = s.get("text") or ""
        m = _PUNTO_RE.search(t)
        if not m:
            continue
        st = s.get("start", 0.0)
        if pts and st - pts[-1]["start"] < 2:        # evita disparos dobles muy juntos
            continue
        # título: cola del cue + los 2 segmentos siguientes (la descripción suele venir partida);
        # se descartan muletillas cortas ("intervención.") y se coge la primera frase con sustancia.
        ctx = t[m.end():] + " " + " ".join((ss[idx + k].get("text") or "") for k in (1, 2) if idx + k < len(ss))
        parts = [p.strip() for p in re.split(r"[.?]\s", ctx) if len(p.strip()) >= 18]
        title = (parts[0] if parts else ctx).strip(" ,.;:—-") or "(punto)"
        if len(title) > 90:                          # no cortar a mitad de palabra
            title = title[:90].rsplit(" ", 1)[0] + "…"
        pts.append({"start": st, "title": title})
    return pts


def _point_index(t, pts) -> int:
    """Nº de punto (1..N) para el instante t; 0 = apertura / antes del primer punto.
    Ignora puntos sin localizar en el audio (start=None: vienen de la convocatoria)."""
    n = 0
    for i, p in enumerate(pts):
        if p.get("start") is not None and t >= p["start"]:
            n = i + 1
    return n


def _desarrollo(segments, pts):
    """Cuerpo del acta como secuencia de elementos: encabezados de punto + intervenciones.
    Trabaja a nivel de SEGMENTO para colocar bien el encabezado de cada punto aunque el que
    preside lo anuncie a mitad de una intervención (parte la intervención en el límite del punto)."""
    items, curp, cur = [], 0, None
    for s in sorted(segments, key=lambda x: x.get("start", 0.0)):
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        pi = _point_index(s.get("start", 0.0), pts) if pts else 0
        if pts and pi != curp:
            cur = None
            if pi >= 1:
                items.append(("HEAD", pi, pts[pi - 1]["title"]))
            curp = pi
        who = _speaker_label(s)
        ov = 1 if s.get("overlap") else 0
        if cur and cur["who"] == who:
            cur["text"] += " " + txt
            cur["end"] = s.get("end", cur["end"])
            cur["nseg"] += 1
            cur["nov"] += ov
        else:
            cur = {"who": who, "start": s.get("start", 0.0), "end": s.get("end", 0.0),
                   "text": txt, "nseg": 1, "nov": ov}
            items.append(cur)
    return items


def _asistentes(ivs: list[dict], stats: dict) -> list[dict]:
    """Oradores de la sesión: nombre(+partido), nº de intervenciones y tiempo. Ordenado por tiempo.
    Es la base de la lista de ASISTENTES del acta formal."""
    n_by: dict[str, int] = {}
    for iv in ivs:
        n_by[iv["who"]] = n_by.get(iv["who"], 0) + 1
    secs = dict(stats["speaker"])                      # label -> segundos (misma etiqueta que iv['who'])
    rows = [{"who": w, "n": n, "sec": secs.get(w, 0.0)} for w, n in n_by.items()]
    return sorted(rows, key=lambda r: -r["sec"])


def _strip(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower())
                   if not unicodedata.combining(c))


def _vote_events(segs: list[dict]) -> list[tuple[float, str]]:
    """Resultados de votación detectados, con su instante. Por NÚMEROS (Congreso, vía extract_votes)
    o por FÓRMULA municipal ('se aprueba por mayoría/unanimidad', 'queda rechazado'). Cada uno se
    coloca luego en su punto del orden del día. (Las votaciones por VISIÓN del vídeo las añade aparte
    el módulo del compañero.)"""
    from .diario import extract_votes
    out: list[tuple[float, str]] = []
    _FORMULAS = [("por unanimidad", "Aprobado por unanimidad."),
                 ("se aprueba por mayoria", "Aprobado por mayoría."),
                 ("queda aprobad", "Aprobado."), ("se aprueba", "Aprobado."),
                 ("queda rechazad", "Rechazado."), ("se rechaza", "Rechazado.")]
    for s in sorted(segs, key=lambda x: x.get("start", 0.0)):
        txt = s.get("text", "") or ""
        st = s.get("start", 0.0)
        votes = extract_votes(txt)
        if votes:
            for v in votes:
                parts = ([f"votos emitidos, {v['emitidos']}"] if v.get("emitidos") else []) + \
                        [f"a favor, {v['a_favor']}", f"en contra, {v['en_contra']}"] + \
                        ([f"abstenciones, {v['abstenciones']}"] if v.get("abstenciones") is not None else [])
                out.append((st, "Efectuada la votación, dio el siguiente resultado: " + "; ".join(parts) + "."))
            continue
        low = _strip(txt)
        # solo en segmentos que SON de votación (evita pillar 'se aprueba' suelto en el debate)
        if not any(c in low for c in ("voto", "votaci", "a favor", "en contra", "abstenc",
                                      "unanim", "asentim")):
            continue
        for key, res in _FORMULAS:
            if key in low:
                out.append((st, res)); break
    return out


def _meta(video_id: str) -> dict:
    try:
        from .db import connect, list_plenos
        con = connect()
        hit = next((p for p in list_plenos(con) if p["video_id"] == video_id), {})
        con.close()
        return hit
    except Exception:
        return {}


def _write_pdf(path, entidad, fecha, titulo, ivs, pts=None, items=None, stats=None,
               asis=None, votes_by_pt=None, dur=0.0, video_id=None, auto_names=None, escudo=None):
    """PDF al estilo del DIARIO DE SESIONES del Congreso (XV leg.): tipografía SANS, membrete
    'DIARIO DE SESIONES', fila Año/Núm/Pág, PRESIDENCIA, ORDEN DEL DÍA y cuerpo a DOS COLUMNAS
    con el orador en versalitas ('NOMBRE: …'). Adaptado a un ayuntamiento."""
    import re

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, NextPageTemplate,
                                    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

    INK = colors.HexColor("#111111")
    GRAY = colors.HexColor("#6b6b6b")
    SOFT = colors.HexColor("#cccccc")
    ACCENT = colors.HexColor("#7a1f2b")
    W, H = A4
    LM = RM = 1.6 * cm
    TM = 1.4 * cm
    BM = 1.5 * cm
    UW = W - LM - RM
    GUT = 0.7 * cm
    CW = (UW - GUT) / 2
    m = re.search(r"(?:19|20)\d{2}", fecha or "")
    year = m.group(0) if m else ""

    base = getSampleStyleSheet()

    def S(name, **k):
        return ParagraphStyle(name, parent=base["Normal"], **k)

    st_inst = S("inst", fontName="Helvetica-Bold", fontSize=12, textColor=GRAY, alignment=TA_CENTER, leading=14)
    st_mast = S("mast", fontName="Helvetica-Bold", fontSize=19, textColor=INK, alignment=TA_CENTER, leading=22)
    st_org = S("org", fontName="Helvetica-Bold", fontSize=13, textColor=INK, alignment=TA_CENTER, leading=16)
    st_pres = S("pres", fontName="Helvetica-Bold", fontSize=11, textColor=INK, alignment=TA_CENTER, leading=14, spaceBefore=10)
    st_sess = S("sess", fontName="Helvetica-Bold", fontSize=10.5, textColor=INK, alignment=TA_CENTER, leading=13)
    st_cel = S("cel", fontName="Helvetica-Bold", fontSize=12, textColor=INK, alignment=TA_CENTER, leading=15, spaceBefore=2)
    st_od = S("od", fontName="Helvetica-Bold", fontSize=9.5, textColor=INK, spaceBefore=14, spaceAfter=6)
    st_sn = S("sn", fontName="Helvetica", fontSize=9, textColor=INK, leading=13)
    st_st = S("st", fontName="Helvetica-Bold", fontSize=9, textColor=INK, alignment=TA_RIGHT, leading=13)
    st_body = S("body", fontName="Helvetica", fontSize=9.3, textColor=INK, alignment=TA_JUSTIFY,
                leading=12.8, spaceAfter=5, firstLineIndent=15)

    chair = next((iv["who"] for iv in ivs
                  if "presid" in iv["who"].lower() or "alcald" in iv["who"].lower()), "")

    info = Table([[Paragraph(f"Año {year}" if year else "", st_sn),
                   Paragraph("SESIÓN PLENARIA", S("c", fontName="Helvetica-Bold", fontSize=9.5, alignment=TA_CENTER)),
                   Paragraph("Pág. 1", S("r", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT))]],
                  colWidths=[UW * 0.33, UW * 0.34, UW * 0.33])
    info.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, INK), ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
                              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                              ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    _org = "DEL CONGRESO DE LOS DIPUTADOS" if "congreso" in (entidad or "").lower() else "DEL PLENO MUNICIPAL"
    story = []
    if escudo:                                    # escudo de la entidad (como el Diario oficial)
        try:
            from reportlab.platypus import Image as RLImage
            esc_img = RLImage(escudo, width=1.7 * cm, height=1.7 * cm)
            esc_img.hAlign = "CENTER"
            story += [esc_img, Spacer(1, 3)]
        except Exception:
            pass
    story += [Paragraph(_esc(entidad).upper(), st_inst),
              Paragraph("DIARIO DE SESIONES", st_mast),
              Paragraph(_org, st_org),
              Spacer(1, 9), info, Spacer(1, 6)]
    if chair and chair.strip().lower() not in ("presidencia", "alcaldía", "alcaldia"):
        story.append(Paragraph(f"PRESIDENCIA DE {_esc(chair).upper()}", st_pres))
    if titulo:
        story.append(Paragraph(f"Sesión plenaria — {_esc(titulo)}", st_sess))
    if fecha:
        story.append(Paragraph(f"celebrada el {_esc(fecha)}", st_cel))
    story.append(HRFlowable(width=70, thickness=0.8, color=INK, spaceBefore=8, spaceAfter=2, hAlign="CENTER"))

    st_pt = ParagraphStyle("pt", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10.5,
                           textColor=ACCENT, spaceBefore=14, spaceAfter=6, leading=13)
    st_vote = ParagraphStyle("vote", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9,
                             textColor=ACCENT, leftIndent=10, spaceBefore=3, spaceAfter=9, leading=12)

    # apertura + ASISTENTES (acta formal)
    if asis:
        story.append(Paragraph(f"<font size=8 color='#6b6b6b'>Se abre la sesión · duración "
                               f"{_hms(dur)} · intervienen {len(asis)} oradores</font>",
                               S("ap", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)))
        story.append(Paragraph("ASISTENTES:", st_od))
        _auto = auto_names or set()
        if _auto:
            story.append(Paragraph("<font size=8 color='#6b6b6b'><i>Nombres automáticos "
                                   "sin confirmar (pendientes de validación).</i></font>", st_sn))
        arows = [[Paragraph("<b>Orador</b>", st_sn), Paragraph("<b>Intervenc.</b>", st_st),
                  Paragraph("<b>Tiempo</b>", st_st)]]
        for a in asis:
            mk = " <font size=7 color='#9a9a9a'>(sin confirmar)</font>" if a["who"] in _auto else ""
            arows.append([Paragraph(_esc(a["who"]) + mk, st_sn), Paragraph(str(a["n"]), st_st),
                          Paragraph(_hms(a["sec"]), st_st)])
        ta = Table(arows, colWidths=[UW - 4.4 * cm, 2.4 * cm, 2.0 * cm])
        ta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK),
                                ("LINEBELOW", (0, 1), (-1, -2), 0.25, SOFT)]))
        story.append(ta)

    story.append(Paragraph("ORDEN DEL DÍA:", st_od))
    if pts:
        rows = []
        for i, p in enumerate(pts):
            located = p.get("start") is not None
            sub = _nint(p.get("nint", 0)) if located else "no localizado en el audio"
            rows.append([Paragraph(f"<b>{i+1}.</b>&nbsp; {_esc(p['title'])}"
                                   f"<br/><font size=8 color='#6b6b6b'>{sub}</font>", st_sn),
                         Paragraph(_hms(p["start"]) if located else "—", st_st)])
        t = Table(rows, colWidths=[UW - 2.4 * cm, 2.4 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                               ("LINEBELOW", (0, 0), (-1, -2), 0.25, SOFT)]))
        story.append(t)
    else:
        story.append(Paragraph("<i>(Los puntos del orden del día no se han detectado "
                               "automáticamente; se completan con la convocatoria oficial.)</i>",
                               S("odn", fontName="Helvetica-Oblique", fontSize=8.5, textColor=GRAY)))

    # --- estadísticas: tiempo por orador y por partido (lo pidió el ayuntamiento) ---
    if stats and stats.get("speaker"):
        def _stat_table(titulo_col, datos):
            head = [Paragraph(f"<b>{titulo_col}</b>", st_sn),
                    Paragraph("<b>Tiempo</b>", st_st), Paragraph("<b>%</b>", st_st)]
            body_rows = [head] + [
                [Paragraph(_esc(nm), st_sn), Paragraph(_hms(sec), st_st),
                 Paragraph(f"{sec / stats['total']:.0%}", st_st)] for nm, sec in datos]
            tb = Table(body_rows, colWidths=[UW - 4.4 * cm, 2.4 * cm, 2.0 * cm])
            tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                                    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK),
                                    ("LINEBELOW", (0, 1), (-1, -2), 0.25, SOFT)]))
            return tb
        story.append(Paragraph("ESTADÍSTICAS:", st_od))
        story.append(_stat_table("Tiempo por orador", stats["speaker"][:12]))
        if stats.get("party"):
            story.append(Spacer(1, 8))
            story.append(_stat_table("Tiempo por partido", stats["party"]))

    story += [NextPageTemplate("body"), PageBreak()]
    vbp = votes_by_pt or {}
    cur_pt = 0

    def _emit_votes(p):
        for res in vbp.get(p, []):
            story.append(Paragraph(f"» VOTACIÓN: {_esc(res)}", st_vote))
    for it in (items if items is not None else ivs):
        if isinstance(it, tuple) and it and it[0] == "HEAD":
            _emit_votes(cur_pt)                          # votación del punto que se cierra
            cur_pt = it[1]
            story.append(Paragraph(f"PUNTO {it[1]}.&nbsp;&nbsp;{_esc(it[2]).upper()}", st_pt))
            continue
        cruce = '<i>(Cruce de intervenciones.)</i> ' if _cruce(it) else ''
        ts = _hms(it["start"])
        url = _yt_url(video_id, it["start"])
        tstamp = (f'<a href="{url}"><font size=8 color="#2f5b8f">[{ts}]</font></a>' if url
                  else f'<font size=8 color="#6b6b6b">[{ts}]</font>')
        story.append(Paragraph(f'{tstamp} <b>{_esc(it["who"]).upper()}:</b> {cruce}{_esc(it["text"])}',
                               st_body))
    _emit_votes(cur_pt)                                  # votación del último punto
    if dur:
        story.append(Paragraph(f"<i>Se levanta la sesión. Duración total de la sesión: {_hms(dur)}.</i>",
                               S("close", fontName="Helvetica-Oblique", fontSize=9,
                                 textColor=GRAY, spaceBefore=14)))

    def deco(canvas, doc, first=False):
        canvas.saveState()
        if not first:
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawCentredString(W / 2, H - TM + 0.45 * cm, f"DIARIO DE SESIONES — {entidad.upper()}")
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(GRAY)
            canvas.drawCentredString(W / 2, H - TM + 0.18 * cm,
                                     "CONGRESO DE LOS DIPUTADOS" if "congreso" in (entidad or "").lower() else "PLENO MUNICIPAL")
            canvas.setStrokeColor(INK)
            canvas.setLineWidth(0.6)
            canvas.line(LM, H - TM - 0.02 * cm, W - RM, H - TM - 0.02 * cm)
            canvas.setFont("Helvetica", 7.5)
            if fecha:
                canvas.drawString(LM, H - TM - 0.33 * cm, fecha)
            canvas.drawRightString(W - RM, H - TM - 0.33 * cm, f"Pág. {canvas.getPageNumber()}")
        canvas.setStrokeColor(SOFT)
        canvas.setLineWidth(0.5)
        canvas.line(LM, 1.1 * cm, W - RM, 1.1 * cm)
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.setFillColor(GRAY)
        canvas.drawString(LM, 0.8 * cm, "Transcripción automática · no sustituye al acta oficial")
        if first:
            canvas.drawRightString(W - RM, 0.8 * cm, "Pág. 1")
        canvas.restoreState()

    first_frame = Frame(LM, BM, UW, H - TM - BM, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    btop = H - TM - 1.0 * cm
    body_frame = Frame(LM, BM, UW, btop - BM, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(str(path), pagesize=A4, title="Diario de sesiones", author=entidad)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=lambda c, d: deco(c, d, True)),
        PageTemplate(id="body", frames=[body_frame], onPage=lambda c, d: deco(c, d, False)),
    ])
    doc.build(story)


_CONNECT = {"i", "y", "e", "de", "del", "la", "las", "los", "el", "da", "do", "san", "von"}


def _name_ok(nm: str) -> bool:
    """¿El nombre auto es lo bastante fiable para mostrarlo? Exige ≥2 tokens 'de verdad'
    (ignorando conectores i/de/la…) de ≥3 letras. Filtra los rotos del ASR ('Fi', 'ti Zabal')."""
    toks = [t for t in nm.split() if t.lower() not in _CONNECT]
    return len(toks) >= 2 and all(len(t) >= 3 for t in toks)


def _assign_labels(segs: list[dict]) -> set[str]:
    """Etiqueta cada orador de forma consistente POR CLUSTER (una voz = una etiqueta), a prueba de
    la fusión de clusters. Reglas:
      - sesión degenerada (un solo nombre para todo = nombrado fallido) -> 'Voz N' a todos;
      - por cluster, nombre mayoritario: Presidencia/Gobierno se respetan; nombre real PLAUSIBLE
        se conserva (y se marca 'sin confirmar'); nombre vacío/marcador/mal transcrito -> 'Voz N'.
    'Voz N' = orden de aparición (coincide con el visor). Devuelve las etiquetas que son
    nombre-automático (para marcarlas como SIN CONFIRMAR en el acta)."""
    from collections import Counter
    blind = re.compile(r"^Voz \d+$")
    order: dict[str, int] = {}
    by_sp: dict[str, list] = {}
    for s in sorted(segs, key=lambda x: x.get("start", 0.0)):
        sp = s.get("speaker")
        if sp is not None and sp not in order:
            order[sp] = len(order) + 1
        by_sp.setdefault(sp, []).append(s)
    degenerate = len({(s.get("name") or "").strip() for s in segs}) <= 1
    auto: set[str] = set()
    for sp, ss in by_sp.items():
        voz = f"Voz {order.get(sp, 0)}"
        if degenerate:
            label, party = voz, ""
        else:
            nm = Counter((s.get("name") or "").strip() for s in ss).most_common(1)[0][0]
            pty = Counter((s.get("party") or "").strip() for s in ss).most_common(1)[0][0]
            if nm == "Presidencia":
                label, party = "Presidencia", ""
            elif nm in ("(miembro del Gobierno)", "Gobierno"):
                label, party = "(miembro del Gobierno)", ""
            elif (not nm) or nm == "(sin identificar)" or blind.match(nm) or not _name_ok(nm):
                label, party = voz, ""
            else:
                label, party = nm, pty
                auto.add(f"{nm} ({pty})" if pty else nm)
        for s in ss:
            s["name"], s["party"] = label, party
    return auto


def _vision_votes(vid: str) -> list[tuple[float, str]]:
    """Votaciones leídas por VISIÓN (recuento de manos, módulo del compañero), si existe
    data/votes/<vid>.json. Devuelve [(instante, línea)] para colocarlas en su punto."""
    p = resolve_path(f"data/votes/{vid}.json")
    if not p.exists():
        return []
    out: list[tuple[float, str]] = []
    try:
        for r in json.loads(p.read_text(encoding="utf-8")):
            c = r.get("recuento", {})
            a, en, ab = c.get("a_favor", 0), c.get("en_contra", 0), c.get("abstencion", 0)
            outcome = "Aprobado por mayoría" if a > en else ("Rechazado" if en > a else "Empate")
            out.append((float(r.get("t", 0.0)),
                        f"a favor {a}, en contra {en}, abstenciones {ab} (recuento aproximado por "
                        f"visión del vídeo). {outcome}."))
    except Exception:
        return []
    return out


def build_acta(transcript_path, video_id: str | None = None, out_dir: str = "data/actas",
               orden_del_dia: list[str] | None = None):
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    auto_names = _assign_labels(data["segments"])
    ivs = interventions(data["segments"])
    vid = video_id or Path(transcript_path).stem
    m = _meta(vid)
    entidad = m.get("entidad_nombre") or "Congreso de los Diputados"
    fecha = _fecha_larga(m.get("fecha") or "")
    # título solo si es de verdad (de la BD); NUNCA el id del vídeo (salía "Sesión plenaria — <id>")
    titulo = (m.get("titulo") or "").strip()

    # Índice por PUNTOS del orden del día (lo que pidió el ayuntamiento): detectamos los
    # límites de cada punto por el anuncio del que preside ('punto número uno/dos…') y, para
    # cada uno, mostramos tiempo de inicio y nº de intervenciones. El título es orientativo
    # (exacto cuando se aporte la convocatoria).
    pts = detect_points(data["segments"])
    if orden_del_dia:
        # convocatoria oficial aportada: los TÍTULOS son los oficiales (por orden); conservamos
        # los tiempos detectados. Si hay más puntos oficiales que localizados, se listan sin tiempo.
        for i, t in enumerate(orden_del_dia):
            if i < len(pts):
                pts[i]["title"] = t
            else:
                pts.append({"start": None, "title": t, "nint": 0})
    items = _desarrollo(data["segments"], pts)
    # nº de intervenciones por punto: contadas sobre el cuerpo YA partido por puntos
    # (una intervención larga del que preside se reparte entre apertura/puntos en su límite).
    counts: dict[int, int] = {}
    curp = 0
    for it in items:
        if isinstance(it, tuple) and it and it[0] == "HEAD":
            curp = it[1]
        elif isinstance(it, dict):
            counts[curp] = counts.get(curp, 0) + 1
    for i, p in enumerate(pts):
        p["nint"] = counts.get(i + 1, 0)
    stats = _talk_stats(data["segments"])
    asis = _asistentes(ivs, stats)                       # ASISTENTES (oradores)
    spoken = [s for s in data["segments"] if (s.get("text") or "").strip()]
    dur = (max(s.get("end", 0.0) for s in spoken) - min(s.get("start", 0.0) for s in spoken)) if spoken else 0.0
    # votaciones colocadas en su punto. La VISIÓN (recuento de manos) tiene prioridad cuando existe
    # (da números); el audio ("se aprueba por mayoría") solo donde no hay lectura por visión.
    votes_by_pt: dict[int, list[str]] = {}
    vis_pts = set()
    for t, line in _vision_votes(vid):
        pi = _point_index(t, pts) if pts else 0
        votes_by_pt.setdefault(pi, []).append(line)
        vis_pts.add(pi)
    for t, res in _vote_events(data["segments"]):
        pi = _point_index(t, pts) if pts else 0
        if pi not in vis_pts:
            votes_by_pt.setdefault(pi, []).append(res)

    out = resolve_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --- acta en texto libre (híbrido: encabezado + asistentes + orden del día + cuerpo + votación) ---
    L = ["ACTA DE LA SESIÓN PLENARIA", entidad + (f" — {fecha}" if fecha else "")]
    if titulo:
        L.append(titulo)
    L += ["", f"Se abre la sesión. Duración: {_hms(dur)}. Intervienen {len(asis)} oradores."]
    L += ["", "=" * 70, "ASISTENTES (oradores)", "=" * 70, ""]
    if auto_names:
        L += ["(Nombres automáticos SIN CONFIRMAR — pendientes de etiquetado/validación.)", ""]
    for a in asis:
        mark = "   (sin confirmar)" if a["who"] in auto_names else ""
        L.append(f"  {a['who'][:42]:42s}  {_nint(a['n']):>16}  ·  {_hms(a['sec'])}{mark}")
    L += ["", "=" * 70, "ORDEN DEL DÍA", "=" * 70, ""]
    if pts:
        for i, p in enumerate(pts):
            L.append(f"  {i+1}.  {p['title']}")
            if p.get("start") is not None:
                L.append(f"        inicio {_hms(p['start'])} · {_nint(p['nint'])}")
            else:
                L.append("        (del orden del día; no localizado en el audio)")
    else:
        L.append("  (Los puntos no se han detectado automáticamente;")
        L.append("   se completan con la convocatoria / orden del día oficial.)")
    L += ["", "=" * 70, "ESTADÍSTICAS", "=" * 70, ""]
    L.append("Tiempo por orador:")
    for who, sec in stats["speaker"][:15]:
        L.append(f"  {who[:34]:34s} {_hms(sec):>9}  ({sec/stats['total']:.0%})")
    if stats["party"]:
        L += ["", "Tiempo por partido:"]
        for pt, sec in stats["party"]:
            L.append(f"  {pt[:34]:34s} {_hms(sec):>9}  ({sec/stats['total']:.0%})")
    L += ["", "=" * 70, "DESARROLLO DE LA SESIÓN", "=" * 70, ""]
    cur_pt = 0

    def _flush_votes(p):
        for res in votes_by_pt.get(p, []):
            L.extend([f"    » VOTACIÓN: {res}", ""])
    for it in items:
        if isinstance(it, tuple) and it and it[0] == "HEAD":
            _flush_votes(cur_pt)                         # cierra el punto anterior con su votación
            cur_pt = it[1]
            L += ["", f"----- PUNTO {it[1]}.  {it[2]} -----", ""]
            continue
        L.append(f"[{_hms(it['start'])}] {it['who']}:")
        pre = "(Cruce de intervenciones.) " if _cruce(it) else ""
        L.append(f"    {pre}{it['text']}")
        L.append("")
    _flush_votes(cur_pt)                                 # votación del último punto
    L += ["", f"Se levanta la sesión. (Duración total: {_hms(dur)}.)"]
    txt_path = out / f"{vid}.acta.txt"
    txt_path.write_text("\n".join(L), encoding="utf-8")

    # --- acta en PDF ---
    pdf_path = out / f"{vid}.acta.pdf"
    _write_pdf(pdf_path, entidad, fecha, titulo, ivs, pts, items, stats,
               asis=asis, votes_by_pt=votes_by_pt, dur=dur, video_id=vid, auto_names=auto_names,
               escudo=_find_escudo(entidad))

    print(f"[acta] {len(ivs)} intervenciones · {entidad} {fecha}")
    print(f"[acta] -> {txt_path}")
    print(f"[acta] -> {pdf_path}")
    return txt_path, pdf_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el acta formal del pleno (txt + pdf).")
    ap.add_argument("transcript", help="JSON de transcripción ya diarizada y con nombres")
    ap.add_argument("--video", default=None, help="video_id (para sacar entidad/fecha de la BD)")
    args = ap.parse_args()
    build_acta(args.transcript, video_id=args.video)


if __name__ == "__main__":
    main()
