"""Construye el registro OFICIAL diputado->grupo desde los Datos Abiertos del Congreso.

Es el 'roster' (lista de miembros), un input legítimo: rellena el partido de los oradores
que NUNCA aparecieron emparejados con su grupo en ningún sumario (los 'sin partido').

Fuente: www.congreso.es/es/opendata/diputados
  - odsDiputados12/13/14  -> legislaturas XII, XIII, XIV (histórico)
  - DiputadosActivos      -> legislatura XV (actual)
Cada fichero trae NOMBRE ('Apellidos, Nombre') y GRUPOPARLAMENTARIO. Mapeamos el grupo a
nuestras siglas con _sigla (mismo criterio que el sumario -> consistente). Clave = apellidos.

Salida: data/registro_diputados.json  ->  {"12": {"APELLIDOS": "PSOE", ...}, ...}
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import resolve_path  # noqa: E402
from src.diario import _KNOWN_SIGLAS, _norm_name, _sigla  # noqa: E402

BASE = "https://www.congreso.es"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=120).read()


def find_url(html: str, pattern: str):
    m = re.search(pattern, html)
    return BASE + m.group(0) if m else None


def rows_of(j):
    return j if isinstance(j, list) else next((v for v in j.values() if isinstance(v, list)), None)


def main() -> None:
    html = fetch(BASE + "/es/opendata/diputados").decode("utf-8", "ignore")
    files = {
        "11": find_url(html, r"/webpublica/opendata/diputados/odsDiputados11__\w+\.json"),
        "12": find_url(html, r"/webpublica/opendata/diputados/odsDiputados12__\w+\.json"),
        "13": find_url(html, r"/webpublica/opendata/diputados/odsDiputados13__\w+\.json"),
        "14": find_url(html, r"/webpublica/opendata/diputados/odsDiputados14__\w+\.json"),
        "15": find_url(html, r"/webpublica/opendata/diputados/DiputadosActivos__\w+\.json"),
    }
    registry: dict[str, dict] = {}
    for leg, url in files.items():
        if not url:
            print(f"  !! sin URL para legislatura {leg}", flush=True)
            continue
        rows = rows_of(json.loads(fetch(url)))
        d: dict[str, str] = {}
        for r in rows:
            apell = (r.get("NOMBRE", "") or "").split(",")[0].strip()   # "Apellidos, Nombre"
            sig = _sigla(r.get("GRUPOPARLAMENTARIO", "") or "")
            if sig not in _KNOWN_SIGLAS:                                 # fallback: formación electoral
                sig = _sigla(r.get("FORMACIONELECTORAL", "") or "")
            if apell and sig in _KNOWN_SIGLAS:
                d[_norm_name(apell)] = [sig, apell]    # sigla + nombre canónico (para fusionar OCR)
        registry[leg] = d
        print(f"  leg {leg}: {len(rows)} diputados -> {len(d)} mapeados  ({url.split('/')[-1]})", flush=True)

    out = resolve_path("data/registro_diputados.json")
    out.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nregistro escrito: {out}  ({sum(len(d) for d in registry.values())} entradas)", flush=True)

    # --- diagnóstico: ¿cuántos 'sin partido' actuales rellenaría? ---
    miss: dict[str, int] = {}
    have = set()
    for f in sorted(resolve_path("data/diarios_json").glob("*.json")):
        leg = f.stem.split("-")[1]
        for it in json.loads(f.read_text(encoding="utf-8"))["interventions"]:
            if it["role"] != "diputado":
                continue
            k = _norm_name(it["speaker"])
            if it["party"]:
                have.add(k)
            else:
                miss[(leg, k)] = miss.get((leg, k), 0) + 1
    truly = {kk: n for kk, n in miss.items() if kk[1] not in have}
    rec = recint = 0
    left: dict[str, int] = {}
    for (leg, k), n in truly.items():
        reg = registry.get(leg, {})
        if k in reg or k.replace(" ", "") in {kk.replace(" ", "") for kk in reg}:
            rec += 1
            recint += n
        else:
            left[k] = left.get(k, 0) + n
    print(f"diagnóstico: 'sin partido' = {len(truly)} oradores / {sum(truly.values())} interv")
    print(f"   el registro rellenaría: {rec} oradores / {recint} interv")
    print(f"   quedarían para CSV manual: {len(left)} oradores / {sum(left.values())} interv  (top:)")
    for k, n in sorted(left.items(), key=lambda x: -x[1])[:15]:
        print(f"      {k[:32]:32s} {n}", flush=True)


if __name__ == "__main__":
    main()
