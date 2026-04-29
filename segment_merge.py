# segment_merge.py
import re

JP_END_PUNCT = ("。", "！", "？", "!", "?", ".", "…", "ー", "♪")
ASS_NEWLINE = "\\N"  # IMPORTANT: avoid Python \N unicode escape

# Match romaji move-name phrases in many forms:
# shinra tensei / Shinra Tensei / SHINRA TENSEI / Shinra Tensei!
ROMAJI_MOVE = re.compile(r"^[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,4}[!?.…]?$")

def _clean(t: str) -> str:
    return (t or "").strip()

def _has_ass_newline(t: str) -> bool:
    return ASS_NEWLINE in (t or "")

def _is_short_shout(text: str) -> bool:
    t = _clean(text)
    if not t:
        return False
    if len(t) <= 16:
        return True
    if t.count(" ") <= 2 and len(t) <= 28:
        return True
    if "!" in t and len(t) <= 40:
        return True
    return False

def _looks_like_move_name(en: str) -> bool:
    t = _clean(en)
    if not t:
        return False
    if len(t) > 36:
        return False
    return bool(ROMAJI_MOVE.fullmatch(t))

def merge_segments(segments, max_gap=0.18, max_chars=70, max_duration=6.0):
    """
    Anime-friendly merge:
    - merges only when it looks like one continuing sentence
    - protects shouts + move names (keeps them separate)
    - avoids merging lines that already contain ASS newlines (\\N)
    """
    if not segments:
        return []

    segs = sorted(segments, key=lambda s: float(s.get("start", 0.0)))
    merged = []
    buf = dict(segs[0])

    for seg in segs[1:]:
        gap = float(seg.get("start", 0.0)) - float(buf.get("end", 0.0))

        buf_text = _clean(buf.get("text", ""))
        seg_text = _clean(seg.get("text", ""))

        buf_raw = _clean(buf.get("raw_text", ""))
        seg_raw = _clean(seg.get("raw_text", ""))

        # Don’t merge if either already has ASS newline (already “split”)
        if _has_ass_newline(buf_text) or _has_ass_newline(seg_text):
            merged.append(buf)
            buf = dict(seg)
            continue

        # Protect shouts & move names: never merge these
        if (
            _is_short_shout(buf_text) or _is_short_shout(seg_text) or
            _looks_like_move_name(buf_text) or _looks_like_move_name(seg_text) or
            _is_short_shout(buf_raw) or _is_short_shout(seg_raw)
        ):
            merged.append(buf)
            buf = dict(seg)
            continue

        # Sentence finished?
        finished = buf_text.endswith(JP_END_PUNCT) or buf_raw.endswith(JP_END_PUNCT)

        too_long = (len(buf_text) + 1 + len(seg_text)) > max_chars
        too_long_time = (float(seg.get("end", 0.0)) - float(buf.get("start", 0.0))) > max_duration

        if gap <= max_gap and (not finished) and (not too_long) and (not too_long_time):
            buf["end"] = seg.get("end", buf.get("end"))
            buf["text"] = (buf_text + " " + seg_text).strip()

            rt1 = _clean(buf.get("raw_text", buf_text))
            rt2 = _clean(seg.get("raw_text", seg_text))
            buf["raw_text"] = (rt1 + " " + rt2).strip()
        else:
            merged.append(buf)
            buf = dict(seg)

    merged.append(buf)
    return merged
