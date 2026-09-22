"""Descarga TODOS los Diarios de Sesiones de PLENO disponibles (todas las legislaturas).

Recorre L1..L15 y, por cada una, n=1.. hasta un techo, descargando los PDF que existan.
Robusto: tolera que falte PL-1/PL-2 (sesión constitutiva) y huecos en la numeración
(no para hasta 40 fallos 404 seguidos), reintenta los timeouts, y salta los ya descargados.

El formato máquina existe ~L10-L15; las anteriores (I-IX) están escaneadas en otro archivo.

Uso:  python scripts/scrape_all_diarios.py
"""
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import resolve_path  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0"}
URL = "https://www.congreso.es/public_oficiales/L{leg}/CONG/DS/PL/DSCD-{leg}-PL-{n}.PDF"
MISS_STOP = 40     # fallos 404 seguidos para dar por terminada una legislatura
CEIL = 400         # techo de nº de pleno por seguridad


def fetch(url: str, dest: Path) -> int:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dest.write_bytes(data)
    return len(data)


def try_download(url: str, dest: Path) -> str:
    """Devuelve 'ok' | '404' | 'err' (con un reintento para no-404)."""
    try:
        fetch(url, dest)
        return "ok"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "404"
        time.sleep(1.5)
    except Exception:
        time.sleep(2.0)
    try:
        fetch(url, dest)
        return "ok"
    except Exception:
        return "err"


def main() -> None:
    out = resolve_path("data/diarios")
    out.mkdir(parents=True, exist_ok=True)
    total_new = 0
    for leg in range(1, 16):
        got = miss = 0
        n = 0
        while miss < MISS_STOP and n < CEIL:
            n += 1
            dest = out / f"DSCD-{leg}-PL-{n}.PDF"
            if dest.exists() and dest.stat().st_size > 0:
                got += 1; miss = 0; continue
            res = try_download(URL.format(leg=leg, n=n), dest)
            if res == "ok":
                got += 1; miss = 0; total_new += 1
                if total_new % 25 == 0:
                    print(f"  ... {total_new} nuevos (vamos por L{leg}-PL-{n})", flush=True)
            else:
                miss += 1
            time.sleep(0.12)   # cortesía con el servidor
        print(f"L{leg}: {got} plenos disponibles", flush=True)
    print(f"\nTOTAL nuevos descargados: {total_new}", flush=True)


if __name__ == "__main__":
    main()
