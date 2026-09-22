"""Compara NUESTRA acta (generada del vídeo) con el DIARIO oficial -> "qué tan buenos somos".

Alinea por CONTENIDO (no por nombre, para no hacer trampa: el nombre se mide aparte) las
intervenciones nuestras y las oficiales, en orden, y reporta:
  - Cobertura: % de intervenciones del acta oficial que capturamos.
  - Acierto de orador: % de intervenciones alineadas cuyo orador coincide (quién dijo qué).
  - Fidelidad de contenido: similitud semántica media del texto (nuestro vs oficial).

Honesto SOLO si la transcripción se nombró sin el Diario (NER+roster). Si se nombró con
--diario, el acierto de orador sale inflado (circular).

Uso:  python scripts/compare_acta.py <whisper_named.json> <diario.pdf>
"""
import difflib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config, resolve_path  # noqa: E402
from src.diario import attach_parties, extract_text, parse_interventions  # noqa: E402
from src.index import get_embedder  # noqa: E402

_CONN = {"de", "del", "la", "las", "los", "el", "i", "y", "e", "da", "do", "san"}


def _norm(s):
    return " ".join(unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().split())


def _toks(s):
    t = [w for w in _norm(s).split() if w not in _CONN]
    return t or _norm(s).split()


def name_sim(a, b):
    at, bt = _toks(a), _toks(b)
    if not at or not bt:
        return 0.0
    return sum(max(difflib.SequenceMatcher(None, x, y).ratio() for y in bt) for x in at) / len(at)


def _group(items, who_key, txt_key, skip):
    out = []
    for it in items:
        who = it[who_key]
        txt = (it[txt_key] or "").strip()
        if not txt:
            continue
        if out and out[-1]["who"] == who:
            out[-1]["text"] += " " + txt
        else:
            out.append({"who": who, "text": txt})
    return [x for x in out if x["who"] not in skip and len(x["text"]) > 120]


def our_interventions(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    segs = sorted(d["segments"], key=lambda x: x.get("start", 0.0))
    items = [{"who": (s.get("name") or "").strip(), "text": s.get("text", "")} for s in segs]
    return _group(items, "who", "text", {"Presidencia", "", "(sin identificar)", "(miembro del Gobierno)"})


def official_interventions(pdf):
    txt = extract_text(pdf)
    items = []
    for it in attach_parties(parse_interventions(txt), txt):
        sp = it["speaker"]
        if "PRESIDENT" in sp.upper():
            continue
        items.append({"who": sp.split(" (")[0].strip(), "text": it["text"]})
    return _group(items, "who", "text", {""})


def _align(S, gap=-0.2):
    """Needleman-Wunsch monotónico maximizando similitud de contenido."""
    na, nb = S.shape
    dp = [[0.0] * (nb + 1) for _ in range(na + 1)]
    bk = [[None] * (nb + 1) for _ in range(na + 1)]
    for i in range(1, na + 1):
        dp[i][0] = dp[i - 1][0] + gap; bk[i][0] = "up"
    for j in range(1, nb + 1):
        dp[0][j] = dp[0][j - 1] + gap; bk[0][j] = "left"
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            m = dp[i - 1][j - 1] + float(S[i - 1, j - 1])
            u, l = dp[i - 1][j] + gap, dp[i][j - 1] + gap
            best = max(m, u, l)
            dp[i][j] = best
            bk[i][j] = "diag" if best == m else ("up" if best == u else "left")
    i, j, pairs = na, nb, []
    while i > 0 and j > 0:
        if bk[i][j] == "diag":
            pairs.append((i - 1, j - 1)); i, j = i - 1, j - 1
        elif bk[i][j] == "up":
            i -= 1
        else:
            j -= 1
    return pairs


def main():
    ours = our_interventions(sys.argv[1])
    offi = official_interventions(sys.argv[2])
    emb = get_embedder(load_config())
    OV = np.asarray(emb.encode([x["text"] for x in ours], normalize_embeddings=True, batch_size=8))
    FV = np.asarray(emb.encode([x["text"] for x in offi], normalize_embeddings=True, batch_size=8))
    S = OV @ FV.T

    pairs = _align(S)
    good = [(a, b) for a, b in pairs if S[a, b] >= 0.5]   # solo alineamientos de contenido fiables
    cobertura = len(good) / max(len(offi), 1)
    acierto = sum(1 for a, b in good if name_sim(ours[a]["who"], offi[b]["who"]) >= 0.6) / max(len(good), 1)
    fidelidad = float(np.mean([S[a, b] for a, b in good])) if good else 0.0

    print(f"Intervenciones — nuestras: {len(ours)} · oficiales: {len(offi)} · alineadas: {len(good)}")
    print(f"Cobertura (del acta oficial):          {cobertura:.1%}")
    print(f"Acierto de orador (quién dijo qué):    {acierto:.1%}")
    print(f"Fidelidad de contenido (semántica):    {fidelidad:.3f}")
    print("\nEjemplos (nuestro orador  ->  oficial):")
    for a, b in good[:12]:
        ok = "OK " if name_sim(ours[a]["who"], offi[b]["who"]) >= 0.6 else "XX "
        print(f"  {ok} {ours[a]['who'][:26]:26s} -> {offi[b]['who'][:26]:26s} (sim {S[a,b]:.2f})")

    # --- informe detallado para ESTUDIAR las diferencias (markdown) ---
    stem = Path(sys.argv[1]).stem
    out = resolve_path("data/processed") / f"comparacion_{stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rep = [f"# Acta generada vs Diario oficial — {stem}", "",
           f"- Cobertura: {cobertura:.1%}  ·  Acierto de orador: {acierto:.1%}  ·  Fidelidad: {fidelidad:.3f}", "",
           "| # | Orador (nuestro) | Orador (oficial) | ¿coincide? | sim | nuestro texto | texto oficial |",
           "|---|---|---|---|---|---|---|"]
    for k, (a, b) in enumerate(good, 1):
        ok = "sí" if name_sim(ours[a]["who"], offi[b]["who"]) >= 0.6 else "**NO**"
        tn = ours[a]["text"][:100].replace("|", " ").replace("\n", " ")
        to = offi[b]["text"][:100].replace("|", " ").replace("\n", " ")
        rep.append(f"| {k} | {ours[a]['who']} | {offi[b]['who']} | {ok} | {S[a,b]:.2f} | {tn}… | {to}… |")
    matched = {b for _, b in good}
    miss = [offi[j]["who"] for j in range(len(offi)) if j not in matched]
    if miss:
        rep += ["", "**Intervenciones oficiales NO capturadas:** " + ", ".join(miss)]
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"\nInforme para estudiar -> {out}")


if __name__ == "__main__":
    main()
