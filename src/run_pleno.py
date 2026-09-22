"""Pipeline de PRODUCCIÓN (a ciegas) de un pleno — un solo comando para el operador:

    fuente (archivo o URL) -> descarga -> transcribe -> diariza -> nombra (roster) -> acta + BD

NO usa Diario oficial (eso es la vía de calibración, en src/pipeline.py). El etiquetado por
voz y la confirmación humana se hacen DESPUÉS en la UI (Bloque D), que reutiliza las huellas
de voz locales. Esto deja el pleno listo para revisar.

Uso:
    python -m src.run_pleno data/raw_audio/<id>.m4a --entidad-slug albacete \
        --entidad "Ayuntamiento de Albacete" --fecha "29 de enero de 2026" \
        --roster data/roster_albacete.json --video-id mTjTqGIWAGs
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from . import db
from .config import load_config, resolve_path


def _find_glosario(slug: str) -> str | None:
    """Busca el glosario del municipio. Acepta slug corto ('chiva') o largo
    ('ayuntamiento-de-chiva'): casa terms_<clave>.txt si <clave> aparece en el slug."""
    refdir = resolve_path("data/ref")
    exact = refdir / f"terms_{slug}.txt"
    if exact.exists():
        return str(exact)
    for f in sorted(refdir.glob("terms_*.txt")):
        key = f.stem[len("terms_"):]
        if key and key in slug:
            return str(f)
    return None


def run(source: str, entidad_slug: str, entidad_nombre: str = "", titulo: str = "",
        fecha: str = "", roster_path: str | None = None, video_id: str | None = None,
        tipo: str = "ayuntamiento", glosario: str | None = None, lang: str | None = None,
        orden: str | None = None, guess_names: bool = False) -> str:
    import sys
    from .acta import build_acta
    from .lexfix import correct_segments, load_terms_file
    from .transcribe import transcribe

    cfg = load_config()
    # El initial_prompt del Congreso (config) ENVENENA la transcripción municipal: está
    # comprobado que hace que Whisper se SALTE texto en tramos de habla rápida (p.ej. min 2:01
    # de Chiva). En el pipeline a ciegas (municipal) lo desactivamos; los términos locales ya
    # los arregla lexfix con el glosario del ayuntamiento.
    cfg.asr.initial_prompt = ""
    if lang:                       # 'auto' -> detección de idioma por fragmento (plenos bilingües)
        cfg.asr.language = lang
    raw = resolve_path(cfg.paths.raw_audio)
    trd = resolve_path(cfg.paths.transcripts)

    src = Path(source)
    if src.exists():                                   # archivo local (ya descargado)
        audio, vid = str(src.resolve()), (video_id or src.stem)
    else:                                              # URL -> descarga (yt-dlp)
        from .download import download_audio
        meta = download_audio(source, raw)
        audio, vid = meta["audio_path"], (video_id or meta["id"])
    stem = Path(audio).stem
    print(f"[1/5] audio: {audio}  (id={vid})", flush=True)
    dur = (meta.get("duration") if not src.exists() else None)
    if not dur:
        try:
            dur = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", audio], text=True).strip())
        except Exception:
            dur = None
    if dur:
        print(f"[dur] {int(dur)}", flush=True)          # -> la UI estima el tiempo de transcripción

    transcribe(audio, cfg, trd)
    tr_path = trd / f"{stem}.json"
    print("[2/5] transcrito", flush=True)

    # corrección léxica: arregla términos LOCALES que el ASR transcribe mal de forma
    # inconsistente (p.ej. mancomunidad -> "bancomunidad"/"humana comunidad"), contra el
    # glosario del municipio. Probado: ningún ajuste de Whisper lo fija; esto sí, y es seguro.
    glos_path = glosario or _find_glosario(entidad_slug)
    terms = load_terms_file(glos_path) if glos_path else []
    if terms:
        data = json.loads(tr_path.read_text(encoding="utf-8"))
        _, changes = correct_segments(data["segments"], terms)
        if changes:
            tr_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[lex] {len(changes)} término(s) local(es) corregido(s) con el glosario", flush=True)

    wav = raw / f"{stem}.wav"
    if not wav.exists():
        subprocess.run(["ffmpeg", "-y", "-i", audio, "-ar", "16000", "-ac", "1", str(wav)],
                       check=True, capture_output=True)
    # diarize + naming en SUBPROCESOS: el cuDNN de CTranslate2 (Whisper) y el de torch (pyannote)
    # chocan en un mismo proceso ("Could not load symbol cudnnGetLibConfig") -> los aislamos.
    subprocess.run([sys.executable, "-m", "src.diarize", str(tr_path), str(wav),
                    "--entidad", entidad_slug], check=True)
    print("[3/5] diarizado", flush=True)
    # NOMBRES: por defecto NO se adivina nada (sin regex/NER de anuncios). Cada voz queda como
    # "Voz N"; el nombre lo pone el humano en el editor o lo sugiere una HUELLA registrada antes.
    # Adivinar el nombre del anuncio se equivocaba (Madrid: "Maestra" por "Maestre") y un nombre
    # mal en un acta oficial es peor que "Voz N". Solo se reactiva con --guess-names (investigación).
    if guess_names:
        cmd = [sys.executable, "-m", "src.speakers", str(tr_path)]
        if roster_path:
            cmd += ["--roster", roster_path]
        subprocess.run(cmd, check=True)
        print("[4/5] nombrado (roster + anuncios)", flush=True)
    else:
        print("[4/5] voces sin nombre (Voz N) — el nombre se pone a mano o por huella registrada", flush=True)

    con = db.connect()
    eid = db.upsert_entidad(con, entidad_slug, entidad_nombre or entidad_slug, tipo)
    nseg = len(json.loads(tr_path.read_text(encoding="utf-8"))["segments"])
    db.register_pleno(con, eid, vid, titulo=titulo, fecha=fecha,
                      video_url=("" if src.exists() else source), n_segmentos=nseg)
    con.close()
    od = None
    if orden and Path(orden).exists():                 # orden del día oficial (convocatoria) aportado
        od = [ln.strip() for ln in Path(orden).read_text(encoding="utf-8").splitlines()
              if ln.strip() and not ln.startswith("#")]
    try:                                               # escudo del municipio (membrete) si aún no está
        from .escudo import ensure_escudo
        if ensure_escudo(entidad_slug, entidad_nombre or entidad_slug):
            print("[escudo] descargado de Wikimedia Commons", flush=True)
    except Exception:
        pass
    build_acta(str(tr_path), video_id=vid, orden_del_dia=od)
    print("[5/5] acta lista · revisa/etiqueta las voces en la UI (Bloque D)", flush=True)
    return vid


def main() -> None:
    ap = argparse.ArgumentParser(description="Pipeline de producción de un pleno (a ciegas) -> acta.")
    ap.add_argument("source", help="archivo de audio/vídeo local o URL de YouTube")
    ap.add_argument("--entidad-slug", required=True, help="slug de la entidad (p.ej. albacete)")
    ap.add_argument("--entidad", default="", help="nombre de la entidad (Ayuntamiento de…)")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--fecha", default="")
    ap.add_argument("--roster", default=None, help="JSON con el roster (concejales)")
    ap.add_argument("--video-id", default=None)
    ap.add_argument("--glosario", default=None,
                    help="TXT de términos locales (por defecto data/ref/terms_<slug>.txt)")
    ap.add_argument("--lang", default=None,
                    help="idioma ASR: 'auto' = detección por fragmento (plenos bilingües), o 'es'/'ca'…")
    ap.add_argument("--orden", default=None,
                    help="TXT con el orden del día oficial (un punto por línea) -> títulos exactos")
    ap.add_argument("--guess-names", action="store_true",
                    help="(investigación) adivinar nombres por anuncios/NER; por defecto NO se adivina")
    a = ap.parse_args()
    run(a.source, a.entidad_slug, a.entidad, a.titulo, a.fecha, a.roster, a.video_id,
        glosario=a.glosario, lang=a.lang, orden=a.orden, guess_names=a.guess_names)


if __name__ == "__main__":
    main()
