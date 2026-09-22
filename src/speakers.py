"""Bloque B (2/2) — NOMBRE y PARTIDO por intervención con NLP. SIN regex.

Detecta el relevo de turno y al orador combinando señales semánticas:
  1. EMBEDDINGS (BGE-M3): similitud de cada segmento a frases-prototipo de "dar la
     palabra" -> mide, de forma semántica, si es un relevo de turno.
  2. NER (modelo español): extrae PERSONA (orador) y ORG (grupo / Gobierno).
     Relevo válido = alta similitud  Y  NER encuentra persona o grupo.

Para poner el nombre REAL hay dos vías (de menor a mayor fiabilidad):
  - ROSTER (--roster): entity-linking difuso por tokens contra una lista de
    diputados/Gobierno (corrige erratas de Whisper: "Sagastita"->Sagastizabal).
  - DIARIO (--diario): alineamiento de secuencias (Needleman-Wunsch) entre los
    relevos del vídeo y el ORDEN oficial de oradores del Diario de Sesiones.
    Es ground-truth: corrige nombres, rellena partidos y descarta fantasmas.
    Solo acepta emparejados por encima de un mínimo de similitud (conservador).

Anota seg["name"] y seg["party"] junto a seg["speaker"] (diarización), sin pisarla.

Uso:  python -m src.speakers data/transcripts/<id>.json [--roster r.json] [--diario DSCD.PDF] [--dry-run]
"""
from __future__ import annotations

import argparse
import difflib
import json
import unicodedata
from pathlib import Path

import numpy as np

from .config import load_config

_PROTOS = [
    "tiene la palabra el señor",
    "tiene ahora la palabra la señora",
    "por el grupo parlamentario tiene la palabra su señoría",
    "para presentar el real decreto tiene la palabra en nombre del gobierno",
]
_SIM_THR = 0.55           # umbral de detección de relevo (embeddings)
_NER_MODEL = "mrm8488/bert-spanish-cased-finetuned-ner"
_CONNECTORS = {"de", "del", "la", "las", "los", "el", "i", "y", "e", "da", "do", "san"}
_ner = None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _toks(s: str) -> list[str]:
    t = [w for w in _norm(s).split() if w not in _CONNECTORS]
    return t or _norm(s).split()


def _name_sim(a: str, b: str) -> float:
    """Similitud por tokens (apellido a apellido), robusta a troceo/erratas."""
    at, bt = _toks(a), _toks(b)
    if not at or not bt:
        return 0.0
    return sum(max(difflib.SequenceMatcher(None, x, y).ratio() for y in bt) for x in at) / len(at)


def _get_ner():
    global _ner
    if _ner is None:
        import torch
        from transformers import pipeline
        _ner = pipeline("token-classification", model=_NER_MODEL,
                        aggregation_strategy="simple", device=0 if torch.cuda.is_available() else -1)
    return _ner


def _entities(text: str):
    pers, orgs = [], []
    for e in _get_ner()(text):
        w = e["word"].replace("##", "").strip(" ,.;:-")
        if len(w) < 2:
            continue
        (pers if e["entity_group"] == "PER" else orgs if e["entity_group"] == "ORG" else []).append(w)
    return pers, orgs


def _pick_person(pers):
    cl = sorted({p for p in pers if len(p) > 1}, key=len, reverse=True)
    return cl[0] if cl else None


def _pick_party(orgs):
    cl = [o for o in orgs if o]
    if not cl:
        return ""
    for o in cl:
        if "gobierno" in _norm(o):
            return "Gobierno"
    grp = [o for o in cl if "grupo" in _norm(o) or "parlament" in _norm(o)
           or any(p in _norm(o) for p in _PARTY_HINTS)]
    return grp[0] if grp else ""   # nada de ORGs basura ("Estado", "Cámara") como partido


def _has_gov(orgs):
    return any("gobierno" in _norm(o) for o in orgs)


_PARTY_HINTS = ("psoe", "socialista", "popular", "vox", "sumar", "junts", "bildu",
                "republican", "pnv", "eaj", "podemos", "compromis", "canaria", "bng", "mixto")


def _real_group(orgs) -> bool:
    """¿Alguna ORG es un grupo parlamentario / Gobierno / partido? (descarta 'Estado', 'Cámara'...)"""
    for o in orgs:
        no = _norm(o)
        if "grupo" in no or "parlament" in no or "gobierno" in no or any(p in no for p in _PARTY_HINTS):
            return True
    return False


_HONOR_TOKENS = {"senor", "senora", "ministro", "ministra", "vicepresidente",
                 "vicepresidenta", "secretario", "secretaria", "don", "dona"}


def _span_sim(seq: list[str], name_toks: list[str]) -> float:
    """Mejor parecido de name_toks contra cualquier ventana consecutiva de seq."""
    L = len(name_toks)
    if not seq or L == 0:
        return 0.0
    best = 0.0
    for st in range(max(1, len(seq) - L + 1)):
        span = seq[st:st + L] or seq[st:]
        sc = sum(max(difflib.SequenceMatcher(None, a, b).ratio() for b in span) for a in name_toks) / L
        best = max(best, sc)
    return best


def _announced_name(window: str, roster, thr: float = 0.6):
    """Empareja el apellido ANUNCIADO (justo tras 'la palabra') con el roster -> (nombre, partido).

    Robusto a que el NER no extraiga nombres largos/raros: buscamos directamente en el roster
    quién es la persona nombrada en el anuncio (gazetteer). Evita coger nombres MENCIONADOS en
    el discurso porque solo miramos los tokens inmediatamente posteriores a 'la palabra'.
    """
    import difflib  # noqa: F401 (ya importado arriba; defensivo)
    low = _norm(window)
    idx = low.rfind("palabra")
    if idx < 0:                       # sin la marca de relevo ("la palabra") NO es un anuncio fiable
        return None                   # (evita falsos: "gracias"≈"garcía" en el saludo del orador)
    region = low[idx + 7:]
    toks = [t for t in region.split() if t not in _CONNECTORS and t not in _HONOR_TOKENS][:5]
    if not toks:
        return None
    best, best_r = 0.0, None
    for r in roster:
        rt = [t for t in _norm(r["name"]).split() if t not in _CONNECTORS]
        if not rt:
            continue
        sc = _span_sim(toks, rt)
        # nombre concatenado vs cada token: cubre que Whisper junte apellidos ("Marí Bosó"->"Mariboso")
        rj = "".join(rt)
        sc = max(sc, max((difflib.SequenceMatcher(None, rj, t).ratio() for t in toks), default=0.0))
        if sc > best or (sc == best and best_r and r.get("n", 0) > best_r.get("n", 0)):
            best, best_r = sc, r
    return best_r if best >= thr else None


# ---------------------------------------------------------------- detección de relevos
def _detect_events(transcript: dict, cfg, roster=None):
    """Devuelve (segs, events, seg_event).

    events[k] = {'start','name'(NER crudo),'party'(NER crudo)}  -> un relevo de turno.
    seg_event[i] = índice del evento (orador) al que pertenece el segmento i; -1 = Presidencia.
    """
    from .index import get_embedder
    segs = sorted(transcript["segments"], key=lambda s: s.get("start", 0.0))
    texts = [(s.get("text", "") or "").strip() for s in segs]
    n = len(segs)
    windows = [(texts[i] + " " + (texts[i + 1] if i + 1 < n else "")).strip() for i in range(n)]

    emb = get_embedder(cfg)
    P = np.asarray(emb.encode(_PROTOS, normalize_embeddings=True))
    V = np.asarray(emb.encode(windows, normalize_embeddings=True,
                              batch_size=getattr(cfg.embeddings, "batch_size", 8)))
    sims = (V @ P.T).max(axis=1)
    ner = {i: _entities(windows[i]) for i in range(n) if sims[i] >= _SIM_THR}

    events, seg_event, cur, cooldown = [], [], -1, 0
    for i, s in enumerate(segs):
        if cooldown and sims[i] >= _SIM_THR:        # cola de un anuncio partido
            seg_event.append(-1); cooldown = 0; continue
        cooldown = 0
        if sims[i] >= _SIM_THR:
            pers, orgs = ner.get(i, ([], []))
            if pers or _real_group(orgs):            # relevo válido (orador o grupo real)
                gaz = _announced_name(windows[i], roster) if roster else None
                has_palabra = "palabra" in windows[i].lower()
                # descartar SOLO si no hay anuncio fiable. Si "la palabra X" nombra a alguien
                # FUERA del roster (municipios con lista incompleta), se usa ese nombre (NER) en
                # vez de perder el relevo -> robusto a rosters imperfectos.
                if roster and gaz is None and not _has_gov(orgs) and not (has_palabra and pers):
                    seg_event.append(cur); continue
                if gaz:                              # nombre anunciado emparejado al roster (fiable)
                    nm, pty = gaz["name"], gaz["party"]
                else:                                # si no, el nombre DICHO (NER) + (Gobierno si aplica)
                    nm = _pick_person(pers)
                    pty = _pick_party(orgs)
                    if nm is None and _has_gov(orgs):
                        nm = "(miembro del Gobierno)"
                events.append({"start": s["start"], "name": nm, "party": pty})
                cur = len(events) - 1
                seg_event.append(-1)                 # el segmento del anuncio es Presidencia
                cooldown = 1
                continue
        seg_event.append(cur)
    return segs, events, seg_event


def _build_turns(segs) -> list[dict]:
    """Agrupa segmentos consecutivos del mismo orador en turnos."""
    turns = []
    for s in segs:
        if turns and turns[-1]["name"] == s["name"] and turns[-1]["party"] == s["party"]:
            turns[-1]["end"] = s["end"]; turns[-1]["n"] += 1
        else:
            turns.append({"name": s["name"], "party": s["party"],
                          "start": s["start"], "end": s["end"], "n": 1})
    return turns


def _apply(segs, seg_event, names) -> list[dict]:
    """Escribe seg['name']/seg['party'] (names[k] = (nombre,partido) por evento) y devuelve turnos."""
    for s, k in zip(segs, seg_event):
        if k is None or k < 0 or k >= len(names):
            s["name"], s["party"] = "Presidencia", ""
        else:
            nm, pty = names[k]
            s["name"], s["party"] = (nm or "(sin identificar)"), (pty or "")
    return _build_turns(segs)


# ---------------------------------------------------------------- vía ROSTER
def link_roster(name, party, roster, thr: float = 0.62):
    """Empareja un nombre del NER con el roster por similitud de tokens. (nombre, partido)."""
    if not name or not roster:
        return name, party
    best, best_r = 0.0, None
    for r in roster:
        sc = _name_sim(name, r["name"])
        if sc > best or (sc == best and best_r and r.get("n", 0) > best_r.get("n", 0)):
            best, best_r = sc, r
    if best_r and best >= thr:
        return best_r["name"], (best_r.get("party") or party)
    return name, party


# ---------------------------------------------------------------- vía DIARIO (alineamiento)
def load_diario_seq(diario_path) -> list[tuple[str, str]]:
    """Orden oficial de oradores sustantivos del Diario: [(nombre, partido)], sin presidencia."""
    from .diario import attach_parties, extract_text, parse_interventions
    txt = extract_text(diario_path)
    seq = []
    for it in attach_parties(parse_interventions(txt), txt):
        sp = it["speaker"]
        if "PRESIDENT" in sp.upper():
            continue
        name = sp.split(" (")[0].strip()
        if not seq or seq[-1][0] != name:           # colapsa consecutivos del mismo orador
            seq.append((name, it.get("party", "")))
    return seq


def align_diario(events, diario_seq, roster=None, min_sim: float = 0.5):
    """Alineamiento Needleman-Wunsch entre relevos del vídeo y el orden del Diario.

    Solo acepta emparejados con similitud >= min_sim (conservador): el resto conserva
    el nombre del NER (limpiado con el roster si se pasa). Devuelve (nombre,partido) por evento.
    """
    A = [e["name"] or "" for e in events]
    B = [d[0] for d in diario_seq]
    parties = [d[1] for d in diario_seq]
    na, nb, GAP = len(A), len(B), -0.3

    def _score(i: int, j: int) -> float:
        a = A[i]
        if a and "gobierno" in _norm(a) and "gobierno" in _norm(parties[j]):
            return 0.6   # mismo tipo (Gobierno): alinea ministros por orden aunque el NER no dé nombre
        return _name_sim(a, B[j])
    dp = [[0.0] * (nb + 1) for _ in range(na + 1)]
    bk = [[None] * (nb + 1) for _ in range(na + 1)]
    for i in range(1, na + 1):
        dp[i][0] = dp[i - 1][0] + GAP; bk[i][0] = "up"
    for j in range(1, nb + 1):
        dp[0][j] = dp[0][j - 1] + GAP; bk[0][j] = "left"
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            s = _score(i - 1, j - 1)
            m = dp[i - 1][j - 1] + (s if s >= min_sim else -9.0)   # prohíbe matches flojos
            u, l = dp[i - 1][j] + GAP, dp[i][j - 1] + GAP
            best = max(m, u, l)
            dp[i][j] = best
            bk[i][j] = "diag" if best == m else ("up" if best == u else "left")
    i, j, match = na, nb, {}
    while i > 0 and j > 0:
        if bk[i][j] == "diag":
            if _score(i - 1, j - 1) >= min_sim:
                match[i - 1] = j - 1
            i -= 1; j -= 1
        elif bk[i][j] == "up":
            i -= 1
        else:
            j -= 1

    names = []
    for k, e in enumerate(events):
        if k in match:
            dn, dpty = diario_seq[match[k]]
            # partido limpio: del roster si lo tiene, si no el del Diario
            if roster:
                _, rpty = link_roster(dn, dpty, roster, thr=0.5)
                dpty = rpty or dpty
            names.append((dn.title() if dn.isupper() else dn, dpty))
        elif roster:
            names.append(link_roster(e["name"], e["party"], roster))
        else:
            names.append((e["name"], e["party"]))
    return names


# ---------------------------------------------------------------- orquestación
def assign_names(transcript, cfg=None, roster=None, diario=None) -> list[dict]:
    cfg = cfg or load_config()
    segs, events, seg_event = _detect_events(transcript, cfg, roster=roster)
    if diario:
        diario_seq = diario if isinstance(diario, list) else load_diario_seq(diario)
        names = align_diario(events, diario_seq, roster=roster)
    else:
        names = [link_roster(e["name"], e["party"], roster) for e in events]
    return _apply(segs, seg_event, names)


def name_transcript(path, cfg=None, roster=None, diario=None, save: bool = True) -> list[dict]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = assign_names(data, cfg=cfg, roster=roster, diario=diario)
    if save:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    named = sum(1 for t in turns if t["name"] not in ("Presidencia", "(sin identificar)"))
    print(f"[speakers] {len(data['segments'])} segmentos -> {len(turns)} turnos "
          f"({named} intervenciones con nombre) -> {path.name}")
    return turns


def _hms(t) -> str:
    t = int(t or 0)
    return f"{t // 3600}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Bloque B (2/2) — nombre/partido por intervención (NER+embeddings, sin regex).")
    ap.add_argument("transcript", help="JSON de transcripción (idealmente ya diarizado)")
    ap.add_argument("--roster", default=None, help="JSON con el roster de diputados/Gobierno")
    ap.add_argument("--diario", default=None, help="PDF del Diario de Sesiones de ESTA sesión (alineamiento por orden)")
    ap.add_argument("--dry-run", action="store_true", help="no guardar, solo mostrar turnos")
    args = ap.parse_args()
    roster = json.loads(Path(args.roster).read_text(encoding="utf-8")) if args.roster else None
    turns = name_transcript(args.transcript, roster=roster, diario=args.diario, save=not args.dry_run)
    print("\n=== TURNOS RECONSTRUIDOS (orden del día) ===")
    for t in turns:
        if t["n"] < 2 and t["name"] == "Presidencia":
            continue
        partido = f"  ({t['party']})" if t["party"] else ""
        print(f"  [{_hms(t['start'])}-{_hms(t['end'])}]  {t['name']}{partido}   ·{t['n']} seg")


if __name__ == "__main__":
    main()
