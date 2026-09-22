"""API del mapa político: sirve la interfaz y expone las posiciones por eje.

Un único servicio: la página (HTML+JS plano) y los endpoints comparten origen, así
que no hace falta build de frontend ni configurar CORS. El modelo pesado se carga
UNA vez, de forma perezosa (en la primera consulta de posiciones), para que el
servidor arranque al instante y la página y los ejes estén disponibles ya.

Arranque:
    uvicorn src.api:app --port 8000        # recomendado
    python -m src.api                      # equivalente (uvicorn embebido)

Endpoints:
    GET /                       -> interfaz
    GET /api/ejes               -> definición de ejes (id, etiquetas, polos)
    GET /api/partidos           -> grupos presentes en el corpus
    GET /api/posiciones?partidos=PSOE,PP,VOX[&temas=economia,aborto]
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .political_map import AXES_BY_ID, PoliticalMap, ejes_json, parties_in_corpus

app = FastAPI(title="Mapa político del Congreso", docs_url="/api/docs", redoc_url=None)

# --- buscador inteligente (recap) expuesto como endpoint para la pestaña Buscar -------------
_SEARCH_CFG = None


@app.get("/api/buscar")
def api_buscar(q: str = Query(..., description="pregunta en lenguaje natural")):
    """Búsqueda semántica del corpus oficial: ficha/fragmentos + respuesta del LLM citando fuentes."""
    global _SEARCH_CFG
    from . import recap
    from .config import load_config
    if _SEARCH_CFG is None:
        _SEARCH_CFG = load_config()
    parsed, rec, resp = recap.ask(q, _SEARCH_CFG)        # con=None -> conexión SQLite por petición
    if "rechazo" in parsed:
        return {"rechazo": True, "mensaje": rec.note}
    return {
        "interpretado": {k: v for k, v in parsed.items() if v},
        "respuesta": resp,
        "fragmentos": [
            {"speaker": h["meta"].get("speaker", ""), "party": h["meta"].get("party", ""),
             "pleno": h["meta"].get("pleno_id", ""), "texto": (h.get("text") or "")[:400]}
            for h in rec.fragments
        ],
    }

# Mismo origen no necesita CORS; se deja abierto solo para desarrollo local
# (p. ej. abrir la página desde un servidor de frontend aparte).
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

_WEB = Path(__file__).resolve().parent / "web" / "index.html"

# El mapa se construye una sola vez y se reutiliza entre peticiones.
_MAP: PoliticalMap | None = None


def get_map() -> PoliticalMap:
    global _MAP
    if _MAP is None:
        _MAP = PoliticalMap()        # carga el embedder y precalcula los ejes
    return _MAP


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _WEB.read_text(encoding="utf-8")


@app.get("/api/ejes")
def api_ejes() -> list[dict]:
    """Definición de ejes; la interfaz la usa para construir sus controles."""
    return ejes_json()


@app.get("/api/partidos")
def api_partidos() -> list[str]:
    """Grupos realmente presentes en el corpus, de más a menos intervenciones."""
    return parties_in_corpus()


@app.get("/api/posiciones")
def api_posiciones(
    partidos: str = Query(..., description="grupos separados por comas"),
    temas: str | None = Query(None, description="ejes separados por comas; por defecto todos"),
) -> dict:
    """Posiciones por eje de los grupos pedidos: {eje: {grupo: {score, n, confidence, evidencia}}}."""
    parties = [p.strip() for p in partidos.split(",") if p.strip()]
    if not parties:
        raise HTTPException(400, "Indica al menos un grupo en 'partidos'.")

    topic_ids = None
    if temas:
        topic_ids = [t.strip() for t in temas.split(",") if t.strip()]
        desconocidos = [t for t in topic_ids if t not in AXES_BY_ID]
        if desconocidos:
            raise HTTPException(400, f"Ejes desconocidos: {', '.join(desconocidos)}")

    return get_map().compute(parties, topic_ids)


def run() -> None:
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
