"""Mapa político: posición de cada grupo sobre ejes temáticos interpretables.

La idea, en una frase: un EJE se define con dos polos textuales (p. ej. en economía
«intervención estatal» frente a «libre mercado»); se proyecta sobre ese eje el discurso
de cada grupo en el tema y el escalar resultante ES la coordenada. Como la dirección la
fijamos nosotros con los polos, el eje es interpretable por construcción (no es un PCA
ciego cuya varianza dominante sería el tema o el binomio gobierno-oposición).

Precisión.  Para cada (grupo, eje) se hace en dos pasos, que es la clave:
  1. SELECCIÓN temática — se recuperan de ChromaDB los fragmentos del grupo más afines
     a la *materia* del eje (una consulta neutra del asunto, no de un polo) y se filtran
     por relevancia mínima. Así medimos sobre lo que de verdad habla del tema.
  2. PROYECCIÓN direccional — el centroide (media ponderada por relevancia) de esos
     fragmentos se proyecta sobre el vector del eje. La escala se ancla a los propios
     polos: la coordenada de cada polo marca +1 y -1, de modo que el resultado es
     comparable y estable entre consultas, no dependiente de la muestra.

Eficiencia.  El modelo de embeddings se carga UNA vez; los vectores de los ejes (polos y
materia) se calculan UNA vez por proceso; cada par (grupo, eje) es una sola consulta
vectorial barata (los embeddings ya están indexados). Pensado para vivir tras un proceso
de larga duración (API) y atender muchas peticiones sin recargar nada.

Las posiciones miden CÓMO se habla en tribuna, no la ideología «verdadera»: dependen del
corpus y de cómo se redacten los polos. Por eso conviene validarlas contra una escala
externa (CHES) o las votaciones reales.

Uso:
    python -m src.political_map compute PSOE PP VOX
    python -m src.political_map compute "Unidas Podemos" VOX --temas economia aborto
    python -m src.political_map ejes            # vuelca la definición de ejes (para el frontend)
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import numpy as np

from . import diarios
from .config import load_config
from .db import connect

# ====================================================================== ejes
# Fuente ÚNICA de la definición de ejes. `ejes_json()` la exporta para que el
# frontend use exactamente los mismos identificadores, etiquetas y polos.
#
#   subject      : consulta NEUTRA del asunto (selecciona los fragmentos del tema).
#   left/right   : anclas de cada polo. Varias por polo -> dirección más robusta.
#   *_short      : etiqueta corta de cada extremo del eje en la interfaz.
# Convenio de signo: el polo `left` es la coordenada -1; el `right`, +1.


@dataclass(frozen=True)
class Axis:
    id: str
    label: str
    subject: str
    left_short: str
    right_short: str
    left: tuple[str, ...]
    right: tuple[str, ...]


AXES: tuple[Axis, ...] = (
    Axis(
        "economia", "Economía",
        "política económica, impuestos, gasto público y papel del Estado en la economía",
        "Intervención estatal", "Libre mercado",
        left=("el Estado debe intervenir en la economía y aumentar el gasto público social",
              "subir los impuestos a las rentas altas y a las grandes empresas para financiar servicios públicos",
              "reforzar lo público frente al mercado"),
        right=("dejar que el mercado funcione con la mínima intervención del Estado",
               "bajar los impuestos y reducir el gasto público y la regulación",
               "favorecer la iniciativa privada y la competencia"),
    ),
    Axis(
        "inmigracion", "Inmigración",
        "inmigración, fronteras, asilo y política migratoria",
        "Acogida", "Control de fronteras",
        left=("acoger a las personas migrantes y refugiadas y abrir vías legales y seguras",
              "garantizar derechos e integración a quienes llegan",
              "una política migratoria humanitaria"),
        right=("controlar las fronteras y reducir la inmigración irregular",
               "endurecer los requisitos migratorios y priorizar la seguridad y el orden",
               "limitar la llegada de inmigrantes"),
    ),
    Axis(
        "aborto", "Aborto",
        "aborto, interrupción voluntaria del embarazo y derechos reproductivos",
        "Derecho a decidir", "Restricción",
        left=("garantizar el derecho al aborto y la autonomía de la mujer sobre su cuerpo",
              "asegurar el acceso público a la interrupción voluntaria del embarazo",
              "ampliar los derechos reproductivos"),
        right=("proteger la vida del no nacido y restringir el aborto",
               "limitar los plazos y reforzar alternativas a la interrupción del embarazo",
               "endurecer los requisitos para abortar"),
    ),
    Axis(
        "territorial", "Modelo territorial",
        "modelo territorial, autonomías, unidad de España, soberanía y autodeterminación",
        "Centralismo", "Autodeterminación",
        left=("reforzar la unidad de España con un Estado fuerte y centralizado",
              "recuperar competencias para el Estado central",
              "rechazar la autodeterminación de las comunidades"),
        right=("ampliar el autogobierno y reconocer el carácter plurinacional del Estado",
               "defender el derecho a decidir y la autodeterminación de los territorios",
               "transferir más competencias a las comunidades"),
    ),
    Axis(
        "medio_ambiente", "Medio ambiente",
        "cambio climático, transición ecológica, energía y medio ambiente",
        "Transición ecológica", "Gradualismo económico",
        left=("acelerar la transición ecológica y reducir drásticamente las emisiones",
              "más renovables y una regulación ambiental ambiciosa aunque tenga coste",
              "tratar la emergencia climática como prioridad"),
        right=("una transición gradual que no penalice la economía ni el empleo",
               "cautela con la regulación ambiental por su coste para la industria y el campo",
               "priorizar la competitividad frente a las exigencias climáticas"),
    ),
    Axis(
        "union_europea", "Unión Europea",
        "Unión Europea, integración europea y soberanía nacional",
        "Más integración", "Soberanía nacional",
        left=("avanzar hacia más integración europea y compartir soberanía en la UE",
              "reforzar las políticas comunes y el papel de la Unión Europea",
              "más unión política y fiscal europea"),
        right=("recuperar soberanía nacional frente a la Unión Europea",
               "rechazar nuevas cesiones de competencias a Bruselas",
               "defender los intereses nacionales frente a la UE"),
    ),
    Axis(
        "seguridad", "Seguridad y libertades",
        "seguridad ciudadana, orden público, derechos civiles y código penal",
        "Garantías civiles", "Orden y seguridad",
        left=("priorizar las garantías y los derechos civiles frente al poder punitivo",
              "apostar por la reinserción y unas penas proporcionadas",
              "limitar los poderes policiales y proteger el derecho de protesta"),
        right=("reforzar la seguridad, el orden público y la autoridad de las fuerzas del orden",
               "endurecer las penas frente a la delincuencia",
               "dotar de más medios y poderes a policía y justicia"),
    ),
    Axis(
        "igualdad_genero", "Igualdad de género",
        "igualdad de género, violencia de género y políticas de igualdad",
        "Políticas de igualdad", "Enfoque crítico",
        left=("impulsar políticas activas de igualdad de género y contra la violencia machista",
              "reconocer la desigualdad estructural entre mujeres y hombres",
              "ampliar los derechos y la perspectiva de género"),
        right=("cuestionar las políticas de género y la legislación sobre violencia de género",
               "defender la igualdad ante la ley sin enfoque de género",
               "rechazar lo que consideran ideología de género"),
    ),
    Axis(
        "memoria", "Memoria histórica",
        "memoria histórica, memoria democrática, franquismo y guerra civil",
        "Memoria democrática", "Reconciliación sin revisión",
        left=("impulsar la memoria democrática y reparar a las víctimas del franquismo",
              "condenar la dictadura y retirar su simbología",
              "verdad, justicia y reparación sobre el pasado"),
        right=("dejar atrás el pasado sin reabrir las heridas de la guerra civil",
               "rechazar las leyes de memoria por considerarlas partidistas",
               "no revisar la historia desde la política"),
    ),
    Axis(
        "vivienda", "Vivienda",
        "vivienda, alquiler, precio de la vivienda y vivienda pública",
        "Regulación pública", "Mercado y oferta",
        left=("regular y limitar el precio de los alquileres",
              "ampliar el parque público de vivienda y proteger a los inquilinos",
              "intervención pública en el mercado de la vivienda"),
        right=("dejar que el mercado fije los precios y estimular la oferta privada",
               "incentivar la construcción en vez de regular los alquileres",
               "menos intervención y más seguridad jurídica para los propietarios"),
    ),
)

AXES_BY_ID: dict[str, Axis] = {a.id: a for a in AXES}


def ejes_json() -> list[dict]:
    """Definición de ejes lista para servir al frontend (mismos ids y etiquetas)."""
    return [
        {"id": a.id, "label": a.label, "subject": a.subject,
         "left_short": a.left_short, "right_short": a.right_short,
         "left_pole": " · ".join(a.left), "right_pole": " · ".join(a.right)}
        for a in AXES
    ]


# ============================================================== modelo compilado

def _unit(v: np.ndarray) -> np.ndarray:
    """Normaliza a norma 1 (estable si el vector es nulo)."""
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


@dataclass
class _AxisModel:
    """Vectores precalculados de un eje: materia, dirección y anclaje de la escala."""
    axis: Axis
    subject_emb: np.ndarray   # consulta temática (unit)
    direction: np.ndarray     # right - left, normalizado (unit)
    mid: float                # proyección del centro entre polos
    half: float               # semirrango entre polos (para mapear a [-1, 1])


@dataclass
class Position:
    """Posición de un grupo en un eje, con su evidencia para justificarla."""
    score: float | None
    n: int
    confidence: str           # 'alta' | 'media' | 'baja' | 'sin_datos'
    evidence: list[dict]      # [{lado, texto, pleno_id, fecha}]

    def as_dict(self) -> dict:
        return {"score": self.score, "n": self.n,
                "confidence": self.confidence, "evidencia": self.evidence}


class PoliticalMap:
    """Calcula posiciones por eje. Constrúyelo UNA vez y reutilízalo entre peticiones."""

    def __init__(self, cfg=None, *, pool: int = 80, min_sim: float = 0.20):
        self.cfg = cfg or load_config()
        pm = getattr(self.cfg, "political_map", None)
        self.pool = int(getattr(pm, "pool", pool))            # nº de fragmentos a traer por par
        self.min_sim = float(getattr(pm, "min_sim", min_sim))  # relevancia temática mínima
        self._embedder = None
        self._col = None
        self._axes: dict[str, _AxisModel] = {}
        self._build_axes()

    # ------------------------------------------------------------ recursos (lazy)
    @property
    def embedder(self):
        if self._embedder is None:
            from .index import get_embedder
            self._embedder = get_embedder(self.cfg)
        return self._embedder

    @property
    def col(self):
        if self._col is None:
            self._col = diarios.get_corpus_collection(self.cfg)
        return self._col

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Embeddings normalizados (mismos ajustes que la ingesta -> espacio comparable)."""
        batch = getattr(getattr(self.cfg, "embeddings", None), "batch_size", 32)
        return np.asarray(self.embedder.encode(
            texts, batch_size=batch, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32)

    # ------------------------------------------------------------ construir ejes
    def _build_axes(self) -> None:
        """Embebe materias y polos de TODOS los ejes en una sola pasada (eficiencia)."""
        texts: list[str] = []
        spans: list[tuple[int, int, int, int]] = []   # (subj, l0, r0, end) por eje
        for a in AXES:
            s = len(texts)
            texts.append(a.subject)
            l0 = len(texts); texts.extend(a.left)
            r0 = len(texts); texts.extend(a.right)
            spans.append((s, l0, r0, len(texts)))

        emb = self._embed(texts)
        for a, (s, l0, r0, end) in zip(AXES, spans):
            subject = emb[s]
            left_c = _unit(emb[l0:r0].mean(axis=0))
            right_c = _unit(emb[r0:end].mean(axis=0))
            direction = _unit(right_c - left_c)
            proj_l = float(left_c @ direction)
            proj_r = float(right_c @ direction)
            self._axes[a.id] = _AxisModel(
                axis=a, subject_emb=subject, direction=direction,
                mid=(proj_r + proj_l) / 2.0, half=max((proj_r - proj_l) / 2.0, 1e-6))

    # ------------------------------------------------------------ una posición
    def score(self, party: str, axis_id: str) -> Position:
        """Posición de un grupo en un eje (proyección anclada a los polos)."""
        m = self._axes[axis_id]
        res = self.col.query(
            query_embeddings=[m.subject_emb.tolist()],
            n_results=self.pool, where={"party": party},
            include=["embeddings", "documents", "metadatas", "distances"])

        # ChromaDB devuelve los embeddings como ndarray; comprobar el vacío con len/size,
        # no con `not` (la verdad de un array de varios elementos es ambigua en numpy).
        raw = res.get("embeddings")
        if raw is None or len(raw) == 0:
            return Position(None, 0, "sin_datos", [])
        embs = np.asarray(raw[0], dtype=np.float32)
        if embs.size == 0:
            return Position(None, 0, "sin_datos", [])
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        sims = 1.0 - np.asarray(res["distances"][0], dtype=np.float32)  # espacio coseno

        keep = sims >= self.min_sim                       # quita fragmentos fuera de tema
        if keep.sum() < 3:
            return Position(None, int(keep.sum()), "sin_datos", [])
        embs, docs, metas, sims = embs[keep], _mask(docs, keep), _mask(metas, keep), sims[keep]

        weights = sims / sims.sum()                       # centroide ponderado por relevancia
        centroid = _unit((embs * weights[:, None]).sum(axis=0))
        proj = float(centroid @ m.direction)
        score = float(np.clip((proj - m.mid) / m.half, -1.0, 1.0))

        n = int(len(docs))
        conf = "alta" if n >= 20 else "media" if n >= 8 else "baja"
        return Position(round(score, 3), n, conf, _evidence(embs, docs, metas, m.direction))

    # ------------------------------------------------------------ texto suelto
    def score_text(self, text: str, axis_id: str) -> float:
        """Proyecta un texto cualquiera sobre un eje. Útil para validar la polaridad."""
        m = self._axes[axis_id]
        c = _unit(self._embed([text])[0])
        proj = float(c @ m.direction)
        return float(np.clip((proj - m.mid) / m.half, -1.0, 1.0))

    # ------------------------------------------------------------ varias posiciones
    def compute(self, parties: list[str], topic_ids: list[str] | None = None) -> dict:
        """{eje: {grupo: {score, n, confidence, evidencia}}} para el frontend."""
        ids = topic_ids or list(AXES_BY_ID)
        return {tid: {p: self.score(p, tid).as_dict() for p in parties} for tid in ids}


# ============================================================== utilidades libres

def _mask(seq: list, keep: np.ndarray) -> list:
    """Aplica una máscara booleana a una lista de Python."""
    return [x for x, k in zip(seq, keep) if k]


def _evidence(embs: np.ndarray, docs: list[str], metas: list[dict],
              direction: np.ndarray, span: int = 240) -> list[dict]:
    """Fragmento más escorado a cada polo: muestra el rango real del discurso del grupo."""
    proj = embs @ direction
    out = []
    for lado, i in (("izq", int(proj.argmin())), ("der", int(proj.argmax()))):
        m = metas[i]
        out.append({"lado": lado, "texto": docs[i][:span].strip(),
                    "pleno_id": m.get("pleno_id", ""), "fecha": m.get("fecha_iso", "")})
    return out


def parties_in_corpus(con=None, top: int = 0) -> list[str]:
    """Grupos realmente presentes en el corpus (para poblar el selector del frontend)."""
    con = con or connect()
    diarios.ensure_schema(con)
    rows = diarios.list_parties(con)
    names = [p for p, _ in rows]
    return names[:top] if top else names


# ====================================================================== CLI

def main() -> None:
    ap = argparse.ArgumentParser(description="Mapa político por ejes temáticos interpretables.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compute", help="posición de uno o varios grupos por eje")
    p.add_argument("parties", nargs="+", help="etiquetas canónicas (p. ej. PSOE PP VOX)")
    p.add_argument("--temas", nargs="*", default=None,
                   help=f"ejes a calcular (por defecto todos: {', '.join(AXES_BY_ID)})")

    sub.add_parser("ejes", help="vuelca la definición de ejes en JSON (para el frontend)")
    sub.add_parser("partidos", help="lista los grupos presentes en el corpus")

    args = ap.parse_args()
    if args.cmd == "ejes":
        print(json.dumps(ejes_json(), ensure_ascii=False, indent=2))
        return
    if args.cmd == "partidos":
        print(json.dumps(parties_in_corpus(), ensure_ascii=False, indent=2))
        return

    pm = PoliticalMap()
    data = pm.compute(args.parties, args.temas)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
