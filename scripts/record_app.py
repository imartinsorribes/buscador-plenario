"""Screencast REAL de la app (pestaña Generar acta) con clicks de verdad, a ritmo HUMANO.

Playwright (Chromium) abre http://localhost:8000, rellena el formulario campo a campo, hace los
clicks y navega; capturo la pantalla. Luego compongo el vídeo con un cursor que se mueve despacio
(con aceleración natural), pausa antes de pulsar, y pausas de lectura. Sin texto ni slides.

Requisitos: servidor en marcha + `playwright install chromium`.
Uso:  python scripts/record_app.py   ->  data/processed/demo_app_real.mp4
"""
import asyncio
import os
import subprocess

import fitz
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

W, H = 1280, 720
VID = "TN_gTdxQXA4"
SHOTS = "data/processed/_appshots"
FR = "data/processed/_appcompose"
OUT = "data/processed/demo_app_real.mp4"


def _cursor(d, x, y):
    x, y = int(x), int(y)
    d.polygon([(x, y), (x, y + 22), (x + 6, y + 16), (x + 10, y + 26), (x + 14, y + 24),
               (x + 10, y + 14), (x + 16, y + 14)], fill=(20, 20, 20), outline=(255, 255, 255))


def _ease(t):                                   # ease-in-out: arranca y frena suave (humano)
    return 2 * t * t if t < 0.5 else 1 - 2 * (1 - t) * (1 - t)


async def grab():
    os.makedirs(SHOTS, exist_ok=True)
    steps = []   # (png, click_xy|None, dwell_s)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": W, "height": H})
        await page.goto("http://localhost:8000/", wait_until="networkidle")
        await page.wait_for_timeout(900)

        async def shot(name, click=None, dwell=1.8):
            path = os.path.abspath(os.path.join(SHOTS, f"{name}.png"))
            await page.screenshot(path=path)
            steps.append((path, click, dwell))

        async def cxy(sel):
            try:
                b = await page.locator(sel).first.bounding_box()
                return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2) if b else None
            except Exception:
                return None

        await shot("01_empty", await cxy("#gen-url"), dwell=1.4)              # formulario vacío
        # enlace: en dos tramos para que se vea escribir
        await page.click("#gen-url")
        await page.type("#gen-url", "https://www.youtube.com/watch", delay=55)
        await shot("02_url_a", None, dwell=0.5)
        await page.type("#gen-url", "?v=" + VID, delay=55)
        await shot("03_url_b", await cxy("#gen-ent"), dwell=1.0)
        await page.click("#gen-ent"); await page.type("#gen-ent", "Ayuntamiento de Chiva", delay=55)
        await shot("04_ent", await cxy("#gen-fecha"), dwell=1.0)
        await page.click("#gen-fecha"); await page.type("#gen-fecha", "18 de mayo de 2026", delay=55)
        await shot("05_fecha", await cxy("#gen-orden"), dwell=1.0)
        await page.click("#gen-orden")
        await page.type("#gen-orden", "Ratificación de la urgencia de la sesión\n"
                        "Aprobación del PAI y solicitud de fondos FEDER", delay=22)
        await shot("06_orden", await cxy("#gen-btn"), dwell=1.6)
        await page.click("#gen-btn"); await page.wait_for_timeout(1900)       # ya generado
        await shot("07_dupcheck", await cxy("#gen-btn"), dwell=3.2)
        try:
            await page.locator("#gen-editor").scroll_into_view_if_needed()
            await page.wait_for_timeout(700)
            await page.select_option("#pleno", VID)
            await page.wait_for_timeout(4000)                                  # carga voces + huellas
            await shot("08_editor", await cxy("#pleno"), dwell=3.6)
            first = page.locator("#results [data-cluster]").first
            await first.scroll_into_view_if_needed()
            await page.wait_for_timeout(700)
            await shot("09_voices", await cxy("#results [data-cluster] .sv"), dwell=4.0)
        except Exception as e:
            print("editor:", e)
        try:
            vlink = await cxy("#acta a[href*='/sync']")
            async with page.expect_popup() as pop:
                await page.click("#acta a[href*='/sync']")
            await shot("10_clickvisor", vlink, dwell=1.0)
            vp = await pop.value
            await vp.wait_for_load_state("domcontentloaded")
            await vp.wait_for_timeout(4000)
            vpath = os.path.abspath(os.path.join(SHOTS, "11_visor.png"))
            await vp.screenshot(path=vpath)
            steps.append((vpath, None, 4.5))
        except Exception as e:
            print("visor:", e)
        await browser.close()
    return steps


def compose(steps):
    os.makedirs(FR, exist_ok=True)
    fitz.open(f"data/actas/{VID}.acta.pdf")[0].get_pixmap(dpi=120).save(os.path.join(FR, "_acta.png"))
    idx = 0
    prev = (W * 0.5, H * 0.62)
    listing = open(os.path.join(FR, "list.txt"), "w", encoding="utf-8")

    def emit(img, dur):
        nonlocal idx
        img.save(os.path.join(FR, f"f{idx:04d}.png"))
        listing.write(f"file 'f{idx:04d}.png'\nduration {dur:.3f}\n")
        idx += 1

    for path, click, dwell in steps:
        base = Image.open(path).convert("RGB").resize((W, H))
        if click is not None:
            N = 26                                       # movimiento lento (~1 s) con easing
            for k in range(1, N + 1):
                f = _ease(k / N)
                fx = prev[0] + (click[0] - prev[0]) * f
                fy = prev[1] + (click[1] - prev[1]) * f
                fr = base.copy(); _cursor(ImageDraw.Draw(fr), fx, fy); emit(fr, 0.04)
            for _ in range(9):                           # pausa antes de pulsar (~0.35 s)
                fr = base.copy(); _cursor(ImageDraw.Draw(fr), *click); emit(fr, 0.04)
            for r in (18, 12, 6):                        # anillo de clic
                fr = base.copy(); d = ImageDraw.Draw(fr)
                d.ellipse([click[0] - r, click[1] - r, click[0] + r, click[1] + r], outline=(122, 31, 43), width=3)
                _cursor(d, *click); emit(fr, 0.08)
            prev = click
        fr = base.copy()
        if click is not None:
            _cursor(ImageDraw.Draw(fr), *click)
        emit(fr, dwell)
    acta = Image.open(os.path.join(FR, "_acta.png")).convert("RGB")
    canvas = Image.new("RGB", (W, H), (250, 249, 246))
    th = H - 30; tw = int(acta.width * th / acta.height)
    canvas.paste(acta.resize((tw, th)), ((W - tw) // 2, 15))
    emit(canvas, 4.0)

    listing.write(f"file 'f{idx-1:04d}.png'\n"); listing.close()
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-vf", "fps=25,format=yuv420p,fade=t=in:st=0:d=0.4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.abspath(OUT)],
                   cwd=FR, check=True, capture_output=True)
    print(f"OK -> {OUT}")


def main():
    steps = asyncio.run(grab())
    print(f"{len(steps)} capturas")
    compose(steps)


if __name__ == "__main__":
    main()
