"""Fuente oficial de texto: Diario de Sesiones del Congreso.

De una URL de YouTube de un pleno -> (descripción del vídeo) -> enlace al Diario
-> PDF -> intervenciones estructuradas {speaker, party, text}. Es la fuente del
corpus de los Bloques B/C: texto OFICIAL, con orador y partido, sin ASR.

Uso (parsear un PDF ya descargado):
    python -m src.diario data/diarios/DSCD-15-PL-109.pdf
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

# Marca de orador en el cuerpo: "El señor APELLIDOS:" / "La señora X (Grupo ...):"
_SPEAKER_RE = re.compile(
    r"(?:El señor|La señora)\s+([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ'.\- ]+?)\s*(?:\(([^)]+)\))?\s*:"
)
# Cabecera de página repetida (a quitar)
_PAGE_HEADER_RE = re.compile(r"DIARIO DE SESIONES.*?P[áa]g\.\s*\d+", re.DOTALL)


def extract_text(pdf_path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    text = _PAGE_HEADER_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text)


_DATE_RE = re.compile(r"celebrada el [^,]*?(\d{1,2} de \w+ de \d{4})", re.IGNORECASE)


def session_date(text: str) -> str:
    """Extrae la fecha de la sesión de la cabecera del Diario."""
    m = _DATE_RE.search(text)
    return m.group(1) if m else ""


def parse_interventions(text: str) -> list[dict]:
    """Divide el texto del Diario en intervenciones por orador."""
    markers = list(_SPEAKER_RE.finditer(text))
    out: list[dict] = []
    for i, m in enumerate(markers):
        speaker = re.sub(r"\s+", " ", m.group(1)).strip()
        party = (m.group(2) or "").strip()
        start, end = m.end(), (markers[i + 1].start() if i + 1 < len(markers) else len(text))
        body = text[start:end].strip()
        if body:
            out.append({"speaker": speaker, "party": party, "text": body})
    return out


# raíces (stems) para tolerar truncamientos del parseo ("popula", "euskal", "sociali"...)
_GROUP_SIGLA = [
    ("social", "PSOE"), ("popul", "PP"), ("vox", "VOX"),
    ("ciuda", "Cs"),
    ("euska", "EH Bildu"), ("bildu", "EH Bildu"),
    ("esqu", "ERC"), ("republic", "ERC"),
    ("llibertat", "DL"),                    # Catalán (Democràcia i Llibertat), XI (2016): NO es Junts
    ("junts", "Junts"),                     # Junts per Catalunya (XV); en XIV iban en Plural
    ("confed", "Podemos"), ("podem", "Podemos"), ("unid", "Podemos"),
    ("plurinac", "Sumar"), ("sumar", "Sumar"),
    ("nacionalista vasco", "PNV"), ("vasc", "PNV"), ("eaj", "PNV"),
    ("canari", "CC"),
    ("plural", "Plural"),
    ("mixto", "Mixto"),
]

# tokens que delatan a un miembro del Gobierno (en el cargo o en el paréntesis)
_GOV_ROLE = ("ministr", "ministerio", "del gobierno", "candidat", "presidente del gobierno",
             "vicepresidente del", "vicepresidenta del")
_GROUP_RE = re.compile(r"grupo (parlamentario [a-záéíóúñ ]+|mixto)")
_NON_PARTY = ("PRESIDENT", "MINISTR", "VICEPRESID", "GOBIERNO", "SECRETARI")


def _sigla(group: str) -> str:
    g = (group or "").lower()
    for kw, s in _GROUP_SIGLA:
        if kw in g:
            return s
    return (group or "").strip()


def _party_for_speaker(low_text: str, speaker: str) -> str:
    """Busca el apellido del orador y el 'Grupo ...' que aparece justo después (en el sumario)."""
    name = speaker.lower().strip()
    idx = low_text.find(name)
    if idx == -1:
        name = name.split()[0]  # probar solo con el primer apellido
        idx = low_text.find(name)
        if idx == -1:
            return ""
    m = _GROUP_RE.search(low_text, idx, idx + 250)
    return _sigla(m.group(0)) if m else ""


def _is_gov(s: str) -> bool:
    s = (s or "").lower()
    return any(g in s for g in _GOV_ROLE)


def _gov_role(cargo: str) -> str:
    """Rol concreto del miembro del Gobierno según su cargo en la etiqueta del Diario."""
    c = (cargo or "").lower()
    if "candidat" in c:
        return "candidato"
    if "presidente del gobierno" in c or "presidenta del gobierno" in c:
        return "presidente del gobierno"
    if "vicepresident" in c:
        return "vicepresidente del gobierno"
    if "ministr" in c or "ministerio" in c:
        return "ministro"
    if "secretari" in c:
        return "secretario de estado"
    return "gobierno"


def _norm_name(s: str) -> str:
    """Normaliza el nombre del orador para casar variantes entre PDFs y con el registro.

    Sin acentos, MAYÚSCULAS, sin guiones/apóstrofos/puntos (el OCR a veces une 'González-Moro'
    -> 'GonzálezMoro') y SIN la 'i' catalana suelta ('Baldoví i Roda' = 'Baldoví Roda')."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    s = s.replace("-", "").replace("'", "").replace(".", "")
    return " ".join(t for t in s.split() if t != "I")


_KNOWN_SIGLAS = {"PP", "PSOE", "VOX", "Cs", "Podemos", "Sumar", "ERC",
                 "Junts", "EH Bildu", "PNV", "CC", "Plural", "Mixto", "DL"}


# Patrones FIABLES del sumario que emparejan orador<->grupo:
#   A) "señor/a Apellidos, del Grupo Parlamentario X"
#   B) "del Grupo Parlamentario X (señor/a Apellidos)"
_SUM_A = re.compile(r"se[ñn]or(?:a)?\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'.\- ]+?)\s*,?\s*del Grupo Parlamentario ([A-Za-záéíóúñ ]+)")
_SUM_B = re.compile(r"del Grupo Parlamentario ([A-Za-záéíóúñ ]+?)\s*\(\s*se[ñn]or(?:a)?\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'.\- ]+?)\s*\)")


def build_party_map(leg_texts) -> dict:
    """Mapa orador->partido POR LEGISLATURA desde el SUMARIO de los Diarios.

    El sumario empareja explícitamente cada orador con su grupo ('señor X, del Grupo Y');
    es la fuente fiable. Se agrega DENTRO de cada legislatura (no global) porque un mismo
    diputado puede cambiar de grupo entre legislaturas (Baldoví: Mixto en XII, Plural en XIV)
    -> así cada legislatura es COHERENTE. Entrada: iterable de (legislatura, texto).
    Salida: {"12": {orador: sigla}, "13": {...}, ...}."""
    from collections import Counter, defaultdict
    acc: dict[str, dict] = defaultdict(lambda: defaultdict(Counter))
    for leg, txt in leg_texts:
        names = acc[str(leg)]
        for m in _SUM_A.finditer(txt):
            sig = _sigla("grupo parlamentario " + m.group(2))
            if sig in _KNOWN_SIGLAS:
                names[_norm_name(m.group(1))][sig] += 1
        for m in _SUM_B.finditer(txt):
            sig = _sigla("grupo parlamentario " + m.group(1))
            if sig in _KNOWN_SIGLAS:
                names[_norm_name(m.group(2))][sig] += 1
    return {leg: {k: c.most_common(1)[0][0] for k, c in names.items()}
            for leg, names in acc.items()}


def _looks_like_firstname(s: str) -> bool:
    """El paréntesis es un nombre de pila (don/doña ...), no un cargo ni un grupo.

    Sirve para homónimos: 'El señor FERNÁNDEZ DÍAZ (don Jorge)' -> el paréntesis es el
    nombre, no el partido; se pega al nombre y el partido se busca por el apellido."""
    t = (s or "").strip().lower()
    return t.startswith("don ") or t.startswith("doña ") or t.startswith("doňa ")


def _within_edit1(a: str, b: str) -> bool:
    """True si la distancia de edición entre a y b es <= 1 (1 sustitución/inserción/borrado).

    Sirve para fusionar variantes de OCR del nombre contra el registro oficial: 'RUFÁAN'
    -> 'RUFIÁN'. Solo se fusiona si el match es ÚNICO (ver attach_parties) -> sin falsos."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    if la > lb:                                   # asegura la <= lb
        a, b, la, lb = b, a, lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] != b[j]:
            if skipped:
                return False
            skipped = True
            j += 1                                # salta un carácter en el más largo
        else:
            i += 1
            j += 1
    return True


def load_overrides(path) -> dict:
    """Correcciones MANUALES orador->partido (CSV: 'speaker', 'party_correcto', y opcional
    'legislatura'). Tiene PRIORIDAD sobre todo: es la última palabra del revisor humano.

    Clave (legislatura|None, nombre): si 'legislatura' está vacía, la corrección vale para
    TODAS las legislaturas; si tiene un número, solo para esa (para quien cambia de grupo)."""
    import csv
    out: dict[tuple, str] = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            corr = (row.get("party_correcto") or "").strip()
            sp = (row.get("speaker") or "").strip()
            leg = (row.get("legislatura") or "").strip()
            if corr and sp:
                out[(leg or None, _norm_name(sp))] = corr
    return out


def load_registry(path) -> dict:
    """Registro OFICIAL diputado->grupo (roster) como JSON {nombre: sigla}.

    Es un input legítimo (la lista de miembros), no el Diario: rellena a los oradores que
    nunca aparecieron emparejados con su grupo en ningún sumario."""
    import json as _json
    p = Path(path)
    if not p.exists():
        return {}
    raw = _json.loads(p.read_text(encoding="utf-8"))
    # estructura {legislatura: {nombre: sigla}}; el grupo es específico de cada legislatura
    return {leg: {_norm_name(k): v for k, v in d.items()} for leg, d in raw.items()}


def attach_parties(interventions: list[dict], text: str, party_map: dict | None = None,
                   registry: dict | None = None, overrides: dict | None = None,
                   leg: int | None = None) -> list[dict]:
    """Asigna 'party' y 'role' a cada intervención. 'party' es SIEMPRE un partido (sigla) o ""
    -> nunca "Gobierno"/"Presidencia" (eso es la función, va en 'role').

    'role': diputado | candidato | presidente del gobierno | vicepresidente del gobierno |
    ministro | secretario de estado | presidencia | representante autonómico.

    party_map y registry son los de ESTA legislatura (coherencia por legislatura). El partido
    de CUALQUIER orador (incluido el Gobierno: p.ej. Sánchez = PSOE) se resuelve igual, en
    orden de fiabilidad: 1) override manual  2) sumario de la legislatura  3) registro oficial
    4) su propio paréntesis  5) "" (nunca adivinar). Las variantes de OCR del nombre
    ('RODRÍ GUEZ', 'RUFÁAN') se fusionan contra el registro."""
    pmap = party_map or {}
    pmap_t = {k.replace(" ", ""): v for k, v in pmap.items()}
    reg = registry or {}                         # {nombre: [sigla, apellidos_canónicos]}
    reg_t = {k.replace(" ", ""): v for k, v in reg.items()}
    reg_keys = list(reg.keys())
    ovr = overrides or {}
    leg_s = str(leg) if leg is not None else None
    fcache: dict[str, list | None] = {}          # cache de fusiones fuzzy por nombre

    def resolve(name_key: str):
        """(sigla, hit) por orden de fiabilidad: override > sumario(leg) > registro > "".

        hit = [sigla, nombre_canónico] del registro (para fusionar variantes) o None. El
        registro se prueba exacto, sin espacios (OCR), a 1 carácter ('RUFÁAN'->'RUFIÁN') o por
        prefijo único (truncamientos)."""
        tkey = name_key.replace(" ", "")
        hit = reg.get(name_key) or reg_t.get(tkey)
        if hit is None and len(name_key) >= 6 and reg_keys:
            if name_key not in fcache:
                d1, pre = [], []
                for k in reg_keys:
                    if _within_edit1(name_key, k):
                        d1.append(k)
                    elif k.startswith(name_key + " ") or name_key.startswith(k + " "):
                        pre.append(k)
                chosen = d1[0] if len(d1) == 1 else (pre[0] if not d1 and len(pre) == 1 else None)
                fcache[name_key] = reg[chosen] if chosen else None
            hit = fcache[name_key]
        if (leg_s, name_key) in ovr:
            return ovr[(leg_s, name_key)], hit       # 1a) corrección manual de ESA legislatura
        if (None, name_key) in ovr:
            return ovr[(None, name_key)], hit         # 1b) corrección manual para todas
        if name_key in pmap:
            return pmap[name_key], hit                # 2) sumario de la legislatura (consistente)
        if tkey in pmap_t:
            return pmap_t[tkey], hit
        if hit:
            return hit[0], hit                        # 3) registro oficial (roster)
        return "", hit

    for it in interventions:
        sp = it["speaker"]
        paren = it.get("party") or ""           # paréntesis del label (NOMBRE, CARGO o GRUPO)
        up = sp.upper()
        is_gov = _is_gov(sp) or _is_gov(paren)

        if up.startswith("REPRESENTANTE"):      # representante de un parlamento autonómico
            if paren:                           # el paréntesis es el apellido de la persona
                it["speaker"] = f"{paren} ({sp})"
            it["party"], it["role"] = "", "representante autonómico"
            continue
        if "DEFENSOR DEL PUEBLO" in up:         # figura institucional, no es de partido
            if paren:
                it["speaker"] = f"{paren} ({sp})"
            it["party"], it["role"] = "", "otros"
            continue
        if is_gov:                              # Gobierno: PARTIDO real en party, CARGO en role
            role_part, name_part = (sp, paren) if _is_gov(sp) else (paren, sp)
            sig, hit = resolve(_norm_name(name_part)) if name_part else ("", None)
            name_disp = hit[1] if hit else name_part.title()
            it["speaker"] = (f"{name_disp} ({role_part.title()})"
                             if name_disp and role_part else (name_disp or sp))
            it["party"], it["role"] = sig, _gov_role(role_part)
            continue
        if "PRESIDENT" in up or "VICEPRESIDENT" in up or "SECRETARI" in up:  # presidencia (neutral)
            it["party"], it["role"] = "", "presidencia"
            continue

        # diputado/a
        name_key = _norm_name(sp)
        firstname = ""
        if paren and _looks_like_firstname(paren):   # nombre de pila (homónimo) -> parte del nombre
            firstname, paren = paren, ""
        sig, hit = resolve(name_key)
        if not sig and paren:                        # 4) su propio paréntesis (SOLO si es sigla real)
            cand = _sigla(paren)
            sig = cand if cand in _KNOWN_SIGLAS else ""   # candado: party = sigla o "", nunca un nombre
        if hit:                                      # nombre canónico del registro (une variantes)
            it["speaker"] = hit[1].upper()
        if firstname:
            it["speaker"] = f"{it['speaker']} ({firstname})"
        it["party"], it["role"] = sig, "diputado"
    return interventions


_ORDEN_RE = re.compile(r"orden del d[ií]a[\s:.]*(.{15,400})", re.IGNORECASE | re.DOTALL)


def session_topic(text: str) -> str:
    """Tema(s) de la sesión: el bloque de 'ORDEN DEL DÍA' de la cabecera (campo etiquetado)."""
    m = _ORDEN_RE.search(text)
    if not m:
        return ""
    t = re.sub(r"\s+", " ", m.group(1))
    t = re.sub(r"\.{3,}\s*\d*", " ", t)     # quita los 'líderes' de puntos + nº de página del sumario
    for stop in ("SUMARIO", "Se abre la sesión", "Se reanuda", "comienza la sesión"):
        i = t.lower().find(stop.lower())
        if i > 15:
            t = t[:i]
    return re.sub(r"\s+", " ", t).strip(" .:;-")[:300]


# Dos formatos de resultado en los Diarios (el número va ANTES o DESPUÉS de la etiqueta):
#  F1: "votos emitidos, 350; a favor, 170; en contra, 180; abstenciones, 0"
#  F2: "243 votos a favor más 2 votos telemáticos, 245; 77 en contra y 15 abstenciones"
#      (voto telemático: el TOTAL es el número tras 'más N votos telemáticos,')
_VOTES_RE = re.compile(
    r"(?:votos\s+emitidos[,:]?\s*(\d+)[;,.\s]+)?"
    r"(?:votos\s+)?a\s+favor[,:]?\s*(\d+)[;,.\s]+"
    r"(?:votos\s+)?en\s+contra[,:]?\s*(\d+)"
    r"(?:[;,.\s]+abstenci\w*[,:]?\s*(\d+))?",
    re.IGNORECASE)
_VOTES_RE2 = re.compile(
    r"(\d+)\s+votos?\s+a\s+favor(?:\s+más\s+\d+\s+votos?\s+telem\w*,?\s*(\d+))?"
    r"[;,\s]+(\d+)\s+(?:votos?\s+)?en\s+contra(?:\s+más\s+\d+\s+votos?\s+telem\w*,?\s*(\d+))?"
    r"(?:[;,\sy]+(\d+)\s+abstenci\w*)?",
    re.IGNORECASE)


def extract_votes(text: str) -> list[dict]:
    """Saca los resultados de votación a una lista estructurada (no dentro del texto).

    Combina los dos formatos del Diario, en orden de aparición. En el formato telemático
    usa el TOTAL (presencial + telemático)."""
    found = []
    for m in _VOTES_RE.finditer(text):
        found.append((m.start(), {
            "emitidos": int(m.group(1)) if m.group(1) else None,
            "a_favor": int(m.group(2)), "en_contra": int(m.group(3)),
            "abstenciones": int(m.group(4)) if m.group(4) else None,
        }))
    for m in _VOTES_RE2.finditer(text):
        af = int(m.group(2) or m.group(1))      # total telemático si lo hay, si no el presencial
        ec = int(m.group(4) or m.group(3))
        ab = int(m.group(5)) if m.group(5) else None
        found.append((m.start(), {"emitidos": None, "a_favor": af, "en_contra": ec,
                                  "abstenciones": ab}))
    found.sort(key=lambda x: x[0])
    return [d for _, d in found]


_SOBRE_RE = re.compile(
    r"\bsobre\b\s+(.{10,150}?)(?:\.|\(n[úu]m|, que formula|\bque formula\b|$)", re.IGNORECASE)


def assign_topics(interventions: list[dict], text: str = "") -> list[dict]:
    """Etiqueta cada intervención con el punto del orden del día activo.

    Usa los anuncios de la Presidencia ('pasamos a la interpelación sobre X…') para
    saber el tema y lo PROPAGA a las intervenciones siguientes, de modo que hasta
    las respuestas cortas heredan el contexto del debate.
    """
    current = ""
    for it in interventions:
        is_chair = it.get("role") == "presidencia"
        if is_chair:
            low = it["text"].lower()
            m = _SOBRE_RE.search(it["text"])
            if m and any(k in low for k in ("interpelaci", "proposici", "moci",
                                            "comparecen", "debate", "toma en consider")):
                current = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
            elif "pregunta" in low and "formula" in low:
                current = "Preguntas al Gobierno"
            elif "interpelaci" in low:
                current = "Interpelaciones urgentes"
            elif "moci" in low:
                current = "Mociones"
            elif "proposici" in low and "ley" in low:
                current = "Proposiciones de ley"
            elif "comparecen" in low:
                current = "Comparecencias del Gobierno"
            elif "convalidaci" in low or "decreto-ley" in low:
                current = "Convalidación de reales decretos-leyes"
            elif "investidura" in low:
                current = "Debate de investidura"
            elif "presupuest" in low:
                current = "Presupuestos Generales del Estado"
        it["topic"] = current
    return interventions


def to_transcript(interventions: list[dict], source: str = "", min_chars: int = 120) -> dict:
    """Convierte las intervenciones al formato de transcripción para indexar.

    Filtra el TRÁMITE: fuera las intervenciones de Presidencia (modera, no debate)
    y los turnos muy cortos ("Muchas gracias…"), que solo meten ruido en la búsqueda.
    """
    segments = []
    for it in interventions:
        text = it["text"].strip()
        if it.get("role") == "presidencia" or len(text) < min_chars:    # fuera trámite de la Mesa
            continue
        who = it["speaker"] + (f" ({it['party']})" if it["party"] else "")
        i = len(segments)
        segments.append({"id": i, "start": float(i), "end": float(i) + 1.0,
                         "text": text, "speaker": who})
    return {"audio": source, "language": "es", "duration": None,
            "model": "diario", "segments": segments}


def diario_url_from_youtube(youtube_url: str) -> str | None:
    """Saca de la descripción del vídeo el enlace al Diario y resuelve el acortador."""
    res = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--remote-components", "ejs:github",
         "--skip-download", "--print", "%(description)s", youtube_url],
        capture_output=True, text=True,
    )
    m = re.search(r"Diario de Sesiones:\s*(https?://\S+)", res.stdout or "")
    if not m:
        return None
    req = urllib.request.Request(m.group(1), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.url  # URL final tras redirecciones (el PDF de congreso.es)


def download_diario(pdf_url: str, out_dir) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / pdf_url.split("/")[-1]
    req = urllib.request.Request(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        dest.write_bytes(r.read())
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description="Parsea un Diario de Sesiones (PDF) en intervenciones.")
    ap.add_argument("pdf", help="ruta al PDF del Diario de Sesiones")
    ap.add_argument("-n", type=int, default=6, help="cuántas intervenciones mostrar")
    ap.add_argument("--index", action="store_true",
                    help="trocear + embeddings + indexar las intervenciones en ChromaDB (Bloque C)")
    args = ap.parse_args()

    text = extract_text(args.pdf)
    ints = attach_parties(parse_interventions(text), text)
    print(f"[diario] {len(ints)} intervenciones detectadas\n")
    for it in ints[:args.n]:
        who = it["speaker"] + (f" ({it['party']})" if it["party"] else "")
        print(f"### {who}\n{it['text'][:280]}...\n")

    if args.index:
        import json
        from .config import load_config, resolve_path
        from .index import index_transcript
        cfg = load_config()
        stem = Path(args.pdf).stem
        tr_dir = resolve_path(cfg.paths.transcripts)
        tr_dir.mkdir(parents=True, exist_ok=True)
        tr_path = tr_dir / f"{stem}.json"
        tr_path.write_text(
            json.dumps(to_transcript(ints, source=stem), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[diario] indexando {len(ints)} intervenciones en ChromaDB...")
        index_transcript(tr_path, {"id": stem, "title": f"Diario {stem}", "url": ""}, cfg)


if __name__ == "__main__":
    main()
