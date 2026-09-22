"""Convierte los Diarios de Sesiones (PDF) a JSON estructurado, uno por pleno.

Dos fases para que el PARTIDO sea consistente:
  A) parsea todos los PDFs y construye un mapa GLOBAL orador->partido (de los grupos
     fiables del paréntesis, por mayoría).
  B) aplica ese mapa + tema de sesión + votaciones, y escribe cada JSON.

Por defecto, legislaturas de 2016 en adelante (XII–XV). Salida: data/diarios_json/.
Uso:  python scripts/diarios_to_json.py [legs...]      # p.ej.  11 12 13 14 15
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import resolve_path  # noqa: E402
from src.diario import (assign_topics, attach_parties, build_party_map,  # noqa: E402
                        extract_text, extract_votes, load_overrides,
                        load_registry, parse_interventions, session_date,
                        session_topic)


def main() -> None:
    legs = [int(x) for x in sys.argv[1:]] or [12, 13, 14, 15]
    base = resolve_path("data/diarios")
    out = resolve_path("data/diarios_json")
    out.mkdir(parents=True, exist_ok=True)
    pdfs = []
    for leg in legs:
        pdfs += sorted(set(list(base.glob(f"DSCD-{leg}-PL-*.PDF")) + list(base.glob(f"DSCD-{leg}-PL-*.pdf"))))

    # --- Fase A: parsear todo (cache) + mapa global de partidos ---
    parsed = []
    for p in pdfs:
        try:
            txt = extract_text(p)
            parsed.append((p, txt, parse_interventions(txt)))
        except Exception as e:
            print("ERR parse", p.name, str(e)[:50], flush=True)
    pmap = build_party_map([(int(p.stem.split("-")[1]), txt) for p, txt, _ in parsed])
    registry = load_registry(resolve_path("data/registro_diputados.json"))
    overrides = load_overrides(resolve_path("data/party_overrides.csv"))
    print(f"mapa del sumario POR LEGISLATURA: {sum(len(d) for d in pmap.values())} pares | "
          f"registro oficial: {sum(len(d) for d in registry.values())} | "
          f"overrides manuales: {len(overrides)}", flush=True)

    # --- Fase B: aplicar mapa + temas + votaciones + escribir (todo POR LEGISLATURA) ---
    done = vacios = 0
    for p, txt, ivs in parsed:
        leg = int(p.stem.split("-")[1])
        pm_leg = pmap.get(str(leg), {})         # sumario de ESA legislatura
        reg_leg = registry.get(str(leg), {})    # roster de ESA legislatura
        ivs = assign_topics(attach_parties(ivs, txt, pm_leg, reg_leg, overrides, leg), txt)
        if not ivs:
            vacios += 1
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
        (out / f"{p.stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
        if done % 50 == 0:
            print(f"  ... {done} JSON", flush=True)
    print(f"\nJSON generados: {done} · vacíos: {vacios}", flush=True)


if __name__ == "__main__":
    main()
