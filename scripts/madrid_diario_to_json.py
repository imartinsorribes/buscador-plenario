"""Diario de Sesiones del Pleno del Ayuntamiento de MADRID (PDF) -> nuestro JSON estructurado.

Madrid SÍ publica un Diario de Sesiones VERBATIM (a diferencia de casi todos los municipios),
con formato propio distinto al del Congreso:
  - "El presidente:" / "El secretario general:"  -> presidencia
  - "<rol largo>, del Grupo Municipal <GRUPO>, don/doña <Nombre Apellidos>:"  -> concejal + grupo
Sirve como GROUND TRUTH para contrastar nuestro acta ciega en un municipio real con Diario.

Uso:  python scripts/madrid_diario_to_json.py data/diarios_madrid/DS_2432_PO_25_03_25.pdf
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import resolve_path  # noqa: E402
from src.diario import extract_text, extract_votes, session_date  # noqa: E402

# cabecera de página de Madrid (se repite en cada página) -> fuera
_HDR = re.compile(r"Diario de Sesiones del Pleno del Ayuntamiento de Madrid.*?N[úu]m\.\s*[\d.]+", re.DOTALL)
_STAGE = re.compile(r"\((?:Aplausos|Rumores|Protestas|Risas|El se[ñn]or[^)]*|La se[ñn]ora[^)]*)\.?\)")

# marcador de orador: presidencia/secretario  O  "..., don/doña Nombre Apellidos:"
_MARK = re.compile(
    r"(El presidente|El secretario general|El secretario|El alcalde|La alcaldesa)\s*:"
    r"|([^.:\n]{0,180}?\b(?:don|do[ñn]a)\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\-]+"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\-]+){0,3})\s*:")

_NAME = re.compile(r"(?:don|do[ñn]a)\s+(.+)$", re.IGNORECASE)
_GROUPS = [("partido popular", "PP"), ("m[áa]s madrid", "Más Madrid"),
           ("socialista", "PSOE"), ("vox", "VOX"), ("mixto", "Mixto")]


def _party(role_text: str) -> str:
    low = role_text.lower()
    for kw, sig in _GROUPS:
        if re.search(kw, low):
            return sig
    return ""


def parse_madrid(text: str) -> list[dict]:
    text = _HDR.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    # el cuerpo real empieza en "Se abre la sesión"; antes está el SUMARIO (no son intervenciones)
    mstart = re.search(r"se abre la sesi[óo]n", text, re.IGNORECASE)
    body = text[mstart.start():] if mstart else text
    out = []
    marks = list(_MARK.finditer(body))
    for i, m in enumerate(marks):
        if m.group(1):                              # presidencia / secretario
            speaker, party, role = m.group(1).strip(), "", "presidencia"
        else:
            seg = m.group(2)
            nm = _NAME.search(seg)
            speaker = re.sub(r"\s+", " ", nm.group(1)).strip() if nm else seg.strip()
            party, role = _party(seg), "concejal"
        start, end = m.end(), (marks[i + 1].start() if i + 1 < len(marks) else len(body))
        txt = _STAGE.sub("", body[start:end]).strip(" .—-")
        txt = re.sub(r"\s+", " ", txt)
        if len(txt) > 15:
            out.append({"speaker": speaker, "party": party, "role": role, "topic": "", "text": txt})
    return out


def main() -> None:
    pdf = sys.argv[1] if len(sys.argv) > 1 else "data/diarios_madrid/DS_2432_PO_25_03_25.pdf"
    text = extract_text(pdf)
    ivs = parse_madrid(text)
    out = resolve_path("data/diarios_json")
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf).stem
    data = {
        "id": stem,
        "legislatura": 0,
        "fecha": session_date(text) or "",
        "tema_sesion": "",
        "votaciones": extract_votes(text),
        "n_intervenciones": len(ivs),
        "interventions": ivs,
    }
    (out / f"{stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    # resumen
    from collections import Counter
    spk = Counter(it["speaker"] for it in ivs)
    pty = Counter(it["party"] for it in ivs if it["party"])
    print(f"{len(ivs)} intervenciones · {len(spk)} oradores distintos · votaciones {len(data['votaciones'])}")
    print("oradores top:", [f"{n}×{s[:24]}" for s, n in spk.most_common(8)])
    print("por grupo:", dict(pty))
    print(f"-> data/diarios_json/{stem}.json")


if __name__ == "__main__":
    main()
