"""Vídeo demo COMPLETO de la parte 'generar acta' (Chiva): app -> acta real -> visor -> resultados.

Recrea la UI con Pillow y usa los ASSETS REALES (el acta PDF de verdad y un fotograma del vídeo
de Chiva). Frames -> MP4 con ffmpeg. Pensado para enseñarlo en un chequeo.

Uso:  python scripts/make_demo_pro.py   ->  data/processed/demo_chiva.mp4
"""
import json
import os
import subprocess

import fitz
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
PAPER = (250, 249, 246)
INK = (26, 26, 26)
ACCENT = (122, 31, 43)
BLUE = (47, 91, 143)
MUTED = (107, 107, 107)
HINT = (170, 165, 158)
LINE = (226, 224, 219)
GREEN = (47, 111, 58)
WHITE = (255, 255, 255)
MX = 120
FD = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
FR = "data/processed/_proframes"
OUT = "data/processed/demo_chiva.mp4"
VID = "TN_gTdxQXA4"


def F(name, s):
    return ImageFont.truetype(os.path.join(FD, name), s)


SERIF = lambda s: F("georgiab.ttf", s)
SERIF_R = lambda s: F("georgia.ttf", s)
SANS = lambda s: F("arial.ttf", s)
SANSB = lambda s: F("arialbd.ttf", s)


def wrap(d, t, f, mw):
    out, ln = [], ""
    for w in t.split():
        s = (ln + " " + w).strip()
        if d.textlength(s, font=f) <= mw:
            ln = s
        else:
            out.append(ln); ln = w
    if ln:
        out.append(ln)
    return out


def para(d, x, y, t, f, fill, mw, lh=1.35):
    for ln in wrap(d, t, f, mw):
        d.text((x, y), ln, font=f, fill=fill); y += int(f.size * lh)
    return y


def chrome(active="generar"):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.text((MX, 40), "D I A R I O   D E   P L E N O S", font=SANSB(12), fill=ACCENT)
    d.text((MX, 62), "Buscador de sesiones plenarias", font=SERIF(34), fill=INK)
    d.line([(MX, 132), (W - MX, 132)], fill=LINE, width=1)
    tx = MX
    for label, key in [("Generar acta", "generar"), ("Buscar", "buscar"), ("Ciudadano", "ciudadano")]:
        on = key == active
        f = SANSB(16) if on else SANS(16)
        d.text((tx, 150), label, font=f, fill=ACCENT if on else MUTED)
        w = d.textlength(label, font=f)
        if on:
            d.rectangle([tx, 176, tx + w, 178], fill=ACCENT)
        tx += w + 30
    d.line([(MX, 178), (W - MX, 178)], fill=LINE, width=1)
    d.text((MX, H - 40), "Buscador Plenario Inteligente   ·   IDAL · Reto 2", font=SANS(13), fill=MUTED)
    return img, d


def cursor(d, x, y):
    d.polygon([(x, y), (x, y + 24), (x + 6, y + 17), (x + 11, y + 28), (x + 15, y + 26),
               (x + 10, y + 15), (x + 17, y + 15)], fill=WHITE, outline=INK)


def check(d, x, y, s, color, w=4):
    d.line([(x, y + s * 0.55), (x + s * 0.35, y + s * 0.9)], fill=color, width=w)
    d.line([(x + s * 0.35, y + s * 0.9), (x + s * 0.95, y + s * 0.12)], fill=color, width=w)


def field(d, x, y, label, value, filled, w):
    d.text((x, y), label, font=SANSB(10), fill=MUTED)
    d.text((x, y + 20), value, font=SANS(18), fill=(INK if filled else HINT))
    d.line([(x, y + 50), (x + w, y + 50)], fill=LINE, width=1)


def form_frame(filled, cur):
    img, d = chrome()
    y = 210
    d.text((MX, y), "Genera el acta desde el vídeo del pleno", font=SERIF(25), fill=INK)
    y += 42
    y = para(d, MX, y, "Pega el enlace de YouTube: la herramienta lo descarga, transcribe, separa "
             "las voces, las nombra y genera el acta con estilo de Diario de Sesiones.",
             SANS(15), MUTED, 900) + 14
    field(d, MX, y, "ENLACE DE YOUTUBE DEL PLENO",
          f"https://www.youtube.com/watch?v={VID}" if filled else "https://www.youtube.com/watch?v=…", filled, 900)
    y += 82
    field(d, MX, y, "AYUNTAMIENTO", "Ayuntamiento de Chiva" if filled else "Ayuntamiento de…", filled, 400)
    field(d, MX + 460, y, "FECHA (OPCIONAL)", "18 de mayo de 2026" if filled else "", filled, 360)
    y += 88
    d.text((MX, y), "ORDEN DEL DÍA (OPCIONAL · DE LA CONVOCATORIA)", font=SANSB(10), fill=MUTED)
    y += 20
    od = ["Ratificación de la urgencia de la sesión",
          "Aprobación del PAI y solicitud de fondos FEDER"] if filled else []
    d.rectangle([MX, y, MX + 900, y + 70], outline=LINE, width=1)
    for i, ln in enumerate(od):
        d.text((MX + 10, y + 10 + i * 24), ln, font=SANS(15), fill=INK)
    if not filled:
        d.text((MX + 10, y + 10), "un punto por línea — o sube la convocatoria en PDF", font=SANS(14), fill=HINT)
    y += 92
    d.rounded_rectangle([MX, y, MX + 150, y + 44], radius=3, fill=INK)
    d.text((MX + 26, y + 12), "Generar acta", font=SANSB(17), fill=WHITE)
    if cur:
        cursor(d, MX + 112, y + 24)
    return img


def progress_frame(step, pct=None, eta=None, elapsed="", rem="", msg=None, done=False, link=False):
    img, d = chrome()
    y = 210
    d.text((MX, y), "Generando el acta…" if not done else "Acta generada", font=SERIF(25), fill=INK)
    y += 42
    d.text((MX, y), f"youtube.com/watch?v={VID}    ·    Ayuntamiento de Chiva", font=SANS(15), fill=MUTED)
    y += 44
    steps = ["Descargando el vídeo", "Transcribiendo (voz a texto)", "Separando las voces",
             "Asignando nombres", "Generando el acta"]
    for i, s in enumerate(steps):
        yy = y + i * 46
        ok = (step > i + 1) or done
        act = (step == i + 1) and not done
        col = GREEN if ok else (INK if act else MUTED)
        mark = "●" if ok else ("◐" if act else "○")
        label = s
        if act and i == 0 and pct is not None:
            label = f"{s} — {pct}%"
        if act and i == 1 and eta is not None:
            label = f"{s} — aprox. {eta} min"
        d.text((MX, yy), mark, font=SANS(18), fill=col)
        d.text((MX + 30, yy + 1), label, font=(SANSB(17) if (ok or act) else SANS(17)), fill=col)
    ty = y + len(steps) * 46 + 16
    if elapsed:
        tl = f"Transcurrido {elapsed}" + (f"  ·  faltan aprox. {rem}" if rem else "")
        d.text((MX, ty), tl, font=SANS(15), fill=MUTED)
    my = ty + 30
    if msg:
        tx = MX
        if done:
            check(d, MX, my + 1, 16, GREEN, 3); tx = MX + 28
        d.text((tx, my), msg, font=SANSB(17), fill=ACCENT)
        if link:
            off = tx + d.textlength(msg + "     ", font=SANSB(17))
            d.text((off, my), "Revisar y etiquetar las voces →", font=SANSB(17), fill=ACCENT)
            d.line([(off, my + 22), (off + d.textlength("Revisar y etiquetar las voces →", font=SANSB(17)), my + 22)], fill=ACCENT, width=1)
    return img


def _paste_doc(img, d, png, top, height, caption_lines):
    a = Image.open(png).convert("RGB")
    tw = int(a.width * height / a.height)
    ax = MX
    d.rectangle([ax + 5, top + 6, ax + tw + 5, top + height + 6], fill=(225, 220, 210))
    img.paste(a.resize((tw, height)), (ax, top))
    d.rectangle([ax, top, ax + tw, top + height], outline=LINE, width=2)
    cx = ax + tw + 50
    cy = top + 30
    for f, fill, t in caption_lines:
        cy = para(d, cx, cy, t, f, fill, W - cx - 60) + 14
    return tw


def acta_overview_frame():
    img, d = chrome()
    d.text((MX, 196), "El acta, con estilo de Diario de Sesiones", font=SERIF(24), fill=INK)
    _paste_doc(img, d, FR + "/_acta_p1.png", 240, 440, [
        (SERIF_R(21), INK, "Membrete oficial, ASISTENTES, orden del día y estadísticas."),
        (SANS(16), MUTED, "•  Quién interviene y cuánto habla cada uno."),
        (SANS(16), MUTED, "•  Orden del día con el minuto de inicio."),
        (SANS(16), MUTED, "•  Tiempo por orador y por partido."),
        (SANS(16), MUTED, "•  Generado solo a partir del vídeo, sin diario previo."),
    ])
    return img


def acta_body_frame():
    img, d = chrome()
    d.text((MX, 196), "El cuerpo: lo que se dijo, enlazado al vídeo", font=SERIF(24), fill=INK)
    _paste_doc(img, d, FR + "/_acta_body.png", 240, 440, [
        (SERIF_R(21), INK, "Transcripción literal por puntos del orden del día."),
        (SANS(16), MUTED, "•  Cada intervención con su minuto."),
        (SANS(16), BLUE, "•  El minuto es un enlace: clic y salta al vídeo."),
        (SANS(16), MUTED, "•  La votación al cierre de cada punto."),
        (SANS(16), MUTED, "•  Voces sin confirmar marcadas; el secretario valida."),
    ])
    return img


def visor_frame(vsegs, hi):
    img, d = chrome()
    d.text((MX, 196), "Visor: acta sincronizada con el vídeo", font=SERIF(24), fill=INK)
    # fotograma real del vídeo
    fr = Image.open(FR + "/_vframe.jpg").convert("RGB")
    vw = 560
    vh = int(fr.height * vw / fr.width)
    img.paste(fr.resize((vw, vh)), (MX, 244))
    d.rectangle([MX, 244, MX + vw, 244 + vh], outline=INK, width=2)
    d.text((MX, 244 + vh + 12), "▶  Reproduciendo el pleno", font=SANS(14), fill=MUTED)
    # transcripción a la derecha, una frase resaltada
    tx = MX + vw + 50
    ty = 250
    d.text((tx, ty), "TRANSCRIPCIÓN", font=SANSB(11), fill=MUTED); ty += 26
    for i, (tm, voz, txt) in enumerate(vsegs):
        block_h = 18 + 17 * len(wrap(d, txt, SANS(15), W - tx - 60))
        if i == hi:
            d.rectangle([tx - 8, ty - 4, W - 70, ty + block_h], fill=(246, 237, 218))
        d.text((tx, ty), f"{tm}   Voz {voz}", font=SANSB(12), fill=ACCENT)
        para(d, tx, ty + 16, txt, SANS(15), INK, W - tx - 60)
        ty += block_h + 8
    para(d, MX, 244 + vh + 40, "Clic en cualquier frase y el vídeo salta a ese momento. "
         "Ideal para verificar el acta contra la grabación.", SERIF_R(18), INK, W - 2 * MX)
    return img


def numbers_frame():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.text((MX, 70), "L O   Q U E   Y A   F U N C I O N A", font=SANSB(13), fill=ACCENT)
    d.text((MX, 100), "Resultados", font=SERIF(40), fill=INK)
    rows = [
        ("100%", "Separación de voz: cada interviniente = una voz (biunívoco).",
         "Etiquetando una vez, atribución perfecta y reutilizable."),
        ("~96%", "Precisión de transcripción sobre audio real de pleno.",
         "Validado contra transcripción humana palabra a palabra."),
        ("90,8%", "Parecido con el Diario oficial del Congreso (a ciegas).",
         "Cobertura 100% · votaciones 4/4 · en un pleno de 3,5 h."),
        ("ca/es", "Multilingüe: valenciano y castellano por fragmento.",
         "Probado en un pleno de Llíria, sin configurar nada."),
    ]
    y = 190
    for big, t1, t2 in rows:
        d.text((MX, y - 6), big, font=SERIF(34), fill=ACCENT)
        d.text((MX + 170, y), t1, font=SANSB(19), fill=INK)
        d.text((MX + 170, y + 28), t2, font=SANS(15), fill=MUTED)
        d.line([(MX, y + 60), (W - MX, y + 60)], fill=LINE, width=1)
        y += 84
    d.text((MX, H - 60), "Piloto con un ayuntamiento real.",
           font=SANSB(16), fill=ACCENT)
    return img


def title_frame(top, mid, sub):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.text((MX, 250), top, font=SANSB(15), fill=ACCENT)
    d.text((MX, 286), mid, font=SERIF(50), fill=INK)
    d.text((MX, 360), sub, font=SERIF(50), fill=ACCENT)
    d.text((MX, H - 44), "Buscador Plenario Inteligente   ·   IDAL · Reto 2", font=SANS(13), fill=MUTED)
    return img


def prep_assets():
    os.makedirs(FR, exist_ok=True)
    doc = fitz.open("data/actas/TN_gTdxQXA4.acta.pdf")
    doc[0].get_pixmap(dpi=200).save(FR + "/_acta_p1.png")
    doc[min(1, doc.page_count - 1)].get_pixmap(dpi=200).save(FR + "/_acta_body.png")
    subprocess.run(["ffmpeg", "-y", "-ss", "95", "-i", f"data/raw_video/{VID}.mp4",
                    "-frames:v", "1", "-q:v", "3", FR + "/_vframe.jpg"], check=True, capture_output=True)
    # frases para el visor (de la transcripción real)
    d = json.loads(open(f"data/transcripts/{VID}.json", encoding="utf-8").read())
    segs = sorted(d["segments"], key=lambda s: s.get("start", 0))
    order = {}
    out = []
    for s in segs:
        sp = s.get("speaker")
        if sp not in order:
            order[sp] = len(order) + 1
        if 90 <= s.get("start", 0) <= 140 and (s.get("text") or "").strip():
            t = int(s["start"]); tm = f"{t // 60}:{t % 60:02d}"
            out.append((tm, order[sp], s["text"].strip()[:90]))
    return out[:4]


def main():
    vsegs = prep_assets()
    frames = [
        (title_frame("D E   U N   V Í D E O   A   U N   A C T A", "Del pleno en YouTube", "al acta formal."), 3.0),
        (form_frame(False, False), 1.6),
        (form_frame(True, True), 3.0),
        (progress_frame(1, pct=35, elapsed="0:18", msg="Descargando el vídeo…"), 2.2),
        (progress_frame(2, eta=4, elapsed="1:30", rem="4 min", msg="Transcribiendo (voz a texto)…"), 2.6),
        (progress_frame(3, elapsed="4:10", rem="2 min", msg="Separando las voces…"), 2.2),
        (progress_frame(5, elapsed="6:05", rem="20 s", msg="Generando el acta…"), 1.8),
        (progress_frame(5, done=True, elapsed="6:40", msg="Acta generada.", link=True), 2.8),
        (acta_overview_frame(), 5.5),
        (acta_body_frame(), 5.0),
        (visor_frame(vsegs, 1), 5.0),
        (numbers_frame(), 6.0),
        (title_frame("I D A L   ·   R E T O   2", "Funciona en cualquier", "ayuntamiento."), 3.0),
    ]
    total = 0.0
    with open(os.path.join(FR, "list.txt"), "w", encoding="utf-8") as fh:
        for i, (img, dur) in enumerate(frames):
            img.save(os.path.join(FR, f"f{i:02d}.png"))
            fh.write(f"file 'f{i:02d}.png'\nduration {dur}\n")
            total += dur
        fh.write(f"file 'f{len(frames)-1:02d}.png'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-vf", f"fps=25,format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={total-0.6:.2f}:d=0.6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.abspath(OUT)],
                   cwd=FR, check=True, capture_output=True)
    print(f"OK  {OUT}  ·  {total:.1f}s  ·  {len(frames)} escenas")


if __name__ == "__main__":
    main()
