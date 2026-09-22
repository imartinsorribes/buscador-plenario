"""Convierte uno o varios .md (con tablas markdown) a un único PDF legible (reportlab).

Uso:  python scripts/md_to_pdf.py salida.pdf informe1.md [informe2.md ...]
"""
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)


def esc(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", s)   # cursiva *texto*
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    # enlaces markdown [texto](url) y URLs sueltas -> CLICABLES en el PDF (p. ej. el minuto
    # exacto del vídeo: youtu.be/ID?t=N). Color corporativo + subrayado para que se vean.
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" color="#7a1f2b"><u>\1</u></a>', s)
    s = re.sub(r"(?<!href=\")(?<!>)(https?://[^\s<)\]]*[^\s<)\].,;:])",
               r'<a href="\1" color="#7a1f2b"><u>\1</u></a>', s)
    return s


def main() -> None:
    out, mds = sys.argv[1], sys.argv[2:]
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontSize=16, alignment=0, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], textColor=colors.HexColor("#7a1f2b"), spaceBefore=10)
    h3 = ParagraphStyle("h3", parent=base["Heading3"], spaceBefore=6)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=base["Normal"], fontSize=7.3, leading=8.8)
    cellh = ParagraphStyle("cellh", parent=cell, textColor=colors.white)

    page = landscape(A4)
    doc = SimpleDocTemplate(out, pagesize=page, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm, title="Informes — Buscador Plenario")
    usable = page[0] - 2.4 * cm
    el = []
    for k, md in enumerate(mds):
        if k > 0:
            el.append(PageBreak())
        lines = Path(md).read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("|"):
                block = []
                while i < len(lines) and lines[i].startswith("|"):
                    block.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                    i += 1
                block = [r for r in block if not all(set(c) <= set("-: ") for c in r)]
                if not block:
                    continue
                ncol = max(len(r) for r in block)
                data = [[Paragraph(esc(c), cellh if ri == 0 else cell) for c in (r + [""] * (ncol - len(r)))]
                        for ri, r in enumerate(block)]
                t = Table(data, colWidths=[usable / ncol] * ncol, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7a1f2b")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f3ee")]),
                ]))
                el += [t, Spacer(1, 0.3 * cm)]
                continue
            img = re.match(r"^!\[[^\]]*\]\(([^)]+)\)\s*$", ln.strip())
            if img and Path(img.group(1)).exists():          # imagen markdown -> incrustada
                from reportlab.lib.utils import ImageReader
                from reportlab.platypus import Image as RLImage
                iw, ih = ImageReader(img.group(1)).getSize()
                w = min(usable * 0.72, 16 * cm)
                h = w * ih / iw
                if h > 13 * cm:               # páginas verticales: que no desborden el marco
                    h = 13 * cm
                    w = h * iw / ih
                el += [RLImage(img.group(1), width=w, height=h), Spacer(1, 0.25 * cm)]
                i += 1
                continue
            if ln.startswith("### "):
                el.append(Paragraph(esc(ln[4:]), h3))
            elif ln.startswith("## "):
                el.append(Paragraph(esc(ln[3:]), h2))
            elif ln.startswith("# "):
                el.append(Paragraph(esc(ln[2:]), h1))
            elif ln.strip().startswith(("- ", "* ")):
                el.append(Paragraph("• " + esc(ln.strip()[2:]), body))
            elif ln.strip():
                el.append(Paragraph(esc(ln), body))
            else:
                el.append(Spacer(1, 0.12 * cm))
            i += 1
    doc.build(el)
    print("PDF ->", out)


if __name__ == "__main__":
    main()
