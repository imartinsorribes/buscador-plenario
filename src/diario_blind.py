"""Genera un Diario de Sesiones A CIEGAS (desde el vídeo: ASR + Bloque B), con la MISMA
estructura que el oficial. Es EL entregable para municipios sin Diario: de un audio sale un
documento con el mismo esquema que `data/diarios_json/` y se puede medir contra el oficial.

Esquema: id, legislatura, fecha, tema_sesion, votaciones, n_intervenciones,
          interventions[speaker, party, role, topic, text].

Uso:  python -m src.diario_blind data/transcripts/<id_named>.json --id DSCD-15-PL-161 \
            --fecha "27 de enero de 2026" --leg 15
(El transcript debe venir ya nombrado por Bloque B: src.speakers.)
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

from .diario import assign_topics, extract_votes

# cue FUERTE: la propia frase nombra el tipo de punto del orden del día
_STRONG = ("orden del dia", "convalidacion", "real decreto", "mocion", "interpelacion",
           "proposicion", "toma en consideracion", "comparecencia del gobierno", "debate de totalidad")
# la SIGUIENTE frase introduce al ponente -> la frase actual es la DESCRIPCIÓN del punto
_INTRO = ("presentacion de la iniciativa", "defensa de la iniciativa", "para presentar", "para defender")


def _n(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().split())


def _orden_del_dia(ivs: list[dict], maxlen: int = 800) -> str:
    """Orden del día A CIEGAS: frases de la Presidencia que describen un punto, sea porque
    nombran el tipo (convalidación/moción/…) o porque la frase SIGUIENTE introduce al ponente
    ('…reducción de la jornada a 35 horas.' + 'Para la presentación de la iniciativa tiene…')."""
    parts, seen = [], set()
    for it in ivs:
        if it.get("role") != "presidencia":
            continue
        sents = re.split(r"(?<=[.;:])\s+", it["text"])
        low = [_n(s) for s in sents]
        for i, s in enumerate(sents):
            if len(s) < 25 or "tiene la palabra" in low[i]:
                continue
            strong = any(c in low[i] for c in _STRONG)
            intro_next = i + 1 < len(sents) and any(c in low[i + 1] for c in _INTRO)
            if strong or intro_next:
                key = low[i][:50]
                if key not in seen:
                    seen.add(key)
                    parts.append(" ".join(s.split()))
        if sum(len(p) for p in parts) > maxlen:
            break
    return " ".join(parts)[:maxlen]


def _role(name: str, party: str) -> str:
    n = (name or "")
    if n == "Presidencia":
        return "presidencia"
    if party == "Gobierno" or n == "(miembro del Gobierno)" or "gobierno" in n.lower():
        return "gobierno"
    return "diputado"


def generate_diario(transcript: dict, roster=None, meta: dict | None = None) -> dict:
    """Construye el Diario ciego a partir de una transcripción ya nombrada (Bloque B)."""
    meta = meta or {}
    segs = sorted(transcript["segments"], key=lambda s: s.get("start", 0.0))
    full = " ".join((s.get("text") or "") for s in segs)

    ivs: list[dict] = []
    for s in segs:
        nm = (s.get("name") or "(sin identificar)")
        pty = s.get("party") or ""
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        if ivs and ivs[-1]["speaker"] == nm and ivs[-1]["party"] == pty:
            ivs[-1]["text"] += " " + txt
        else:
            ivs.append({"speaker": nm, "party": pty, "role": _role(nm, pty),
                        "topic": "", "text": txt})
    ivs = assign_topics(ivs, full)                 # propaga el tema desde los anuncios (a ciegas)

    temas: list[str] = []
    for it in ivs:
        t = it.get("topic")
        if t and t not in temas:
            temas.append(t)
    tema = _orden_del_dia(ivs) or "; ".join(temas)   # orden del día con detalle (frases del chair)

    return {
        "id": meta.get("id", ""),
        "legislatura": meta.get("legislatura", ""),
        "fecha": meta.get("fecha", ""),
        "tema_sesion": tema,
        "votaciones": extract_votes(full),         # a ciegas, de lo que anuncia la Presidencia
        "n_intervenciones": len(ivs),
        "interventions": ivs,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera un Diario de Sesiones a ciegas (ASR+Bloque B).")
    ap.add_argument("transcript", help="JSON de transcripción YA nombrada por Bloque B")
    ap.add_argument("--id", default="", help="id del pleno (p.ej. DSCD-15-PL-161)")
    ap.add_argument("--fecha", default="", help="fecha de la sesión")
    ap.add_argument("--leg", type=int, default=0, help="legislatura")
    ap.add_argument("--out", default="data/diarios_json_blind", help="carpeta de salida")
    args = ap.parse_args()

    tr = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    meta = {"id": args.id or Path(args.transcript).stem, "fecha": args.fecha, "legislatura": args.leg}
    diario = generate_diario(tr, meta=meta)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{meta['id']}.json"
    dest.write_text(json.dumps(diario, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[diario_blind] {diario['n_intervenciones']} intervenciones · "
          f"{len(diario['votaciones'])} votaciones · tema='{diario['tema_sesion'][:60]}' -> {dest}")


if __name__ == "__main__":
    main()
