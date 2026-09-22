"""Identificación de locutor por VOZ (biometría) — Bloque B para municipios SIN Diario.

Donde no hay Diario ni anuncios formales ("tiene la palabra X"), identificamos a cada orador
por su HUELLA DE VOZ: cada persona se registra UNA vez (unos segundos de audio) y después, en
cualquier pleno, comparamos la voz de cada turno diarizado con las registradas.

- Embedding de locutor: ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb), vector de 192-d.
- La diarización (pyannote) ya AGRUPA las voces (SPEAKER_00, _01…); aquí solo PONEMOS NOMBRE
  a cada cluster comparando su huella con las registradas (coseno).

Pipeline:
  enroll(audio, [(start,end)…])           -> voiceprint (registro de una persona)
  cluster_voiceprints(audio, segments)    -> {SPEAKER_xx: voiceprint} (huella por cluster)
  identify(clusters, enrolled, thr)        -> {SPEAKER_xx: (nombre, similitud)}
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import resolve_path

_SR = 16000
_enc = None
_wav_cache: dict[str, object] = {}

# Etiquetas AUTOMÁTICAS (no son un nombre real): "Voz 1", "Nueva voz 3", "(sin identificar)"…
# NUNCA se guarda una huella con estos nombres -> significa que NADIE identificó esa voz.
import re as _re

_AUTO_NAME_RE = _re.compile(r"^(voz|nueva voz)\s*\d*$", _re.IGNORECASE)


def _is_auto_name(name: str) -> bool:
    n = (name or "").strip()
    return (not n) or bool(_AUTO_NAME_RE.match(n)) or n.lower() in (
        "(sin identificar)", "(sin confirmar)", "sin identificar", "presidencia")


def _encoder():
    global _enc
    if _enc is None:
        import os
        import os.path as op
        import shutil

        import torch
        from huggingface_hub import snapshot_download
        from speechbrain.inference.speaker import EncoderClassifier

        # Windows bloquea symlinks (WinError 1314) y speechbrain los usa al recolectar el
        # modelo -> parcheamos os.symlink para COPIAR en vez de enlazar mientras carga.
        _orig = os.symlink

        def _sym_or_copy(src, dst, *a, **k):
            try:
                _orig(src, dst, *a, **k)
            except OSError:
                s = src if op.isabs(str(src)) else op.join(op.dirname(str(dst)), str(src))
                if op.abspath(s) != op.abspath(str(dst)):
                    shutil.copy(s, dst)

        os.symlink = _sym_or_copy
        try:
            local = snapshot_download(repo_id="speechbrain/spkrec-ecapa-voxceleb")
            _enc = EncoderClassifier.from_hparams(
                source=local, savedir=local,
                run_opts={"device": "cuda:0" if torch.cuda.is_available() else "cpu"},
            )
        finally:
            os.symlink = _orig
    return _enc


def _load_audio(path):
    """Carga el audio a mono 16 kHz (cacheado por ruta)."""
    import torchaudio
    key = str(path)
    if key not in _wav_cache:
        wav, sr = torchaudio.load(key)
        if wav.shape[0] > 1:
            wav = wav.mean(0, keepdim=True)
        if sr != _SR:
            wav = torchaudio.functional.resample(wav, sr, _SR)
        _wav_cache[key] = wav
    return _wav_cache[key]


def _embed_spans(wav, spans, max_secs: float = 30.0):
    """Embedding L2-normalizado del audio de varios tramos [start,end] (segundos), priorizando
    los tramos más largos hasta `max_secs` (suficiente para una huella estable)."""
    import torch
    chunks, total = [], 0.0
    for st, en in sorted(spans, key=lambda x: -(x[1] - x[0])):
        if total >= max_secs:
            break
        a, b = int(st * _SR), int(en * _SR)
        seg = wav[:, a:b]
        if seg.shape[1] < int(_SR * 0.5):        # descarta tramos < 0.5 s
            continue
        chunks.append(seg)
        total += (en - st)
    if not chunks:
        return None
    audio = torch.cat(chunks, dim=1)
    with torch.no_grad():
        emb = _encoder().encode_batch(audio).squeeze().cpu().numpy()
    return emb / (np.linalg.norm(emb) + 1e-9)


def enroll(audio_path, spans, max_secs: float = 30.0):
    """Registra a una persona: huella de voz a partir de sus tramos de audio."""
    return _embed_spans(_load_audio(audio_path), spans, max_secs)


def _spans_by_speaker(segments):
    """Tramos por orador, SIN los marcados como cruce (overlap). Respaldo: si una voz solo
    aparece en cruces, se usan todos sus tramos (mejor algo que nada)."""
    clean, allsp = defaultdict(list), defaultdict(list)
    for s in segments:
        spk = s.get("speaker")
        if spk and s.get("end", 0) > s.get("start", 0):
            allsp[spk].append((s["start"], s["end"]))
            if not s.get("overlap"):
                clean[spk].append((s["start"], s["end"]))
    return {spk: (clean.get(spk) or allsp[spk]) for spk in allsp}


def cluster_voiceprints(audio_path, segments, max_secs: float = 30.0) -> dict:
    """Huella de voz de cada cluster de diarización (campo 'speaker') del pleno."""
    wav = _load_audio(audio_path)
    return {spk: _embed_spans(wav, spans, max_secs) for spk, spans in _spans_by_speaker(segments).items()}


def identify(clusters: dict, enrolled: dict, thr: float = 0.5) -> dict:
    """Empareja cada cluster con la persona registrada más parecida (coseno >= thr)."""
    names = [n for n, v in enrolled.items() if v is not None]
    E = np.array([enrolled[n] for n in names]) if names else np.zeros((0, 192))
    out = {}
    for spk, v in clusters.items():
        if v is None or not names:
            out[spk] = ("(desconocido)", 0.0)
            continue
        sims = E @ v
        j = int(np.argmax(sims))
        out[spk] = (names[j], float(sims[j])) if sims[j] >= thr else ("(desconocido)", float(sims[j]))
    return out


# ---------------------------------------------------------------- huellas LOCALES por entidad
def _vp_path(entidad: str) -> Path:
    p = resolve_path(f"data/voiceprints/{entidad}.json")     # se queda en el equipo del ayto.
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_voiceprints(entidad: str) -> dict:
    p = _vp_path(entidad)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_voiceprints(entidad: str, vps: dict) -> None:
    _vp_path(entidad).write_text(json.dumps(vps, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------- multi-vector (varias huellas/persona)
# Cuanta más información tengamos de una persona, mejor: en vez de UNA huella promedio guardamos
# VARIAS (exemplars) que cubren su variabilidad (tono tranquilo / enfadado / micro distinto). Se
# empareja por el MEJOR exemplar -> reconoce más casos sin bajar el umbral ni inventar nombres.
_K = 8  # nº máx. de huellas por persona (se acumulan entre plenos; al pasar de K se FUSIONAN
        # las dos más parecidas, no se descarta audio -> se conserva la diversidad)


def _embed_exemplars(wav, spans, per_secs: float = 12.0, k: int = _K, max_secs: float = 30.0):
    """Varias huellas de una misma persona: agrupa sus tramos en bloques de ~per_secs y saca un
    vector por bloque (hasta k). Si solo hay un trozo corto, devuelve una sola huella."""
    vecs, bucket, tot = [], [], 0.0
    for st, en in sorted(spans, key=lambda x: -(x[1] - x[0])):
        if en - st < 0.5:
            continue
        bucket.append((st, en))
        tot += en - st
        if tot >= per_secs:
            v = _embed_spans(wav, bucket, max_secs)
            if v is not None:
                vecs.append(v)
            bucket, tot = [], 0.0
            if len(vecs) >= k:
                break
    if bucket and len(vecs) < k:
        v = _embed_spans(wav, bucket, max_secs)
        if v is not None:
            vecs.append(v)
    return vecs


def _vecs_of(entry: dict):
    """Huellas de una persona como lista de vectores (compatible con el formato antiguo {'vec'})."""
    if entry.get("vecs"):
        return [np.asarray(x, dtype=np.float32) for x in entry["vecs"]]
    if "vec" in entry:
        return [np.asarray(entry["vec"], dtype=np.float32)]
    return []


def _cap(vecs, k: int = _K):
    """Limita a k huellas fusionando (media) las dos más parecidas -> conserva la diversidad."""
    vecs = [np.asarray(v, dtype=np.float32) for v in vecs]
    while len(vecs) > k:
        best = (-2.0, 0, 1)
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                s = float(vecs[i] @ vecs[j])
                if s > best[0]:
                    best = (s, i, j)
        _, i, j = best
        m = vecs[i] + vecs[j]
        vecs = [v for t, v in enumerate(vecs) if t not in (i, j)] + [m / (np.linalg.norm(m) + 1e-9)]
    return vecs


def _match(v, mats):
    """Mejor persona para la huella v: MÁXIMO coseno sobre todos sus exemplars.
    `mats`: lista (por persona) de matriz (n_exemplars x 192). Devuelve (idx, sim1, sim2)."""
    per = [float(np.max(M @ v)) if len(M) else -1.0 for M in mats]
    order = np.argsort(per)[::-1]
    j = int(order[0])
    s2 = float(per[order[1]]) if len(order) > 1 else 0.0
    return j, float(per[j]), s2


def enroll_clusters(audio_path, segments, cluster_labels: dict, entidad: str, per_secs: float = 12.0) -> int:
    """Tras etiquetar un pleno, guarda/ACUMULA las huellas locales de cada voz nombrada (consentido).
    cluster_labels: {cluster: {'name','party','chair'?}}. Añade las nuevas huellas a las previas
    (multi-vector) y cuenta en cuántos plenos ha aparecido la persona (`n`)."""
    wav = _load_audio(audio_path)
    byc = _spans_by_speaker(segments)          # sin tramos con cruce (overlap)
    vps = load_voiceprints(entidad)
    n = 0
    for spk, spans in byc.items():
        lab = cluster_labels.get(spk) or {}
        nm = (lab.get("name") or "").strip()
        if not nm or lab.get("chair") or _is_auto_name(nm):   # nunca huellas de "Voz N" / sin nombre
            continue
        new = _embed_exemplars(wav, spans, per_secs)
        if not new:
            continue
        vecs = _cap(_vecs_of(vps.get(nm, {})) + new)         # ACUMULA entre sesiones
        vps[nm] = {
            "vecs": [v.tolist() for v in vecs],
            "n": int(vps.get(nm, {}).get("n", 0)) + 1,
            "party": (lab.get("party") or vps.get(nm, {}).get("party", "") or ""),
        }
        n += 1
    save_voiceprints(entidad, vps)
    return n


def _cluster_vp_cached(audio_path, segments) -> dict:
    """Huellas por cluster del pleno, CACHEADAS en disco (calcular ECAPA sobre el audio es lo
    lento). Solo se recalcula si cambia la diarización (firma de speakers+tiempos+cruce)."""
    import hashlib
    stem = Path(audio_path).stem
    cache = resolve_path(f"data/voiceprints/_cache/{stem}.json")
    sig = hashlib.md5("".join(f"{s.get('speaker','')}|{int(s.get('start',0))}|{1 if s.get('overlap') else 0};"
                              for s in segments).encode()).hexdigest()[:16]
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("sig") == sig:
                return {k: (np.asarray(v, dtype=np.float32) if v is not None else None)
                        for k, v in d["vp"].items()}
        except Exception:
            pass
    vp = cluster_voiceprints(audio_path, segments)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"sig": sig, "vp": {k: (v.tolist() if v is not None else None)
                                                        for k, v in vp.items()}}, ensure_ascii=False),
                         encoding="utf-8")
    except Exception:
        pass
    return vp


def supervised_assign(audio_path, segments, entidad: str, thr: float = 0.55,
                      margin: float = 0.05, min_dur: float = 2.5) -> int:
    """Asignación SUPERVISADA por huella registrada: usa las voces del registro del municipio
    para CORREGIR el clustering ciego (no solo para nombrarlo). Conservador por diseño:

      - Ignora los tramos con CRUCE (voz mezclada físicamente: su huella no es de nadie) y los
        cortos (<min_dur, huella inestable).
      - Un tramo solo se asigna si supera el umbral Y hay margen claro sobre la 2ª persona
        (open-set: ante la duda, se queda como estaba — nunca puede empeorar el clustering).
      - Voto por cluster: si ≥80 % de lo que casó en un cluster es de UNA persona, todo el
        cluster pasa a esa persona (evita fragmentar). Si el cluster está repartido entre dos
        personas registradas (pyannote los juntó), se parte tramo a tramo por su huella.

    Reasigna seg['speaker'] a 'REG::<nombre>' y fija name/party. Devuelve nº de tramos asignados."""
    vps = load_voiceprints(entidad)
    names = [n for n in vps if _vecs_of(vps[n])]
    if not names or not segments:
        return 0
    mats = [np.array(_vecs_of(vps[n])) for n in names]
    wav = _load_audio(audio_path)

    # pasada 1: match por TRAMO (solo limpios y largos)
    seg_hit: dict[int, str] = {}                  # idx segmento -> persona
    by_cluster: dict[str, list[int]] = {}
    for i, s in enumerate(segments):
        sp = s.get("speaker")
        if sp:
            by_cluster.setdefault(sp, []).append(i)
        if s.get("overlap") or (s.get("end", 0) - s.get("start", 0)) < min_dur:
            continue
        v = _embed_spans(wav, [(s["start"], s["end"])])
        if v is None:
            continue
        j, s1, s2 = _match(v, mats)
        if s1 >= thr and (s1 - s2) >= margin:
            seg_hit[i] = names[j]

    # pasada 2: voto por cluster (dominante ≥80 % -> todo el cluster; repartido -> tramo a tramo)
    assigned = 0
    for sp, idxs in by_cluster.items():
        durs: dict[str, float] = {}
        for i in idxs:
            if i in seg_hit:
                s = segments[i]
                durs[seg_hit[i]] = durs.get(seg_hit[i], 0.0) + (s["end"] - s["start"])
        if not durs:
            continue                               # nadie registrado en este cluster: intacto
        total = sum(durs.values())
        top = max(durs, key=durs.get)
        whole = durs[top] / total >= 0.80          # una sola persona domina lo casado
        for i in idxs:
            person = top if whole else seg_hit.get(i)
            if person is None:
                continue                           # cluster mixto: solo tramos con huella clara
            s = segments[i]
            s["speaker"] = f"REG::{person}"
            s["name"] = person
            s["party"] = vps[person].get("party", "") or ""
            assigned += 1
    return assigned


def suggest_from_voiceprints(audio_path, segments, entidad: str, thr: float = 0.55,
                             margin: float = 0.05) -> dict:
    """Pleno NUEVO: empareja cada cluster con las huellas guardadas del ayto. -> auto-sugerencia.
    {cluster: {'name','party','sim','n'}}. Solo sugiere si supera el umbral Y hay margen claro
    sobre la 2ª persona (evita confundir voces parecidas). Vacío si aún no hay huellas."""
    vps = load_voiceprints(entidad)
    names = [n for n in vps if _vecs_of(vps[n])]
    if not names:
        return {}
    mats = [np.array(_vecs_of(vps[n])) for n in names]
    out = {}
    for spk, v in _cluster_vp_cached(audio_path, segments).items():
        if v is None:
            continue
        j, s1, s2 = _match(v, mats)
        if s1 >= thr and (s1 - s2) >= margin:
            out[spk] = {"name": names[j], "party": vps[names[j]].get("party", ""),
                        "sim": s1, "n": int(vps[names[j]].get("n", 1))}
    return out
