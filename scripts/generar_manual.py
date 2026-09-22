"""VÍDEO → MANUAL ilustrado, con control de duplicados: solo redacta lo que NO esté ya en un
manual existente (idea del equipo: "crear manuales a partir de vídeos si no existe ya uno").

Flujo (todo automático, idempotente):
  1. descarga el audio y el vídeo (480p) del tutorial de YouTube (si no están ya),
  2. transcribe con timestamps (Bloque A),
  3. trocea en CAPÍTULOS por cambio semántico (BGE-M3),
  4. COMPRUEBA cada capítulo contra los manuales ya indexados:
       - cubierto (sim>=0.65)  -> NO se redacta: se remite al manual oficial (manual, página),
       - no cubierto           -> lo redacta el LLM (gemini-flash) citando su tramo del vídeo,
  5. inserta el fotograma del punto medio de cada capítulo,
  6. genera docs/manual_<id>.md + .pdf.

Uso:
  python scripts/generar_manual.py https://www.youtube.com/watch?v=XXXX --titulo "Módulo X"
  python scripts/generar_manual.py XXXX --force      # redactar TODO aunque esté cubierto
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.bakeoff_llm import _load_env, _openrouter  # noqa: E402
from scripts.video_a_manual import _SECCION, _chapters, _mmss, _windows  # noqa: E402
from src.config import load_config  # noqa: E402
from src.index import get_embedder  # noqa: E402

BASE = Path("data/sedipualba")
PY = sys.executable
THR_CUBIERTO = 0.65


def _vid_of(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", s)
    return m.group(1) if m else s.strip()


def _ensure_media(vid: str) -> tuple[Path, Path]:
    """Audio wav 16k + vídeo 480p en local (descarga solo lo que falte)."""
    url = f"https://www.youtube.com/watch?v={vid}"
    (BASE / "videos").mkdir(parents=True, exist_ok=True)
    wav = BASE / "videos" / f"{vid}.wav"
    if not wav.exists():
        raw = BASE / "videos" / f"{vid}_a.webm"
        subprocess.run([PY, "-m", "yt_dlp", "--remote-components", "ejs:github", "-q",
                        "-f", "bestaudio", "-o", str(raw), url], check=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(raw), "-ar", "16000", "-ac", "1", str(wav)],
                       check=True, capture_output=True)
        raw.unlink(missing_ok=True)
    video = next(iter((BASE / "videos").glob(f"{vid}_v.*")), None)
    if video is None:
        subprocess.run([PY, "-m", "yt_dlp", "--remote-components", "ejs:github", "-q",
                        "-f", "bestvideo[height<=480][ext=mp4]/bestvideo[height<=480]/best[height<=480]",
                        "-o", str(BASE / "videos" / f"{vid}_v.%(ext)s"), url], check=True)
        video = next(iter((BASE / "videos").glob(f"{vid}_v.*")))
    return wav, video


def _ensure_transcript(vid: str, wav: Path) -> Path:
    tr = BASE / "transcripts" / f"{vid}.json"
    # reutiliza el transcript del pipeline previo si ya existía con otro nombre (p. ej. secoin)
    if not tr.exists():
        cfg = load_config()
        cfg.asr.initial_prompt = ""
        cfg.asr.language = "es"
        from src.transcribe import transcribe
        out = transcribe(str(wav), cfg, str(BASE / "transcripts"))  # escribe <stem>.json
        Path(BASE / "transcripts" / f"{wav.stem}.json").rename(tr)
    return tr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="URL de YouTube o id del vídeo")
    ap.add_argument("--titulo", default="", help="título del manual generado")
    ap.add_argument("--force", action="store_true", help="redactar también lo ya cubierto")
    ap.add_argument("--transcript", default=None, help="usar un transcript ya existente (ruta)")
    ap.add_argument("--solo-indexar", action="store_true",
                    help="NO redactar manual: transcribir e indexar el vídeo por minutos "
                         "(el asistente enlazará el momento exacto para quien quiera verlo)")
    a = ap.parse_args()
    _load_env()
    vid = _vid_of(a.video)

    print("[1/4] descargando audio y vídeo…", flush=True)
    wav, video = _ensure_media(vid)
    print("[2/4] transcribiendo…", flush=True)
    tr = Path(a.transcript) if a.transcript else _ensure_transcript(vid, wav)
    if a.solo_indexar:
        if a.titulo.strip():
            (BASE / "transcripts" / f"{vid}.title.txt").write_text(a.titulo.strip(), encoding="utf-8")
        print("[3/4] indexando el vídeo por minutos…", flush=True)
        from src.manuales import ingest
        r = ingest()
        print(f"[4/4] listo · id={vid} · índice con {r.get('indexados', 0)} fragmentos", flush=True)
        return
    print("[3/4] capítulos y cobertura…", flush=True)
    segs = json.loads(tr.read_text(encoding="utf-8"))["segments"]
    # corrección léxica del dominio (nombres de módulo verificados + alias de errores conocidos
    # del ASR: 'SEGES=SEGEX', 'seficu'->SEFYCU...). Multipalabra fonético DESACTIVADO (thr>1):
    # con siglas cortas arrasa frases comunes ('se hace'->SEFACE). Solo 1 palabra + alias exactos.
    gl = BASE / "terms_sedipualba.txt"
    if gl.exists():
        from src.lexfix import correct_segments, load_aliases, load_terms_file
        _, ch = correct_segments(segs, load_terms_file(gl), thr_multi=1.1, aliases=load_aliases(gl))
        if ch:
            print(f"[lex] {len(ch)} términos de módulo corregidos en la transcripción")
    wins = _windows(segs)

    cfg = load_config()
    cfg.embeddings.device = "cpu"                        # no pelear por la GPU con el server
    emb = get_embedder(cfg)
    chaps = _chapters(wins, emb)
    print(f"{len(wins)} ventanas -> {len(chaps)} capítulos")

    # corpus de manuales EXISTENTES (texto + capturas; ni el vídeo ni los manuales GENERADOS
    # cuentan para la barrera — se compara solo contra documentación oficial).
    # Los embeddings se LEEN de ChromaDB (ya calculados en el ingest): ~10 min -> segundos.
    import numpy as np
    from src.manuales import _collection, _fragments
    metas, F = [], None
    try:
        col = _collection(cfg)
        res = col.get(where={"tipo": {"$in": ["texto", "captura"]}},
                      include=["embeddings", "metadatas"])
        pairs = [(m, e) for m, e in zip(res["metadatas"], res["embeddings"])
                 if not m.get("generado")]
        if pairs:
            metas = [m for m, _ in pairs]
            F = np.asarray([e for _, e in pairs], dtype=np.float32)
            print(f"[cov] {len(metas)} embeddings del corpus leídos de ChromaDB (sin recalcular)")
    except Exception as e:
        print(f"[cov] índice no disponible ({str(e)[:60]}) -> codifico el corpus (lento)")
    if F is None:                                # respaldo: sin índice, comportamiento antiguo
        frags = [f for f in _fragments() if f["meta"]["tipo"] in ("texto", "captura")]
        metas = [f["meta"] for f in frags]
        F = emb.encode([f["text"] for f in frags], normalize_embeddings=True, batch_size=8)

    # fotogramas del punto medio
    fdir = BASE / "frames" / vid
    fdir.mkdir(parents=True, exist_ok=True)

    # --- LA BARRERA (a nivel de VÍDEO): si ya existe manual que cubre el contenido, NO se crea ---
    cover = []                                   # por capítulo: (sim, meta del mejor manual)
    for x, y in chaps:
        text = " ".join(w["text"] for w in wins[x:y])[:2000]
        v = emb.encode([text], normalize_embeddings=True)[0]
        sims = F @ v
        j = int(sims.argmax())
        cover.append((float(sims[j]), metas[j]))
    n_cub = sum(1 for s, _ in cover if s >= THR_CUBIERTO)
    frac = n_cub / max(len(chaps), 1)
    print(f"cobertura por manuales existentes: {n_cub}/{len(chaps)} capítulos ({frac:.0%})")
    if frac >= 0.6 and not a.force:
        top = {}
        for s, m in cover:
            if s >= THR_CUBIERTO:
                top[m["manual"]] = top.get(m["manual"], 0) + 1
        print("\nYA EXISTE manual para este contenido -> NO se genera (esa es la barrera).")
        print("Manuales que lo cubren:", ", ".join(f"{k} ({v} caps)" for k, v in top.items()))
        print("(usa --force para generarlo igualmente)")
        return

    print("[4/4] redactando el manual…", flush=True)
    titulo = a.titulo or f"Manual generado del vídeo {vid}"
    out = [f"# {titulo}", "",
           f"Documento generado automáticamente del vídeo https://youtu.be/{vid}. "
           f"Los apartados ya documentados oficialmente se remiten a su manual (no se duplican); "
           f"el resto se redacta desde el vídeo citando el tramo exacto.", ""]
    generados = remitidos = 0
    for k, (x, y) in enumerate(chaps, 1):
        text = " ".join(w["text"] for w in wins[x:y])
        t0, t1 = wins[x]["start"], wins[y - 1]["end"]
        s, m = cover[k - 1]

        frame = fdir / f"cap{k:02d}.png"
        if not frame.exists():
            subprocess.run(["ffmpeg", "-y", "-ss", str(int((t0 + t1) / 2)), "-i", str(video),
                            "-frames:v", "1", str(frame)], capture_output=True)
            # (la censura de caras existe en scripts/censurar_caras.py pero NO está activada:
            #  al usuario no le convenció el resultado — aplicar a mano solo si hace falta)

        if s >= THR_CUBIERTO and not a.force:            # YA documentado -> remitir, no duplicar
            out.append(f"## Capítulo {k} — ya documentado oficialmente\n")
            out.append(f"Este apartado está cubierto por **{m['manual']}, pág. {m['page']}** "
                       f"(coincidencia {s:.2f}). Vídeo: min {_mmss(t0)}–{_mmss(t1)} "
                       f"(https://youtu.be/{vid}?t={int(t0)}).")
            remitidos += 1
            print(f"  [{k}] {_mmss(t0)}-{_mmss(t1)}  REMITIDO -> {m['manual']} p.{m['page']} ({s:.2f})")
        else:                                            # hueco real -> redactar del vídeo
            try:
                md = _openrouter("or:google/gemini-3.5-flash", _SECCION.format(text=text[:7000]), timeout=90)
            except Exception as e:
                print(f"  [{k}] fallo LLM: {str(e)[:60]}")
                continue
            if not md.strip().startswith("#"):
                md = f"## Sección {k}\n\n" + md
            if frame.exists():
                md += f"\n\n![captura]({frame.as_posix()})"
            md += (f"\n\n*Fuente: vídeo, min {_mmss(t0)}–{_mmss(t1)} — "
                   f"https://youtu.be/{vid}?t={int(t0)}*")
            out.append(md)
            generados += 1
            print(f"  [{k}] {_mmss(t0)}-{_mmss(t1)}  GENERADO ({s:.2f} vs manuales)")
        out.append("")

    dest = Path(f"docs/manual_{vid}.md")
    dest.write_text("\n".join(out), encoding="utf-8")
    subprocess.run([PY, "scripts/md_to_pdf.py", f"docs/manual_{vid}.pdf", str(dest)], check=True)
    print(f"\n{generados} capítulos redactados · {remitidos} remitidos a manuales existentes")
    print(f"-> docs/manual_{vid}.md + docs/manual_{vid}.pdf")


if __name__ == "__main__":
    main()
