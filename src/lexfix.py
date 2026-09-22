"""Corrección de términos LOCALES mal transcritos, contra un vocabulario curado.

El ASR es bueno con el castellano corriente pero falla —de forma inconsistente— en lo
propio de cada municipio: 'mancomunidad' -> 'bancomunidad' / 'humana comunidad', nombres
de concejales, partidas, calles. Está comprobado que NINGÚN ajuste de Whisper lo arregla
(initial_prompt, hotwords y large-v3 cometen el mismo error). La solución es una pasada
posterior que, con el vocabulario que el ayuntamiento ya tiene (roster + términos + orden
del día), sustituye las variantes casi idénticas por la forma canónica.

No es regex ni reglas de clasificación: empareja por SIMILITUD FONÉTICA contra una lista
CERRADA de términos conocidos y solo corrige cuando la coincidencia es muy alta.
"""
from __future__ import annotations

import difflib
import json
import unicodedata
from pathlib import Path

_MAXW = 5   # máx. palabras de un término a considerar (cubre frases del orden del día)


def _key(s: str) -> str:
    """Clave fonética aproximada para castellano (b=v, h muda, seseo, dobles->simple)."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ll", "y").replace("qu", "k").replace("gu", "g")
    out: list[str] = []
    for i, c in enumerate(s):
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if not c.isalpha():
            continue
        if c == "h":
            continue
        if c == "v":
            c = "b"
        elif c == "z":
            c = "s"
        elif c == "c":
            c = "s" if nxt in "ei" else "k"
        elif c == "g" and nxt in "ei":
            c = "j"
        elif c == "y":
            c = "i"
        if not out or out[-1] != c:        # colapsa letras repetidas
            out.append(c)
    return "".join(out)


def _recap(canon: str, sample: str) -> str:
    """Devuelve el término canónico respetando mayúscula inicial si la tenía el original."""
    return canon[:1].upper() + canon[1:] if sample[:1].isupper() else canon


def load_terms_file(path: str) -> list[str]:
    """Glosario del municipio: un término por línea (ignora líneas vacías y las que empiezan por #).

    Aquí van SOLO términos de contenido y del orden del día (mancomunidad, FEDER, nombres de
    partidas/calles…). Los APELLIDOS del roster NO van aquí: son para etiquetar oradores, no
    para corregir el cuerpo (colisionan con palabras comunes: 'Lemos'/'lo hemos')."""
    p = Path(path)
    if not p.exists():
        return []
    terms = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    # las líneas 'MAL=BIEN' son alias exactos (ver load_aliases), no términos fonéticos
    return sorted({t for t in terms if t and not t.startswith("#") and "=" not in t},
                  key=len, reverse=True)


def load_aliases(path) -> dict:
    """Alias EXACTOS del fichero de términos: líneas 'MAL=BIEN' (p. ej. 'SEGES=SEGEX').

    Reemplazo de palabra COMPLETA (sin fonética, sin umbral) para errores conocidos del ASR
    que no llegan al umbral fonético. Riesgo cero si 'MAL' no existe como palabra real."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            a, b = ln.split("=", 1)
            if a.strip() and b.strip():
                # clave normalizada (minúsculas, solo alfanumérico): admite alias de UNA o DOS
                # palabras ('Cedipo Alvar=Sedipualba') y con guiones ('SEGES-SEGRA=...')
                key = "".join(ch for ch in a.lower() if ch.isalnum())
                out[key] = b.strip()
    return out


def load_vocab(roster_path: str | None = None, extra: list[str] | None = None) -> list[str]:
    vocab: list[str] = []
    if roster_path and Path(roster_path).exists():
        for r in json.loads(Path(roster_path).read_text(encoding="utf-8")):
            if r.get("name"):
                vocab.append(r["name"])
    vocab += extra or []
    return sorted(set(vocab), key=len, reverse=True)


def _match(span_words, canon, thr):
    """Mejor término para un span. Devuelve (term, ratio) o None. 'exact' si ya es correcto."""
    sk = _key("".join(span_words))
    if len(sk) < 5:
        return None
    best = None
    for term, tk in canon:
        if sk == tk:
            return ("exact", 1.0)        # ya está bien -> no tocar
        r = difflib.SequenceMatcher(None, sk, tk).ratio()
        if r >= thr and (best is None or r > best[1]):
            best = (term, r)
    return best


def correct_text(text: str, vocab: list[str], thr1: float = 0.90, thr_multi: float = 0.80,
                 aliases: dict | None = None):
    """Corrige una cadena de forma CONSERVADORA. Devuelve (texto_corregido, cambios).

    - Ancla en la palabra mínima: una palabra suelta solo se corrige con umbral ALTO (thr1),
      para no tocar palabras correctas parecidas ('comunidad' NO -> 'mancomunidad').
    - Solo si la palabra suelta no casa, prueba 2-3 palabras (thr_multi) para errores que
      parten el término ('humana comunidad' -> 'mancomunidad'). Nunca se come artículos,
      porque si la palabra del término ya está bien, casa como 'exact' y se deja.
    """
    canon = [(t, _key(t)) for t in vocab if len(_key(t)) >= 5]
    words = text.split()
    out: list[str] = []
    changes: list[tuple[str, str]] = []
    i = 0
    while i < len(words):
        if aliases:                               # alias exacto 'MAL=BIEN' (1 o 2 palabras)
            c1 = "".join(ch for ch in words[i].lower() if ch.isalnum())
            hit_n = 0
            if i + 1 < len(words):
                c2 = c1 + "".join(ch for ch in words[i + 1].lower() if ch.isalnum())
                if c2 in aliases:
                    hit_n = 2
            if not hit_n and c1 in aliases:
                hit_n = 1
            if hit_n:
                last = words[i + hit_n - 1]
                tail = "".join(ch for ch in last if not ch.isalnum() and ch not in "-")
                key = c1 if hit_n == 1 else c2
                new = aliases[key] + tail
                changes.append((" ".join(words[i:i + hit_n]), new)); out.append(new)
                i += hit_n; continue
        one = _match(words[i:i + 1], canon, thr1)
        if one and one[0] == "exact":
            out.append(words[i]); i += 1; continue
        if one:                                   # palabra suelta mal transcrita
            tail = "".join(ch for ch in words[i] if not ch.isalnum())
            new = _recap(one[0], words[i]) + tail
            changes.append((words[i], new)); out.append(new); i += 1; continue
        # ¿hay ya un término multipalabra CORRECTO empezando aquí? entonces no tocar nada
        # (evita 'machacar' frases largas que el ASR ya transcribió bien).
        maxsz = min(_MAXW, len(words) - i)
        if any(_match(words[i:i + s], canon, thr_multi) == ("exact", 1.0)
               for s in range(2, maxsz + 1)):
            out.append(words[i]); i += 1; continue
        hit = None                                # prueba término partido en 2..N palabras
        for size in range(2, maxsz + 1):
            m = _match(words[i:i + size], canon, thr_multi)
            if not m or m[0] == "exact":
                continue
            # ¿hace falta la 1ª palabra? si sin ella casa igual o mejor, sobra (era artículo)
            sub = _match(words[i + 1:i + size], canon, thr_multi)
            if sub and (sub[0] == "exact" or sub[1] >= m[1]):
                continue
            hit = (size, m[0]); break
        if hit:
            size, term = hit
            span = words[i:i + size]
            tail = "".join(ch for ch in span[-1] if not ch.isalnum())
            new = _recap(term, span[0]) + tail
            changes.append((" ".join(span), new)); out.append(new); i += size; continue
        out.append(words[i]); i += 1
    return " ".join(out), changes


def correct_segments(segments: list[dict], vocab: list[str],
                     thr1: float = 0.90, thr_multi: float = 0.80,
                     aliases: dict | None = None):
    total: list[tuple[str, str]] = []
    for seg in segments:
        fixed, ch = correct_text(seg.get("text", ""), vocab, thr1, thr_multi, aliases)
        if ch:
            seg["text"] = fixed
            total += ch
    return segments, total
