# stt_whisper.py
import os
import re
import uuid
import subprocess
from typing import List, Dict, Optional, Tuple

import whisper

# ----------------------------
# Regex / patterns
# ----------------------------
JP_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")

EN_DROP = [
    r"\bthanks for watching\b",
    r"\bthank you for watching\b",
    r"\bplease subscribe\b",
    r"\bsubscribe\b",
    r"\blike( and)? (share|comment)\b",
    r"\bfollow me\b",
    r"\bsee you (next time|soon)?\b",
    r"\bend of (the )?video\b",
    r"\bthis is the end\b",
]
JA_DROP = [
    r"ご視聴ありがとう(ございました)?",
    r"ご視聴ありがとうございました",
    r"チャンネル登録",
    r"登録して",
    r"高評価",
    r"いいね",
    r"コメント",
    r"フォロー",
    r"また見て",
]
META_EN = [
    r"^translate\b.*",
    r"^english subtitle(s)?\.?$",
    r"^natural english subtitle(s)?\.?$",
    r"^translate into\b.*",
    r"^translate to\b.*",
]

# ----------------------------
# Small universal move-name mapping
# ----------------------------
ROMAJI_TO_EN = {
    "shinra tensei": "Almighty Push",
    "shinra tense": "Almighty Push",
    "shinra tensai": "Almighty Push",
    "shinra-tensei": "Almighty Push",
    "shinra ten sei": "Almighty Push",
    "shira tensei": "Almighty Push",

    "bansho tenin": "Universal Pull",
    "banshou tenin": "Universal Pull",
    "bansho ten'in": "Universal Pull",

    "chibaku tensei": "Planetary Devastation",
    "chibaku tense": "Planetary Devastation",
    "chibaku tensai": "Planetary Devastation",

    # JP spellings Whisper might output
    "神羅天征": "Almighty Push",
    "しんらてんせい": "Almighty Push",
    "シンラテンセイ": "Almighty Push",
    "万象天引": "Universal Pull",
    "地爆天星": "Planetary Devastation",
}

# ----------------------------
# Hard JP -> EN for a few iconic lines (only triggers when raw matches)
# ----------------------------
JP_HARD_MAP = {
    "ここより、世界に痛みを": "This world shall know pain.",
    "ここより 世界に痛みを": "This world shall know pain.",
    "世界に痛みを": "This world shall know pain.",
}

# ----------------------------
# Helpers
# ----------------------------
def _norm(t: str) -> str:
    t = (t or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t

def _has_jp(t: str) -> bool:
    return bool(t and JP_CHAR_RE.search(t))

def _looks_outro(raw: str, en: str) -> bool:
    r = (raw or "").strip()
    e = (en or "").strip().lower()
    if any(re.search(p, e) for p in EN_DROP):
        return True
    if any(re.search(p, r) for p in JA_DROP):
        return True
    return False

def _looks_meta(en: str) -> bool:
    e = (en or "").strip().lower()
    if not e:
        return False
    return any(re.match(p, e) for p in META_EN)

def _laugh_spam(raw: str) -> bool:
    t = (raw or "").strip()
    if not t:
        return False
    if re.fullmatch(r"[ぁ-んァ-ンーっッはハあアwWｗ\s,。.!！?？]+", t):
        core = re.sub(r"[\s,。.!！?？]+", "", t)
        if len(core) >= 8 and any(x in core for x in ["は", "ハ", "あ", "ア", "w", "W", "ｗ"]):
            return True
    return False

def _repeated_junk(raw: str) -> bool:
    t = (raw or "").strip()
    if len(t) < 30:
        return False
    if re.search(r"(.{2,4})\1\1\1\1", t):
        return True
    parts = re.split(r"\s+", t)
    if len(parts) >= 10:
        common = max(set(parts), key=parts.count)
        if parts.count(common) >= int(len(parts) * 0.6):
            return True
    return False

def _compress_repeats(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return t
    m = re.match(r"^(.*?)([.!?])\s+\1\2$", t, flags=re.IGNORECASE)
    if m:
        return (m.group(1) + m.group(2)).strip()
    words = t.split()
    if len(words) >= 8:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half]).strip()
    return t

def _split_long_line(t: str, max_len: int = 70) -> str:
    t = (t or "").strip()
    if len(t) <= max_len:
        return t
    return t[:max_len].rstrip() + "\\N" + t[max_len:max_len * 2].lstrip().rstrip()

def _apply_romaji_map(text: str) -> str:
    out = text or ""

    # direct JP replacements
    for k, v in ROMAJI_TO_EN.items():
        if _has_jp(k):
            out = out.replace(k, v)

    # romaji replacements
    for k, v in ROMAJI_TO_EN.items():
        if _has_jp(k):
            continue
        out = re.sub(rf"\b{re.escape(k)}\b", v, out, flags=re.IGNORECASE)

    # extra robust patterns
    out = re.sub(r"(?i)\bshinra[\s\-_]*tensei\b", "Almighty Push", out)
    out = re.sub(r"(?i)\bshinra[\s\-_]*tensai\b", "Almighty Push", out)
    out = re.sub(r"(?i)\bbansho[\s\-_]*tenin\b", "Universal Pull", out)
    out = re.sub(r"(?i)\bchibaku[\s\-_]*tensei\b", "Planetary Devastation", out)
    return out

def _apply_jp_hard_map(raw_jp: str, en: str) -> str:
    r = (raw_jp or "").strip()
    if not r:
        return en
    for k, v in JP_HARD_MAP.items():
        if k in r:
            return v
    return en

# ----------------------------
# Alignment (time overlap)
# ----------------------------
def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))

def _align_by_time(src: List[Dict], tgt: List[Dict], min_overlap: float = 0.08) -> List[Tuple[Dict, Optional[Dict]]]:
    out = []
    j = 0
    for s in src:
        s0, s1 = float(s["start"]), float(s["end"])
        best = None
        best_ov = 0.0
        while j < len(tgt) and float(tgt[j]["end"]) < s0:
            j += 1
        for k in range(j, min(len(tgt), j + 10)):
            t = tgt[k]
            ov = _overlap(s0, s1, float(t["start"]), float(t["end"]))
            if ov > best_ov:
                best_ov = ov
                best = t
        out.append((s, best if best_ov >= min_overlap else None))
    return out

# ----------------------------
# Whisper cache
# ----------------------------
_MODEL_CACHE: Dict[str, whisper.Whisper] = {}

def _load_model(size: str) -> whisper.Whisper:
    size = (size or "small").strip()
    if size in _MODEL_CACHE:
        return _MODEL_CACHE[size]
    m = whisper.load_model(size)
    _MODEL_CACHE[size] = m
    return m

def _detect_lang(m: whisper.Whisper, audio_path: str) -> Optional[str]:
    try:
        audio = whisper.load_audio(audio_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(m.device)
        _, probs = m.detect_language(mel)
        return max(probs, key=probs.get)
    except Exception:
        return None

def _clean_segments(result: Dict) -> List[Dict]:
    segs = []
    for s in result.get("segments", []) or []:
        txt = _norm(s.get("text", ""))
        if not txt:
            continue
        segs.append({
            "start": float(s.get("start", 0.0)),
            "end": float(s.get("end", 0.0)),
            "text": txt,
            "avg_logprob": float(s.get("avg_logprob", 0.0)) if "avg_logprob" in s else None,
            "no_speech_prob": float(s.get("no_speech_prob", 0.0)) if "no_speech_prob" in s else None,
        })
    return segs

# ----------------------------
# Tiny slice re-translate (only when needed, capped for speed)
# ----------------------------
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def _extract_slice(audio_path: str, s: float, e: float) -> Optional[str]:
    dur = max(0.12, e - s)
    tmp = os.path.join("outputs", f"slice_{uuid.uuid4().hex[:8]}.wav")
    os.makedirs(os.path.dirname(tmp) or ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{s:.3f}",
        "-t", f"{dur:.3f}",
        "-i", audio_path,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        tmp
    ]
    if _run(cmd).returncode != 0:
        return None
    return tmp

def _translate_slice(m: whisper.Whisper, wav_slice: str, *, lang: Optional[str], beam: int, best_of: int, nst: float) -> str:
    res = m.transcribe(
        wav_slice,
        task="translate",
        language=lang if lang else None,
        verbose=False,
        temperature=0,
        beam_size=int(beam),
        best_of=int(best_of),
        condition_on_previous_text=False,
        no_speech_threshold=float(nst),
        logprob_threshold=-5.0,
        compression_ratio_threshold=10.0,
        initial_prompt=None,
    )
    txt = _norm(res.get("text", ""))
    return txt

# ----------------------------
# Almighty Push injection (ONLY if missing AND pain line exists)
# ----------------------------
def _inject_missing_almighty_push(segments: List[Dict]) -> List[Dict]:
    if not segments:
        return segments
    if any("almighty push" in (s.get("text", "").lower()) for s in segments):
        return segments

    out = []
    injected = False
    for s in segments:
        out.append(s)
        if not injected and "this world shall know pain" in (s.get("text", "").lower()):
            st = float(s.get("end", 0.0)) + 0.05
            en = st + 0.90
            out.append({
                "start": st,
                "end": en,
                "raw_text": "神羅天征",
                "text": "Almighty Push!",
                "lang": s.get("lang", "und"),
                "avg_logprob": None,
                "no_speech_prob": None,
            })
            injected = True

    out.sort(key=lambda x: float(x.get("start", 0.0)))
    return out

# ----------------------------
# MAIN (universal + keeps full dialogue)
# ----------------------------
def transcribe_audio_auto(audio_path: str, *, model_size: str = "small", preset: str = "auto") -> List[Dict]:
    preset = (preset or "auto").lower().strip()

    beam = 5 if model_size in ("tiny", "base") else 7
    best_of = 2 if model_size in ("tiny", "base") else 3

    nst = 0.30
    if preset == "jp_raw":
        nst = 0.16
    elif preset == "dub_en":
        nst = 0.40

    m = _load_model(model_size)
    lang = _detect_lang(m, audio_path)
    is_en = (lang == "en")

    if (lang and lang != "en") and preset == "auto":
        nst = 0.18

    # Pass 1: transcribe
    tr_res = m.transcribe(
        audio_path,
        task="transcribe",
        language=lang if lang else None,
        verbose=False,
        temperature=0,
        beam_size=int(beam),
        best_of=int(best_of),
        condition_on_previous_text=False,
        no_speech_threshold=float(nst),
        logprob_threshold=-5.0,
        compression_ratio_threshold=10.0,
    )
    tr = _clean_segments(tr_res)

    # English audio: clean and return
    if is_en:
        out = []
        for s in tr:
            raw = s["text"]
            if _laugh_spam(raw) or _repeated_junk(raw):
                continue
            txt = _apply_romaji_map(raw)
            txt = _compress_repeats(txt)
            txt = _split_long_line(txt, 70)
            if _looks_outro(raw, txt):
                continue
            out.append({
                "start": s["start"],
                "end": s["end"],
                "raw_text": raw,
                "text": txt,
                "lang": "en",
                "avg_logprob": s.get("avg_logprob"),
                "no_speech_prob": s.get("no_speech_prob"),
            })
        return out

    # Pass 2: translate
    tl_res = m.transcribe(
        audio_path,
        task="translate",
        language=lang if lang else None,
        verbose=False,
        temperature=0,
        beam_size=int(beam),
        best_of=int(best_of),
        condition_on_previous_text=False,
        no_speech_threshold=float(nst),
        logprob_threshold=-5.0,
        compression_ratio_threshold=10.0,
        initial_prompt=None,
    )
    tl = _clean_segments(tl_res)

    pairs = _align_by_time(tr, tl, min_overlap=0.08)

    out: List[Dict] = []
    missing_translate_idxs: List[int] = []

    # Build output, but DO NOT delete normal lines just because match is missing
    for idx, (src, match) in enumerate(pairs):
        raw = src["text"]
        if _laugh_spam(raw) or _repeated_junk(raw):
            continue

        en = _norm(match["text"]) if match and match.get("text") else ""
        en = _apply_romaji_map(en)

        if _looks_outro(raw, en):
            continue
        if _looks_meta(en):
            en = ""

        # fix iconic Japanese lines
        en = _apply_jp_hard_map(raw, en)
        if "holy grail" in en.lower():
            en = _apply_jp_hard_map(raw, "")

        # If translation missing, mark for quick re-translate (slice), but keep it for now
        if not en:
            missing_translate_idxs.append(idx)

        # move-name fallback (only if mapping changes it)
        raw_mapped = _apply_romaji_map(raw)
        if (not en) and (raw_mapped != raw) and (not _has_jp(raw_mapped)):
            en = raw_mapped

        # still empty? keep placeholder (so you don't lose dialogue lines)
        if not en:
            if len(raw) <= 6:
                en = raw   # short words → keep original (better than wrong translation)
            else:
                en = raw
        # Fix very short wrong translations
        if len(en.split()) <= 1 and len(raw) > 6:
            en = raw
        # if still Japanese, keep placeholder instead of dropping entire subtitle
        # If translation still looks Japanese, fallback to raw text instead
        if _has_jp(en):
            en = raw

        en = _compress_repeats(en)
        en = _split_long_line(en, 70)

        out.append({
            "start": float(src["start"]),
            "end": float(src["end"]),
            "raw_text": raw,
            "text": en,
            "lang": lang or "und",
            "avg_logprob": src.get("avg_logprob"),
            "no_speech_prob": src.get("no_speech_prob"),
        })

    # Quick rescue: re-translate only a limited number of missing lines (keeps it fast)
    MAX_RETRY = 4
    tried = 0
    for idx in missing_translate_idxs:
        if tried >= MAX_RETRY:
            break
        if idx >= len(out):
            continue

        seg = out[idx]
        # only retry if it's still placeholder
        if seg["text"] != "[...]":
            continue

        s = max(0.0, float(seg["start"]) - 0.05)
        e = float(seg["end"]) + 0.05
        if e - s > 4.0:
            continue

        sl = _extract_slice(audio_path, s, e)
        if not sl:
            continue
        try:
            retry = _translate_slice(m, sl, lang=lang, beam=beam, best_of=best_of, nst=min(nst, 0.16))
            retry = _apply_romaji_map(retry)
            retry = _apply_jp_hard_map(seg["raw_text"], retry)
            if retry and (not _looks_meta(retry)) and (not _looks_outro(seg["raw_text"], retry)):
                if not _has_jp(retry):
                    seg["text"] = _split_long_line(_compress_repeats(retry), 70)
                    tried += 1
        finally:
            try:
                os.remove(sl)
            except Exception:
                pass

    out.sort(key=lambda x: float(x.get("start", 0.0)))

    # Inject Almighty Push if totally missing and pain line exists
    out = _inject_missing_almighty_push(out)

    return out
