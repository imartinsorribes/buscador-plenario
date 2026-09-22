"""Compara nuestro Diario CIEGO (generado del vídeo) con el Diario OFICIAL, campo a campo,
y da un "% de parecido". Ambos en el mismo esquema JSON.

Mide:
  - Cobertura  : % de intervenciones oficiales que capturamos (alineadas por CONTENIDO).
  - Acierto    : % de esas cuyo ORADOR coincide (quién dijo qué).
  - Fidelidad  : similitud semántica media del texto (el oficial está editado, no es literal).
  - Tema       : similitud del orden del día.
  - Votaciones : cuántas de las oficiales capturamos (dimensión débil a ciegas).
  - Parecido   : media de cobertura·acierto·fidelidad·tema (votaciones aparte, informativo).

Uso:  python scripts/compare_diario.py <ciego.json> <oficial.json>
"""
import difflib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config, resolve_path  # noqa: E402
from src.index import get_embedder  # noqa: E402

_CONN = {"de", "del", "la", "las", "los", "el", "i", "y", "e", "da", "do", "san"}


def _norm(s):
    return " ".join(unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().split())


def name_sim(a, b):
    at = [w for w in _norm(a).split() if w not in _CONN] or _norm(a).split()
    bt = [w for w in _norm(b).split() if w not in _CONN] or _norm(b).split()
    if not at or not bt:
        return 0.0
    return sum(max(difflib.SequenceMatcher(None, x, y).ratio() for y in bt) for x in at) / len(at)


def substantive(diario, skip_roles=("presidencia",)):
    """Intervenciones con texto sustantivo (fuera Presidencia/trámite), agrupando consecutivas."""
    out = []
    for it in diario["interventions"]:
        if it.get("role") in skip_roles:
            continue
        who = it["speaker"].split(" (")[0].strip()
        txt = (it.get("text") or "").strip()
        if who in ("(sin identificar)", "(miembro del Gobierno)", ""):
            who = "?"
        if out and out[-1]["who"] == who:
            out[-1]["text"] += " " + txt
        else:
            out.append({"who": who, "text": txt})
    return [x for x in out if len(x["text"]) > 120]


def _align(S, gap=-0.2):
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
    ours = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    offi = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    emb = get_embedder(load_config())

    O = substantive(ours)
    F = substantive(offi)
    OV = np.asarray(emb.encode([x["text"] for x in O], normalize_embeddings=True, batch_size=8))
    FV = np.asarray(emb.encode([x["text"] for x in F], normalize_embeddings=True, batch_size=8))
    S = OV @ FV.T
    pairs = [(a, b) for a, b in _align(S) if S[a, b] >= 0.5]
    conf = [(a, b) for a, b in pairs if S[a, b] >= 0.8]   # pares fiables = MISMA intervención
    base = conf or pairs                                   # el acierto SOLO sobre esos (no mezcla
    cobertura = len(pairs) / max(len(F), 1)                # fallo de alineación con fallo de nombre)
    acierto = sum(1 for a, b in base if name_sim(O[a]["who"], F[b]["who"]) >= 0.6) / max(len(base), 1)
    fidelidad = float(np.mean([S[a, b] for a, b in pairs])) if pairs else 0.0

    # tema
    tv = emb.encode([ours.get("tema_sesion") or "", offi.get("tema_sesion") or ""],
                    normalize_embeddings=True)
    tema = float(np.dot(tv[0], tv[1]))

    # votaciones (cuántas oficiales capturamos por tripleta a_favor/en_contra)
    def vkey(v):
        return (v.get("a_favor"), v.get("en_contra"))
    ov = {vkey(v) for v in ours.get("votaciones", [])}
    fv = [vkey(v) for v in offi.get("votaciones", [])]
    vmatch = sum(1 for k in fv if k in ov)

    parecido = float(np.mean([cobertura, acierto, fidelidad, tema]))

    print(f"=== Diario CIEGO vs OFICIAL  ({offi.get('id','')}) ===")
    print(f"Intervenciones sustantivas — nuestras: {len(O)} · oficiales: {len(F)} · alineadas: {len(pairs)}")
    print(f"  Cobertura (contenido oficial capturado): {cobertura:.1%}")
    print(f"  Acierto de orador (quién dijo qué):      {acierto:.1%}  (sobre {len(base)} pares de contenido fiable)")
    print(f"  Fidelidad de contenido (semántica):      {fidelidad:.3f}")
    print(f"  Tema / orden del día (semántica):        {tema:.1%}")
    print(f"  Votaciones capturadas:                   {vmatch}/{len(fv)}  (débil a ciegas)")
    print(f"  ----------------------------------------------------")
    print(f"  PARECIDO GLOBAL (cob·acierto·fidel·tema): {parecido:.1%}")

    out = resolve_path("data/processed") / f"parecido_{offi.get('id','x')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rep = [f"# Acta CIEGA (nuestra) vs Diario OFICIAL — {offi.get('id','')}", "",
           f"- **Parecido global: {parecido:.1%}** · Cobertura {cobertura:.0%} · "
           f"Acierto orador {acierto:.0%} · Fidelidad {fidelidad:.2f} · Tema {tema:.0%} · "
           f"Votaciones {vmatch}/{len(fv)}", "",
           "| # | Nuestra acta (orador) | Diario oficial (orador) | ¿= ? | nuestro texto | texto oficial |",
           "|---|---|---|:---:|---|---|"]
    for k, (a, b) in enumerate(sorted(pairs, key=lambda p: p[1]), 1):
        ok = "sí" if name_sim(O[a]["who"], F[b]["who"]) >= 0.6 else "**NO**"
        tn = " ".join(O[a]["text"][:120].split()).replace("|", "/")
        to = " ".join(F[b]["text"][:120].split()).replace("|", "/")
        rep.append(f"| {k} | {O[a]['who']} | {F[b]['who']} | {ok} | {tn}… | {to}… |")
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"\nInforme (tabla lado a lado) -> {out}")


if __name__ == "__main__":
    main()
