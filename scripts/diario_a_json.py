"""Diario de Sesiones (PDF) -> JSON estructurado + indexado en la búsqueda inteligente.

Pensado para PROBAR plenos nuevos de uno en uno (no es el pipeline de lote de los 667).
Por cada PDF hace dos cosas:
  1) escribe el JSON del corpus en data/diarios_json/<ID>.json   (mismo esquema que el resto)
  2) lo indexa en ChromaDB para que salga en la búsqueda semántica  (salvo --no-index)

El PARTIDO de cada orador se resuelve por fiabilidad: corrección manual (party_overrides.csv) >
sumario del propio Diario > registro oficial (registro_diputados.json) > "" (nunca se adivina).
party = SIEMPRE sigla (PP/PSOE/VOX/...) o ""; la función (presidencia, ministro...) va en role.

Uso:
  # un pleno (ya descargado el PDF) -> JSON + indexar
  python scripts/diario_a_json.py data/diarios/DSCD-15-PL-50.pdf

  # varios PDFs o una carpeta entera
  python scripts/diario_a_json.py ruta/al/DSCD-15-PL-50.pdf otro.pdf
  python scripts/diario_a_json.py data/diarios_nuevos/

  # solo generar el JSON, sin tocar la búsqueda (no carga el modelo de embeddings)
  python scripts/diario_a_json.py mi_pleno.pdf --no-index

  # bajar el Diario directamente desde el vídeo de YouTube del pleno
  python scripts/diario_a_json.py --from-youtube https://www.youtube.com/watch?v=XXXX
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config, resolve_path  # noqa: E402
from src.diario import (assign_topics, attach_parties, build_party_map,  # noqa: E402
                        download_diario, diario_url_from_youtube, extract_text,
                        extract_votes, load_overrides, load_registry,
                        parse_interventions, session_date, session_topic,
                        to_transcript)

_LEG_RE = re.compile(r"DSCD-(\d+)-", re.IGNORECASE)


def _leg_of(pdf: Path, override: int | None) -> int:
    """Legislatura: de --leg, o del nombre DSCD-<leg>-PL-..., o 0 si no se puede inferir."""
    if override is not None:
        return override
    m = _LEG_RE.search(pdf.name)
    return int(m.group(1)) if m else 0


def _collect(inputs: list[str]) -> list[Path]:
    """Acepta PDFs sueltos, carpetas (busca *.pdf/*.PDF dentro) o comodines."""
    pdfs: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            pdfs += sorted(set(p.glob("*.pdf")) | set(p.glob("*.PDF")))
        elif p.exists():
            pdfs.append(p)
        else:                                   # comodín (p.ej. "data/diarios/DSCD-15-*.pdf")
            pdfs += sorted(Path().glob(raw))
    # dedup conservando orden
    seen, out = set(), []
    for p in pdfs:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="*", help="PDF(s) del Diario, una carpeta, o un comodín")
    ap.add_argument("--from-youtube", metavar="URL",
                    help="baja el Diario desde el enlace de la descripción del vídeo de YouTube")
    ap.add_argument("--leg", type=int, default=None,
                    help="legislatura (si no se puede deducir del nombre del archivo)")
    ap.add_argument("--out", default="data/diarios_json", help="carpeta de salida de los JSON")
    ap.add_argument("--no-index", action="store_true",
                    help="solo escribe el JSON; NO lo indexa en la búsqueda (no carga embeddings)")
    args = ap.parse_args()

    pdfs = _collect(args.pdfs)
    if args.from_youtube:
        url = diario_url_from_youtube(args.from_youtube)
        if not url:
            print("No encontré el enlace al Diario en la descripción del vídeo.", file=sys.stderr)
            sys.exit(1)
        print(f"Diario del vídeo -> {url}")
        pdfs.append(download_diario(url, resolve_path("data/diarios")))
    if not pdfs:
        ap.error("indica al menos un PDF, una carpeta, o --from-youtube")

    out_dir = resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- parsear todos + mapa orador->partido (del SUMARIO de estos PDFs, por legislatura) ---
    parsed = []                                 # (pdf, leg, texto, intervenciones)
    for p in pdfs:
        try:
            txt = extract_text(p)
            parsed.append((p, _leg_of(p, args.leg), txt, parse_interventions(txt)))
        except Exception as e:
            print(f"ERR al leer {p.name}: {str(e)[:80]}", file=sys.stderr)
    if not parsed:
        sys.exit("No se pudo leer ningún PDF.")
    pmap = build_party_map([(leg, txt) for _, leg, txt, _ in parsed])
    registry = load_registry(resolve_path("data/registro_diputados.json"))   # opcional
    overrides = load_overrides(resolve_path("data/party_overrides.csv"))      # opcional
    print(f"{len(parsed)} PDF(s) · sumario: {sum(len(d) for d in pmap.values())} pares "
          f"· registro: {sum(len(d) for d in registry.values())} · overrides: {len(overrides)}\n")

    cfg = None if args.no_index else load_config()
    tr_dir = resolve_path(cfg.paths.transcripts) if cfg else None

    # --- por cada pleno: JSON del corpus (+ indexado) ---
    for p, leg, txt, ivs in parsed:
        pm_leg = pmap.get(str(leg), {})
        reg_leg = registry.get(str(leg), {})
        ivs = assign_topics(attach_parties(ivs, txt, pm_leg, reg_leg, overrides, leg), txt)
        if not ivs:
            print(f"  {p.name}: 0 intervenciones (¿PDF escaneado/sin texto?) — saltado")
            continue
        data = {
            "id": p.stem,
            "legislatura": leg,
            "fecha": session_date(txt),
            "tema_sesion": session_topic(txt),
            "votaciones": extract_votes(txt),
            "n_intervenciones": len(ivs),
            "interventions": [
                {"speaker": it["speaker"], "party": it.get("party", ""),
                 "role": it.get("role", ""), "topic": it.get("topic", ""),
                 "text": it["text"]}
                for it in ivs
            ],
        }
        json_path = out_dir / f"{p.stem}.json"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        msg = f"  {p.stem}: {len(ivs)} intervenciones, {len(data['votaciones'])} votaciones -> {json_path}"

        if cfg:                                 # indexar en la búsqueda (Bloque C / ChromaDB)
            from src.index import index_transcript
            tr_dir.mkdir(parents=True, exist_ok=True)
            tr_path = tr_dir / f"{p.stem}.json"
            tr_path.write_text(
                json.dumps(to_transcript(ivs, source=p.stem), ensure_ascii=False, indent=2),
                encoding="utf-8")
            n = index_transcript(tr_path, {"id": p.stem,
                                           "title": f"Diario {p.stem} — {data['fecha']}",
                                           "url": ""}, cfg)
            msg += f" · {n} fragmentos indexados"
        print(msg)

    print(f"\nListo. JSON en {out_dir}" + ("" if cfg else "  (sin indexar; quita --no-index para la búsqueda)"))


if __name__ == "__main__":
    main()
