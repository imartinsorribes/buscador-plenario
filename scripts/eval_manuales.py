"""Evaluación de RECUPERACIÓN del buscador de manuales (hit@k, sin LLM: rápido y gratis).

Para cada pregunta de data/sedipualba/eval_qa.json comprueba si entre las k mejores fuentes
aparece el manual esperado (y, si el set fija páginas verificadas, alguna de esas páginas).
Los manuales GENERADOS cuentan como acierto solo si la pregunta lo permite (por defecto se
evalúa contra fuentes oficiales: texto/captura/vídeo).

Uso:  python scripts/eval_manuales.py [k]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load_config  # noqa: E402
from src.index import get_embedder  # noqa: E402
from src.manuales import _collection  # noqa: E402


def main() -> None:
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    data = json.loads(Path("data/sedipualba/eval_qa.json").read_text(encoding="utf-8"))
    qs = data["preguntas"]
    cfg = load_config()
    cfg.embeddings.device = "cpu"
    emb = get_embedder(cfg)
    col = _collection(cfg)

    hits_manual = hits_page = con_pagina = 0
    for item in qs:
        qv = emb.encode([item["q"]], normalize_embeddings=True)[0].tolist()
        res = col.query(query_embeddings=[qv], n_results=k)
        metas = res["metadatas"][0]
        ok_m = ok_p = False
        for m in metas:
            if m.get("generado"):
                continue                              # se evalúa contra las fuentes oficiales
            manual_ok = item["manual"].lower() in str(m.get("manual", "")).lower()
            tipo_ok = m.get("tipo") in item.get("tipo_ok", ["texto", "captura", "video"])
            if manual_ok and tipo_ok:
                ok_m = True
                if "pages" in item and m.get("page") in item["pages"]:
                    ok_p = True
        hits_manual += ok_m
        if "pages" in item:
            con_pagina += 1
            hits_page += ok_p
        top = metas[0]
        print(f"  {'OK ' if ok_m else 'MAL'}  {item['q'][:58]:58} top: "
              f"{str(top.get('manual', top.get('title','')))[:28]} p.{top.get('page', top.get('start',''))}")
    print(f"\nhit@{k} por MANUAL correcto : {hits_manual}/{len(qs)} = {hits_manual/len(qs):.0%}")
    if con_pagina:
        print(f"hit@{k} con PÁGINA exacta  : {hits_page}/{con_pagina} = {hits_page/con_pagina:.0%} "
              f"(solo en las {con_pagina} preguntas con página verificada)")


if __name__ == "__main__":
    main()
