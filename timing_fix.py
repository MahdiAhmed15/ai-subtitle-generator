# timing_fix.py
import re
import subprocess
import wave
import struct
from typing import List, Dict, Optional


# ----------------------------
# 1) Detect initial voice start
# ----------------------------
def detect_first_voice_time(
    wav_path: str,
    max_check: int = 12,
    noise_db: str = "-35dB",
    min_silence: float = 0.20,
) -> float:
    """
    Detect when initial silence ends using ffmpeg silencedetect.
    Returns first detected silence_end time in seconds, else 0.0

    Note: On some anime with music/ambience, this can be "wrong".
    So fix_first_subtitle_start() below is conservative by design.
    """
    cmd = [
        "ffmpeg", "-hide_banner",
        "-t", str(max_check),
        "-i", wav_path,
        "-af", f"silencedetect=noise={noise_db}:d={min_silence}",
        "-f", "null", "-"
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    log = p.stderr or ""

    m = re.search(r"silence_end:\s*([0-9.]+)", log)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except Exception:
        return 0.0


def fix_first_subtitle_start(
    segments: Optional[List[Dict]],
    voice_time: float,
    pad: float = 0.03,
    min_apply: float = 0.15,
    min_shift: float = 0.60,
    max_reasonable_voice_time: float = 8.0,
) -> List[Dict]:
    """
    Conservative: ONLY push the FIRST segment forward if it's clearly too early.

    Why conservative?
    - silencedetect can be fooled by music/ambience and report a late "voice_time"
    - pushing forward can hide early dialogue if voice_time is wrong

    Rules to apply:
    - only if voice_time >= min_apply
    - only if voice_time is not crazy large (<= max_reasonable_voice_time)
    - only if the first segment starts BEFORE (voice_time - min_shift)
    """
    if not segments:
        return []

    if voice_time < min_apply:
        return segments

    if voice_time > max_reasonable_voice_time:
        # likely false detection (music/ambience), do nothing
        return segments

    s0 = float(segments[0].get("start", 0.0))
    e0 = float(segments[0].get("end", s0 + 0.12))

    # If first line is only slightly early, DON'T move it.
    if s0 >= (voice_time - min_shift):
        return segments

    delta = (voice_time + pad) - s0

    seg0 = dict(segments[0])
    new_start = max(0.0, s0 + delta)
    new_end = max(new_start + 0.12, e0 + delta)

    seg0["start"] = float(new_start)
    seg0["end"] = float(new_end)

    return [seg0] + segments[1:]


# ----------------------------
# 2) General timing helpers
# ----------------------------
def nudge_starts(
    segments: Optional[List[Dict]],
    start_delay: float = 0.01,
    min_gap: float = 0.02,
    min_dur: float = 0.12,
) -> List[Dict]:
    """
    Push every segment start slightly later (reduces "too-early" feel),
    while keeping a small min_gap and valid duration.
    Keep start_delay SMALL to avoid missing early shouts.
    """
    if not segments:
        return []

    out = []
    prev_end = 0.0

    for seg in segments:
        s = float(seg.get("start", 0.0))
        e = float(seg.get("end", s + min_dur))

        s2 = s + start_delay
        s2 = max(s2, prev_end + min_gap)

        if s2 > e - min_dur:
            s2 = max(s, e - min_dur)

        e2 = max(e, s2 + min_dur)

        ns = dict(seg)
        ns["start"] = float(s2)
        ns["end"] = float(e2)
        out.append(ns)
        prev_end = float(e2)

    return out


def clamp_ends(
    segments: Optional[List[Dict]],
    min_gap: float = 0.06,
    max_duration: float = 6.5,
    min_dur: float = 0.12,
) -> List[Dict]:
    """
    Prevent subtitles from hanging too long.
    - end time <= next start - min_gap
    - duration <= max_duration
    """
    if not segments:
        return []

    fixed = []
    for i, seg in enumerate(segments):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + min_dur))

        if end - start > max_duration:
            end = start + max_duration

        if i < len(segments) - 1:
            next_start = float(segments[i + 1].get("start", end))
            end = min(end, max(start + min_dur, next_start - min_gap))

        if end < start + min_dur:
            end = start + min_dur

        ns = dict(seg)
        ns["start"] = float(start)
        ns["end"] = float(end)
        fixed.append(ns)

    return fixed


# ----------------------------
# 3) Deduplicate repeating subtitles (SAFER)
# ----------------------------
def _key_text(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s']", "", t)
    return t.strip()


def _is_short_shout(text: str) -> bool:
    """
    Do NOT dedupe short shouts like:
    "Naruto!" "Help!" "No!" "Run!"
    """
    if not text:
        return True
    raw = text.strip()
    k = _key_text(raw)
    # very short, or one/two words => treat as shout
    if len(k) <= 8:
        return True
    if raw.count(" ") <= 1 and len(k) <= 12:
        return True
    if "!" in raw and len(k) <= 20:
        return True
    return False


def dedupe_segments(
    segments: Optional[List[Dict]],
    window: float = 25.0,
    mode: str = "extend",
) -> List[Dict]:
    """
    Remove annoying repeats where the SAME text appears again and again.

    SAFETY:
    - Will NOT dedupe short shouts (so you don't lose real "Naruto!" moments)
    """
    if not segments:
        return []

    out: List[Dict] = []
    last_by_key: Dict[str, int] = {}

    for seg in segments:
        s = float(seg.get("start", 0.0))
        e = float(seg.get("end", s + 0.12))
        text = str(seg.get("text", "") or "")
        k = _key_text(text)

        if not k:
            out.append(seg)
            continue

        if _is_short_shout(text):
            out.append(seg)
            continue

        if k in last_by_key:
            j = last_by_key[k]
            prev = out[j]
            prev_end = float(prev.get("end", float(prev.get("start", 0.0))))

            if (s - prev_end) <= window:
                if mode == "extend":
                    prev2 = dict(prev)
                    prev2["end"] = max(prev_end, e)
                    out[j] = prev2
                    continue
                elif mode == "drop":
                    continue

        last_by_key[k] = len(out)
        out.append(seg)

    return out


# ----------------------------
# 4) Snap each segment start to actual voice onset (VAD-like)
# ----------------------------
def _read_wav_pcm16_mono_16k(wav_path: str):
    with wave.open(wav_path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        if sr != 16000 or ch != 1 or sw != 2:
            raise ValueError(f"WAV must be 16kHz mono 16-bit PCM. Got sr={sr}, ch={ch}, sw={sw}")
        pcm = w.readframes(w.getnframes())
    return pcm, sr


def _slice_pcm(pcm: bytes, sr: int, t0: float, t1: float) -> bytes:
    bps = 2
    start = max(0, int(t0 * sr)) * bps
    end = max(0, int(t1 * sr)) * bps
    if end <= start:
        return b""
    return pcm[start:end]


def _avg_abs(frame: bytes) -> float:
    if not frame:
        return 0.0
    n = len(frame) // 2
    if n <= 0:
        return 0.0
    samples = struct.unpack("<" + "h" * n, frame)
    return sum(abs(s) for s in samples) / n


def refine_starts_to_voice(
    wav_path: str,
    segments: Optional[List[Dict]],
    *,
    max_seek: float = 1.00,
    frame_ms: int = 20,
    vad_aggressiveness: int = 2,
    prepad: float = 0.05,
    min_dur: float = 0.12,
    energy_floor: int = 300,
    energy_mult: float = 3.0,
    look_ahead: float = 0.25,
) -> List[Dict]:
    """
    For each segment, find first voiced frame and move start forward.

    Uses webrtcvad if installed; otherwise uses adaptive energy fallback:
    threshold = max(energy_floor, noise_floor * energy_mult)

    look_ahead lets us search slightly past the segment end (helps when Whisper start/end is sloppy).
    """
    if not segments:
        return []

    try:
        pcm, sr = _read_wav_pcm16_mono_16k(wav_path)
    except Exception:
        return segments

    try:
        import webrtcvad
        vad = webrtcvad.Vad(int(vad_aggressiveness))
        use_vad = True
    except Exception:
        vad = None
        use_vad = False

    bytes_per_frame = int(sr * (frame_ms / 1000.0)) * 2
    if bytes_per_frame <= 0:
        return segments

    fixed: List[Dict] = []
    for seg in segments:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + min_dur))
        if end <= start:
            fixed.append(seg)
            continue

        # allow slight lookahead (helps catch late-start voice)
        search_end = min(end + look_ahead, start + max_seek)
        if search_end <= start:
            fixed.append(seg)
            continue

        chunk = _slice_pcm(pcm, sr, start, search_end)
        if len(chunk) < bytes_per_frame:
            fixed.append(seg)
            continue

        voice_offset = None

        if use_vad:
            for i in range(0, len(chunk) - bytes_per_frame + 1, bytes_per_frame):
                frame = chunk[i:i + bytes_per_frame]
                if vad.is_speech(frame, sr):
                    voice_offset = (i / 2) / sr
                    break
        else:
            # adaptive energy threshold
            # estimate noise floor from first few frames
            noise_frames = min(6, (len(chunk) // bytes_per_frame))
            noise_vals = []
            for i in range(0, noise_frames * bytes_per_frame, bytes_per_frame):
                noise_vals.append(_avg_abs(chunk[i:i + bytes_per_frame]))
            noise_floor = sorted(noise_vals)[len(noise_vals) // 2] if noise_vals else 0.0
            thr = max(float(energy_floor), float(noise_floor) * float(energy_mult))

            for i in range(0, len(chunk) - bytes_per_frame + 1, bytes_per_frame):
                frame = chunk[i:i + bytes_per_frame]
                if _avg_abs(frame) > thr:
                    voice_offset = (i / 2) / sr
                    break

        if voice_offset is not None:
            new_start = start + max(0.0, voice_offset - prepad)
            # keep duration safe
            if new_start < end - min_dur:
                start = new_start
            else:
                start = max(float(seg.get("start", 0.0)), end - min_dur)

        if end < start + min_dur:
            end = start + min_dur

        ns = dict(seg)
        ns["start"] = float(start)
        ns["end"] = float(end)
        fixed.append(ns)

    return fixed
