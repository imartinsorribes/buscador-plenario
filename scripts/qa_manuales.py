"""QA RIGUROSO del asistente de Manuales, de punta a punta (ask() completo, con LLM).

Por cada pregunta comprueba 4 cosas:
  1. FUENTE     : el manual esperado está entre las fuentes CITADAS por la respuesta.
  2. CITAS      : todo [n] que aparece en la respuesta existe de verdad en las fuentes.
  3. GROUNDING  : cada frase de la respuesta tiene apoyo en las fuentes citadas
                  (max-sim BGE-M3; aprobado si media>=0.55 y mínimo>=0.42).
  4. HONESTIDAD : la pregunta fuera de tema se rechaza sin inventar.

Uso:  python scripts/qa_manuales.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np

from src.config import load_config
from src.index import get_embedder
from src.manuales import ask

QS = [
    # (pregunta, manual esperado en CITADAS, kwargs)
    ("¿Cómo busco un convenio en SECON?", "Manual_SECON", {}),
    ("¿Cómo doy de alta un convenio nuevo en SECON?", "Manual_SECON", {}),
    ("¿Cómo consulto el estado de una factura en SEFACE?", "Manual_SEFACE", {}),
    ("¿Cómo se accede al Registro General Electrónico SERES?", "ANIMSA_Manual_SERES", {}),
    ("¿Cómo se hace el envío diario en SERES?", "SERES_EnvioDiario", {}),
    ("¿Cómo se trabaja con el SIR en SERES?", "SERES", {}),
    ("¿Cómo se crea un expediente en SEGEX?", "SEGEX", {}),
    ("¿Cómo se planifican las tareas de un expediente en SEGEX?", "SEGEX", {}),
    ("¿Cómo firmo un documento en SEFYCU?", "SEFYCU", {}),
    ("¿Quién debe firmar un SEGRA?", "SEGRA_o_SEGEX_o_Conceptos", {}),
    ("¿Qué es un requisito básico en la fiscalización limitada previa?", "SECOIN", {}),
    ("¿Qué significa la casilla Permite No Procede?", "SECOIN", {}),
    ("¿Cómo se gestionan los reparos y su remisión al Tribunal de Cuentas?", "SECOIN", {}),
    ("¿Cómo funciona la contratación menor con SECA?", "SECA", {}),
    ("¿Y si no tengo certificado digital?", "Cl@ve",
     {"manual": "ANIMSA_Manual_SERES.PDF",
      "history": [{"q": "¿Cómo se accede al Registro General Electrónico SERES?",
                   "a": "Desde Catálogo de Trámites, pulsando Login y autenticándose con certificado."}]}),
    ("¿Cuál es el plazo para presentar la declaración de la renta?", "FUERA_DE_TEMA", {}),
]


def frases(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if len(s.strip()) > 45]


def main():
    cfg = load_config()
    cfg.embeddings.device = "cpu"
    emb = get_embedder(cfg)
    filas, fallos = [], []
    for q, esperado, kw in QS:
        d = ask(q, cfg=cfg, **kw)
        resp = d.get("respuesta", "") or ""
        fts = d.get("fuentes", [])
        citas = sorted({int(x) for x in re.findall(r"\[(\d+)", resp)})
        ns = {f["n"] for f in fts}

        # 4) honestidad para la trampa
        if esperado == "FUERA_DE_TEMA":
            ok = bool(re.search(r"no (hay|consta|se encuentra|existe|contiene|dispon)", resp.lower()))
            filas.append((q, "HONESTA" if ok else "FALLO", "-", "-", "-"))
            if not ok:
                fallos.append((q, "no rechazó el fuera de tema", resp[:150]))
            continue

        # 1) fuente esperada entre las CITADAS (o entre todas si no cita)
        base = [f for f in fts if f["n"] in citas] or fts
        nombres = " | ".join(str(f.get("manual", "video")) for f in base) + \
                  (" | video" if any(f["tipo"] == "video" for f in base) else "")
        alts = esperado.split("_o_")
        fuente_ok = any(a.lower().replace("cl@ve", "") in nombres.lower() for a in alts) or \
                    ("Cl@ve" in esperado and "cl@ve" in resp.lower() and
                     any("segex" in str(f.get("manual", "")).lower() or "conceptos" in str(f.get("manual", "")).lower() for f in base))

        # 2) citas válidas
        citas_ok = all(c in ns for c in citas) and bool(citas)

        # 3) grounding (contra los extractos de las fuentes citadas)
        gr_m = gr_min = None
        try:
            textos = [f["texto"] for f in base if f.get("texto")]
            fr = frases(resp)
            if textos and fr:
                F = emb.encode(textos, normalize_embeddings=True)
                S = emb.encode(fr, normalize_embeddings=True)
                per = (S @ F.T).max(axis=1)
                gr_m, gr_min = float(per.mean()), float(per.min())
        except Exception:
            pass
        gr_ok = gr_m is not None and gr_m >= 0.55 and gr_min >= 0.42

        filas.append((q, "OK" if fuente_ok else "FALLO",
                      "OK" if citas_ok else "FALLO",
                      f"{gr_m:.2f}/{gr_min:.2f}" if gr_m else "n/a",
                      "OK" if gr_ok else "revisar"))
        if not fuente_ok:
            fallos.append((q, f"esperaba {esperado}, citadas: {nombres[:90]}", resp[:120]))
        if not citas_ok:
            fallos.append((q, f"citas {citas} vs fuentes {sorted(ns)}", ""))

    print(f"\n{'pregunta':58} {'fuente':7} {'citas':6} {'ground(med/min)':16} {'g.ok'}")
    for f in filas:
        print(f"{f[0][:56]:58} {f[1]:7} {f[2]:6} {f[3]:16} {f[4]}")
    n = len([f for f in filas if f[1] in ("OK", "HONESTA")])
    print(f"\nFUENTE correcta/honesta: {n}/{len(filas)}")
    nc = len([f for f in filas if f[2] == "OK"])
    print(f"CITAS válidas          : {nc}/{len([f for f in filas if f[2] != '-'])}")
    if fallos:
        print("\n--- FALLOS a revisar ---")
        for q, why, extra in fallos:
            print(f"  · {q[:55]} -> {why}")
            if extra:
                print(f"      resp: {extra}")


if __name__ == "__main__":
    main()
