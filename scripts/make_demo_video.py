"""Genera un vídeo de demo (MP4) para enseñar en los ayuntamientos / el concurso.

Caso: Congreso (tenemos acta + precisión medida contra el Diario oficial verbatim).
Hace fotogramas con Pillow (acta real + números reales) y los une con ffmpeg.

Uso:  python scripts/make_demo_video.py   ->  data/processed/demo_congreso.mp4
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BG = (250, 249, 246)
INK = (24, 24, 24)
ACCENT = (122, 31, 43)
MUTED = (108, 108, 108)
LINE = (206, 200, 188)
SOFT = (244, 240, 233)
GREEN = (47, 111, 58)

FD = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
OUT = "data/processed/demo_congreso.mp4"
FRDIR = "data/processed/_demoframes"
ACTA = "data/processed/demo_acta_cover.png"


def F(name, size):
    return ImageFont.truetype(os.path.join(FD, name), size)


SERIF = lambda s: F("georgiab.ttf", s)
SERIF_R = lambda s: F("georgia.ttf", s)
SANS = lambda s: F("arial.ttf", s)
SANSB = lambda s: F("arialbd.ttf", s)


def wrap(draw, text, font, max_w):
    out, line = [], ""
    for word in text.split():
        t = (line + " " + word).strip()
        if draw.textlength(t, font=font) <= max_w:
            line = t
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out


def text(draw, x, y, s, font, fill, max_w=None, lh=1.32, center=False):
    lines = wrap(draw, s, font, max_w) if max_w else [s]
    h = font.size * lh
    for ln in lines:
        xx = x
        if center and max_w:
            xx = x + (max_w - draw.textlength(ln, font=font)) / 2
        draw.text((xx, y), ln, font=font, fill=fill)
        y += h
    return y


def base():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((80, H - 46), "Buscador Plenario Inteligente   ·   IDAL · Reto 2", font=SANS(15), fill=MUTED)
    return img, d


def kicker(d, x, y, s):
    d.text((x, y), s.upper(), font=SANSB(15), fill=ACCENT)
    return y + 30


def rule(d, x, y, w, color=ACCENT, h=3):
    d.rectangle([x, y, x + w, y + h], fill=color)


# ---------------- fotogramas ----------------
def f_hook():
    img, d = base()
    y = kicker(d, 80, 150, "De un vídeo de pleno al acta")
    rule(d, 80, y + 2, 70)
    y += 28
    text(d, 80, y, "El acta del pleno,", SERIF(64), INK)
    text(d, 80, y + 78, "generada sola.", SERIF(64), ACCENT)
    text(d, 80, y + 185, "De la grabación a un acta con estilo de Diario de Sesiones,\nsin necesidad de un acta previa.", SANS(26), MUTED, max_w=1000)
    return img


def f_problem():
    img, d = base()
    y = kicker(d, 80, 150, "El problema")
    rule(d, 80, y + 2, 70)
    y += 36
    text(d, 80, y, "La mayoría de ayuntamientos no tienen Diario de Sesiones.", SERIF(40), INK, max_w=1080)
    text(d, 80, y + 130, "Transcribir un pleno a mano cuesta tiempo y dinero, y la ciudadanía\nno puede buscar “qué se dijo” sobre un tema.", SANS(27), MUTED, max_w=1080)
    return img


def f_input():
    img, d = base()
    y = kicker(d, 80, 130, "Paso 1")
    rule(d, 80, y + 2, 70)
    y += 30
    text(d, 80, y, "Pega el enlace del vídeo del pleno", SERIF(44), INK)
    by = y + 120
    d.rounded_rectangle([80, by, 1000, by + 92], radius=8, fill="white", outline=LINE, width=2)
    d.text((110, by + 22), "https://www.youtube.com/watch?v=…", font=SANS(24), fill=MUTED)
    d.text((110, by + 50), "Congreso de los Diputados · sesión del 27/01/2026", font=SANSB(18), fill=ACCENT)
    d.rounded_rectangle([1010, by, 1180, by + 92], radius=8, fill=INK)
    d.text((1042, by + 32), "Generar", font=SANSB(24), fill="white")
    return img


def f_pipeline(done):
    img, d = base()
    y = kicker(d, 80, 110, "Paso 2 — la herramienta hace el resto")
    rule(d, 80, y + 2, 70)
    y += 40
    steps = ["Descarga el vídeo", "Transcribe (voz a texto)", "Separa las voces",
             "Pone nombre a cada voz", "Genera el acta"]
    upto = 5 if done else 3
    for i, s in enumerate(steps):
        yy = y + i * 66
        ok = i < upto
        col = GREEN if ok else (INK if i == upto else MUTED)
        mark = "●" if ok else ("◐" if i == upto else "○")
        d.text((90, yy), mark, font=SANS(30), fill=col)
        d.text((140, yy + 2), s, font=SANSB(27) if (ok or i == upto) else SANS(27), fill=col)
        if ok:
            d.text((1000, yy + 4), "hecho", font=SANS(20), fill=GREEN)
    return img


def f_acta():
    img, d = base()
    y = kicker(d, 80, 90, "El resultado")
    rule(d, 80, y + 2, 70)
    y += 30
    text(d, 80, y, "Acta con el estilo del\nDiario de Sesiones.", SERIF(40), INK, max_w=470)
    for i, b in enumerate(["Membrete oficial", "Sumario / orden del día", "Orador en versalitas",
                           "Listo en PDF y texto"]):
        d.text((84, y + 150 + i * 44), "•  " + b, font=SANS(24), fill=MUTED)
    if os.path.exists(ACTA):
        a = Image.open(ACTA).convert("RGB")
        th = 600
        tw = int(a.width * th / a.height)
        a = a.resize((tw, th))
        ax, ay = 700, 60
        d.rectangle([ax + 6, ay + 8, ax + tw + 6, ay + th + 8], fill=(225, 220, 210))   # sombra
        img.paste(a, (ax, ay))
        d.rectangle([ax, ay, ax + tw, ay + th], outline=LINE, width=2)
    return img


def f_fiable():
    img, d = base()
    y = kicker(d, 80, 170, "¿Y es fiable?")
    rule(d, 80, y + 2, 70)
    y += 30
    text(d, 80, y, "Lo hemos medido contra el Diario\noficial verbatim del Congreso.", SERIF(52), INK, max_w=1080)
    text(d, 80, y + 200, "No es una demo: es una comparación real, frase a frase, con el acta oficial.", SANS(26), MUTED, max_w=1080)
    return img


def f_numbers():
    img, d = base()
    y = kicker(d, 80, 70, "Precisión medida — Congreso, 27/01/2026")
    rule(d, 80, y + 2, 70)
    y += 28
    # stats
    for i, (num, lab) in enumerate([("100%", "cobertura de\nintervenciones"), ("0,91", "fidelidad de\ncontenido")]):
        x = 90 + i * 360
        d.text((x, y), num, font=SERIF(96), fill=ACCENT)
        d.text((x + 4, y + 118), lab.replace("\n", "  "), font=SANS(22), fill=MUTED)
    # side-by-side
    sy = y + 220
    d.text((90, sy), "Nuestro (a ciegas)", font=SANSB(20), fill=ACCENT)
    text(d, 90, sy + 30, "“Gracias, señora presidenta. Es verdad, lo primero, el recuerdo a las víctimas…”", SANS(21), INK, max_w=520)
    d.text((650, sy), "Diario oficial", font=SANSB(20), fill=INK)
    text(d, 650, sy + 30, "“Gracias, señora presidenta. Es verdad, lo primero, el recuerdo a las víctimas…”", SANS(21), INK, max_w=520)
    rule(d, 90, sy + 150, 1080, color=LINE, h=1)
    d.text((90, sy + 162), "Casi calcado — incluso en catalán, euskera y gallego.", font=F("ariali.ttf", 22), fill=MUTED)
    return img


def f_diff():
    img, d = base()
    y = kicker(d, 80, 110, "Y va más allá de un acta")
    rule(d, 80, y + 2, 70)
    y += 36
    items = [
        ("Memoria de voz", "Etiquetas las voces una vez y se reconocen solas en cada nuevo pleno. Cuanto más se usa, mejor va."),
        ("Búsqueda ciudadana", "“¿Qué dijo cada concejal sobre X?” — con el minuto del vídeo como prueba."),
        ("Rendición de cuentas", "Detección de contradicciones y seguimiento de promesas a lo largo del tiempo."),
    ]
    for i, (t, s) in enumerate(items):
        yy = y + i * 130
        d.text((84, yy), "→", font=SANSB(30), fill=ACCENT)
        d.text((140, yy), t, font=SANSB(28), fill=INK)
        text(d, 140, yy + 42, s, font=SANS(23), fill=MUTED, max_w=980)
    return img


def f_close():
    img, d = base()
    y = 210
    text(d, 80, y, "Buscador Plenario Inteligente", SERIF(56), INK)
    text(d, 80, y + 100, "Para vuestro ayuntamiento.", SERIF_R(34), ACCENT)
    text(d, 80, y + 175, "Local · privado · sin gastar en transcripción.", SANS(26), MUTED)
    return img


FRAMES = [
    (f_hook(), 4.2),
    (f_problem(), 3.8),
    (f_input(), 3.6),
    (f_pipeline(False), 1.7),
    (f_pipeline(True), 2.0),
    (f_acta(), 4.8),
    (f_fiable(), 3.2),
    (f_numbers(), 5.5),
    (f_diff(), 5.0),
    (f_close(), 3.6),
]


def main():
    os.makedirs(FRDIR, exist_ok=True)
    listf = os.path.join(FRDIR, "list.txt")
    total = 0.0
    with open(listf, "w", encoding="utf-8") as fh:
        for i, (img, dur) in enumerate(FRAMES):
            p = os.path.join(FRDIR, f"f{i:02d}.png")
            img.save(p)
            fh.write(f"file '{os.path.basename(p)}'\nduration {dur}\n")
            total += dur
        fh.write(f"file 'f{len(FRAMES)-1:02d}.png'\n")        # repetir el último (quirk concat)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
           "-vf", f"fps=25,format=yuv420p,fade=t=in:st=0:d=0.5,fade=t=out:st={total-0.6:.2f}:d=0.6",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.abspath(OUT)]
    subprocess.run(cmd, cwd=FRDIR, check=True, capture_output=True)
    print(f"OK  {OUT}  ·  {total:.1f}s")


if __name__ == "__main__":
    main()
