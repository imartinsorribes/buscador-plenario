"""Convierte los documentos markdown de docs/ a PDF limpios (para enseñar/imprimir).

Uso:  python scripts/make_docs_pdf.py docs/carta_interes_ayuntamiento.md [...]
      (sin args -> convierte los dos documentos del piloto)
"""
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

FONT, FONTB, FONTI = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
try:                                                   # Arial (Windows) -> mejor unicode + look oficial
    fd = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
    pdfmetrics.registerFont(TTFont("Doc", os.path.join(fd, "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Doc-B", os.path.join(fd, "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("Doc-I", os.path.join(fd, "ariali.ttf")))
    registerFontFamily("Doc", normal="Doc", bold="Doc-B", italic="Doc-I", boldItalic="Doc-B")
    FONT, FONTB, FONTI = "Doc", "Doc-B", "Doc-I"
except Exception:
    pass

ACCENT = colors.HexColor("#7a1f2b")
INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5a5a5a")
LINE = colors.HexColor("#cccccc")
HEADBG = colors.HexColor("#7a1f2b")

base = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=base["Normal"], fontName=FONTB, fontSize=17, textColor=INK, leading=21, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=base["Normal"], fontName=FONTB, fontSize=12.5, textColor=ACCENT, leading=16, spaceBefore=14, spaceAfter=4)
H3 = ParagraphStyle("H3", parent=base["Normal"], fontName=FONTB, fontSize=10.5, textColor=INK, leading=14, spaceBefore=8, spaceAfter=2)
BODY = ParagraphStyle("BODY", parent=base["Normal"], fontName=FONT, fontSize=9.5, textColor=INK, leading=14, spaceAfter=4, alignment=TA_JUSTIFY)
BULLET = ParagraphStyle("BULLET", parent=BODY, leftIndent=12, spaceAfter=2, alignment=TA_LEFT)
QUOTE = ParagraphStyle("QUOTE", parent=base["Normal"], fontName=FONTI, fontSize=9, textColor=MUTED, leading=13, leftIndent=10, spaceAfter=4)
CELL = ParagraphStyle("CELL", parent=base["Normal"], fontName=FONT, fontSize=8.6, textColor=INK, leading=11)
CELLH = ParagraphStyle("CELLH", parent=CELL, fontName=FONTB, textColor=colors.white)


def _inline(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<font face='" + FONTI + r"'>\1</font>", s)
    return s


def md_to_flowables(md):
    el, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\s*\|", ln):                    # bloque de tabla
            block = []
            while i < len(lines) and re.match(r"^\s*\|", lines[i]):
                block.append(lines[i])
                i += 1
            rows = []
            for r in block:
                if re.match(r"^\s*\|[\s:|-]+\|\s*$", r):
                    continue
                rows.append([c.strip() for c in r.strip().strip("|").split("|")])
            if rows:
                nc = len(rows[0])
                mx = [max(len(r[c]) if c < len(r) else 0 for r in rows) for c in range(nc)]
                tot = sum(mx) or 1
                avail = 17 * cm
                w = [max(1.1 * cm, avail * m / tot) for m in mx]
                w = [x * avail / sum(w) for x in w]
                data = [[Paragraph(_inline(c), CELLH if ri == 0 else CELL) for c in row] for ri, row in enumerate(rows)]
                t = Table(data, colWidths=w, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), HEADBG),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f3ee")]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                    ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                el += [t, Spacer(1, 8)]
            continue
        s = ln.strip()
        if not s:
            el.append(Spacer(1, 3))
        elif s.startswith("# "):
            el += [Paragraph(_inline(s[2:]), H1), HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceBefore=2, spaceAfter=8)]
        elif s.startswith("## "):
            el.append(Paragraph(_inline(s[3:]), H2))
        elif s.startswith("### "):
            el.append(Paragraph(_inline(s[4:]), H3))
        elif s == "---":
            el.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=4, spaceAfter=8))
        elif s.startswith(">"):
            el.append(Paragraph(_inline(s.lstrip("> ").rstrip()), QUOTE))
        elif s.startswith("- "):
            el.append(Paragraph("•&nbsp;&nbsp;" + _inline(s[2:]), BULLET))
        else:
            el.append(Paragraph(_inline(s), BODY))
        i += 1
    return el


def convert(md_path):
    md = open(md_path, encoding="utf-8").read()
    pdf = os.path.splitext(md_path)[0] + ".pdf"

    def deco(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONTI, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f"Pág. {canvas.getPageNumber()}")
        canvas.restoreState()

    SimpleDocTemplate(pdf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=1.8 * cm, bottomMargin=1.6 * cm,
                      title=os.path.basename(pdf)).build(md_to_flowables(md), onFirstPage=deco, onLaterPages=deco)
    print("->", pdf)


if __name__ == "__main__":
    args = sys.argv[1:] or ["docs/carta_interes_ayuntamiento.md", "docs/piloto_y_rgpd.md"]
    for a in args:
        convert(a)
