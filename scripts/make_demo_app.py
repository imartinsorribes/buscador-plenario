"""Screencast de la APP (modo 'pega enlace de YouTube -> genera el acta').

Reproduce fielmente la pantalla real (pestaña Generar) y la barra de progreso, y termina
con el acta real renderizada. Frames con Pillow -> MP4 con ffmpeg.

Uso:  python scripts/make_demo_app.py   ->  data/processed/demo_app.mp4
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
PAPER = (250, 249, 246)
INK = (26, 26, 26)
ACCENT = (122, 31, 43)
MUTED = (107, 107, 107)
HINT = (170, 165, 158)
LINE = (226, 224, 219)
GREEN = (47, 111, 58)
WHITE = (255, 255, 255)
MX = 150
FD = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
ACTA = "data/processed/demo_chiva_acta.png"
OUT = "data/processed/demo_app.mp4"
FRDIR = "data/processed/_appframes"


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
            out.append(ln)
            ln = w
    if ln:
        out.append(ln)
    return out


def para(d, x, y, t, f, fill, mw, lh=1.35):
    for ln in wrap(d, t, f, mw):
        d.text((x, y), ln, font=f, fill=fill)
        y += f.size * lh
    return y


def chrome(active="generar"):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.text((MX, 44), "D I A R I O   D E   P L E N O S   ·   B Ú S Q U E D A   S E M Á N T I C A", font=SANSB(12), fill=ACCENT)
    d.text((MX, 66), "Buscador de sesiones plenarias", font=SERIF(38), fill=INK)
    d.line([(MX, 142), (W - MX, 142)], fill=LINE, width=1)
    tx = MX
    for label, key in [("Generar acta", "generar"), ("Buscar", "buscar"), ("Ciudadano", "ciudadano")]:
        on = key == active
        f = SANSB(17) if on else SANS(17)
        d.text((tx, 162), label, font=f, fill=ACCENT if on else MUTED)
        w = d.textlength(label, font=f)
        if on:
            d.rectangle([tx, 190, tx + w, 192], fill=ACCENT)
        tx += w + 34
    d.line([(MX, 192), (W - MX, 192)], fill=LINE, width=1)
    d.text((MX, H - 44), "Buscador Plenario Inteligente   ·   IDAL · Reto 2", font=SANS(14), fill=MUTED)
    return img, d


def cursor(d, x, y):
    d.polygon([(x, y), (x, y + 26), (x + 7, y + 19), (x + 12, y + 30), (x + 16, y + 28),
               (x + 11, y + 17), (x + 19, y + 17)], fill=WHITE, outline=INK)


def check(d, x, y, s, color, w=4):
    d.line([(x, y + s * 0.55), (x + s * 0.35, y + s * 0.9)], fill=color, width=w)
    d.line([(x + s * 0.35, y + s * 0.9), (x + s * 0.95, y + s * 0.12)], fill=color, width=w)


def field(d, x, y, label, value, filled, w):
    d.text((x, y), label, font=SANSB(11), fill=MUTED)
    d.text((x, y + 22), value, font=SANS(20), fill=(INK if filled else HINT))
    d.line([(x, y + 56), (x + w, y + 56)], fill=LINE, width=1)


def form_frame(filled, cur):
    img, d = chrome()
    y = 232
    d.text((MX, y), "Genera el acta desde un vídeo de YouTube", font=SERIF(27), fill=INK)
    y += 46
    y = para(d, MX, y, "Pega el enlace del pleno en YouTube. La herramienta lo descarga, lo transcribe, "
             "separa las voces, les pone nombre y genera un acta con el estilo del Diario de Sesiones.",
             SANS(17), MUTED, 820) + 16
    field(d, MX, y, "ENLACE DE YOUTUBE DEL PLENO",
          "https://www.youtube.com/watch?v=e2fGiHP2XcY" if filled else "https://www.youtube.com/watch?v=…", filled, 820)
    y += 92
    field(d, MX, y, "AYUNTAMIENTO", "Ayuntamiento de Chiva", filled, 380)
    field(d, MX + 440, y, "FECHA (OPCIONAL)", "18 de mayo de 2026", filled, 380)
    y += 104
    d.rounded_rectangle([MX, y, MX + 156, y + 46], radius=3, fill=INK)
    d.text((MX + 30, y + 13), "Generar acta", font=SANSB(18), fill=WHITE)
    if cur:
        cursor(d, MX + 118, y + 26)
    return img


def progress_frame(step, pct=None, eta=None, msg=None, done=False, link=False):
    img, d = chrome()
    y = 244
    d.text((MX, y), "Generando el acta…", font=SERIF(27), fill=INK)
    y += 48
    d.text((MX, y), "youtube.com/watch?v=e2fGiHP2XcY    ·    Ayuntamiento de Chiva", font=SANS(17), fill=MUTED)
    y += 50
    steps = ["Descargando el vídeo", "Transcribiendo (voz a texto)", "Separando las voces",
             "Asignando nombres", "Generando el acta"]
    for i, s in enumerate(steps):
        yy = y + i * 52
        ok = (step > i + 1) or done
        act = (step == i + 1) and not done
        col = GREEN if ok else (INK if act else MUTED)
        mark = "●" if ok else ("◐" if act else "○")
        label = s
        if act and i == 0 and pct is not None:
            label = f"{s} — {pct}%"
        if act and i == 1 and eta is not None:
            label = f"{s} — ≈ {eta} min"
        d.text((MX, yy), mark, font=SANS(20), fill=col)
        d.text((MX + 32, yy + 2), label, font=(SANSB(19) if (ok or act) else SANS(19)), fill=col)
    my = y + len(steps) * 52 + 18
    if msg:
        tx = MX
        if done:
            check(d, MX, my + 2, 18, GREEN, 3)
            tx = MX + 30
        d.text((tx, my), msg, font=SANSB(18), fill=ACCENT)
        if link:
            mw = tx - MX + d.textlength(msg + "    ", font=SANSB(18))
            d.text((MX + mw, my), "Revisar y etiquetar las voces →", font=SANSB(18), fill=ACCENT)
            d.line([(MX + mw, my + 24), (MX + mw + d.textlength("Revisar y etiquetar las voces →", font=SANSB(18)), my + 24)], fill=ACCENT, width=1)
    return img


def acta_frame():
    img, d = chrome()
    d.text((MX, 232), "Acta generada", font=SERIF(27), fill=INK)
    d.text((MX, 280), "Ayuntamiento de Chiva — lista en PDF y texto, con estilo de Diario de Sesiones.", font=SANS(17), fill=MUTED)
    if os.path.exists(ACTA):
        a = Image.open(ACTA).convert("RGB")
        th = 380
        tw = int(a.width * th / a.height)
        ax, ay = MX, 330
        d.rectangle([ax + 5, ay + 6, ax + tw + 5, ay + th + 6], fill=(225, 220, 210))
        img.paste(a.resize((tw, th)), (ax, ay))
        d.rectangle([ax, ay, ax + tw, ay + th], outline=LINE, width=2)
        # check + texto al lado
        check(d, ax + tw + 60, 358, 38, GREEN, 5)
        para(d, ax + tw + 116, 366, "De un enlace de YouTube a un acta presentable, en un solo paso.",
             SERIF_R(24), INK, 360)
        d.text((ax + tw + 60, 470), "El secretario revisa, confirma las voces y firma.", font=SANS(18), fill=MUTED)
    return img


def title_frame():
    img, d = chrome()
    img2 = Image.new("RGB", (W, H), PAPER)
    d2 = ImageDraw.Draw(img2)
    d2.text((MX, 250), "P E G A   U N   E N L A C E", font=SANSB(15), fill=ACCENT)
    d2.text((MX, 286), "De YouTube al acta del pleno,", font=SERIF(50), fill=INK)
    d2.text((MX, 350), "en un solo paso.", font=SERIF(50), fill=ACCENT)
    d2.text((MX, 450), "La aplicación, en directo.", font=SANS(24), fill=MUTED)
    d2.text((MX, H - 44), "Buscador Plenario Inteligente   ·   IDAL · Reto 2", font=SANS(14), fill=MUTED)
    return img2


FRAMES = [
    (title_frame(), 3.2),
    (form_frame(False, False), 2.6),
    (form_frame(True, True), 3.2),
    (progress_frame(1, pct=35, msg="Descargando el vídeo…"), 2.4),
    (progress_frame(2, eta=4, msg="Transcribiendo (voz a texto)…"), 2.6),
    (progress_frame(3, msg="Separando las voces…"), 2.2),
    (progress_frame(5, msg="Generando el acta…"), 2.0),
    (progress_frame(5, done=True, msg="Acta generada.", link=True), 3.2),
    (acta_frame(), 5.0),
]


def main():
    os.makedirs(FRDIR, exist_ok=True)
    total = 0.0
    with open(os.path.join(FRDIR, "list.txt"), "w", encoding="utf-8") as fh:
        for i, (img, dur) in enumerate(FRAMES):
            img.save(os.path.join(FRDIR, f"f{i:02d}.png"))
            fh.write(f"file 'f{i:02d}.png'\nduration {dur}\n")
            total += dur
        fh.write(f"file 'f{len(FRAMES)-1:02d}.png'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-vf", f"fps=25,format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={total-0.6:.2f}:d=0.6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.abspath(OUT)],
                   cwd=FRDIR, check=True, capture_output=True)
    print(f"OK  {OUT}  ·  {total:.1f}s")


if __name__ == "__main__":
    main()
