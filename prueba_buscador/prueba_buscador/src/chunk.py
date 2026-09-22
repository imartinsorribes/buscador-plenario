"""Bloque C (1/3): trocea una transcripción en fragmentos indexables.

Agrupa segmentos consecutivos en trozos de ~max_chars conservando los
timestamps (para enlazar a YouTube en el minuto exacto) y, cuando exista, el
orador (que añadirá el Bloque B). Trozos alineados a segmentos -> timestamps
siempre coherentes.
"""
from __future__ import annotations


def _make_chunk(segs: list[dict]) -> dict:
    return {
        "text": " ".join(s["text"].strip() for s in segs).strip(),
        "start": segs[0]["start"],
        "end": segs[-1]["end"],
        "speaker": segs[0].get("speaker"),
    }


def chunk_transcript(transcript: dict, max_chars: int = 1200,
                     respect_speaker: bool = True, overlap_segments: int = 1) -> list[dict]:
    segments = [s for s in transcript.get("segments", []) if s.get("text", "").strip()]
    chunks: list[dict] = []
    cur: list[dict] = []
    cur_len = 0

    for seg in segments:
        seg_text = seg["text"].strip()
        speaker_break = (respect_speaker and cur
                         and seg.get("speaker") != cur[0].get("speaker"))
        too_long = cur and cur_len + len(seg_text) + 1 > max_chars

        if speaker_break or too_long:
            chunks.append(_make_chunk(cur))
            # solape: arrastrar los últimos segmentos (salvo si cambió el orador)
            carry = [] if speaker_break else cur[-overlap_segments:] if overlap_segments else []
            cur = list(carry)
            cur_len = sum(len(s["text"].strip()) + 1 for s in cur)

        cur.append(seg)
        cur_len += len(seg_text) + 1

    if cur:
        chunks.append(_make_chunk(cur))
    return chunks
