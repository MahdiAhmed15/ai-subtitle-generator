# dub_utils.py
import os
import re
import uuid
import time
import asyncio
import subprocess
from typing import List, Dict, Optional

import edge_tts

OUTPUT_DIR = "outputs"

# Remove ASS tags like {\i1} etc
ASS_TAG_RE = re.compile(r"\{[^}]*\}")
# Remove control chars
CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
# Lines that are basically not speakable
BAD_ONLY_RE = re.compile(r"^[\W_]+$")


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _safe_unlink(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _clean_tts_text(t: str) -> str:
    """
    Make text safe for Edge TTS:
    - remove ASS tags
    - replace \\N with space
    - remove control chars
    - collapse spaces
    """
    t = (t or "").strip()
    if not t:
        return ""

    t = t.replace("\\N", " ").replace("\n", " ").replace("\r", " ")
    t = ASS_TAG_RE.sub("", t)
    t = CTRL_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()

    if not t or BAD_ONLY_RE.match(t):
        return ""

    return t


def _split_for_tts(t: str, max_len: int = 180) -> List[str]:
    """
    Edge TTS is more stable with shorter chunks.
    """
    t = (t or "").strip()
    if not t:
        return []
    if len(t) <= max_len:
        return [t]

    parts = re.split(r"([.!?])", t)
    chunks = []
    cur = ""

    for i in range(0, len(parts), 2):
        seg = parts[i].strip()
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        piece = (seg + punct).strip()
        if not piece:
            continue

        if len(cur) + 1 + len(piece) <= max_len:
            cur = (cur + " " + piece).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = piece

    if cur:
        chunks.append(cur)

    out = []
    for c in chunks:
        if len(c) <= max_len:
            out.append(c)
        else:
            out.extend([c[i:i + max_len].strip() for i in range(0, len(c), max_len)])

    return [x for x in out if x]


def _run_coro_blocking(coro):
    """
    Runs async safely from sync code.
    """
    try:
        asyncio.get_running_loop()
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    except RuntimeError:
        return asyncio.run(coro)


async def _edge_tts_to_file(text: str, voice: str, rate: str, volume: str, out_mp3: str):
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
    await comm.save(out_mp3)


def _tts_with_retry(
    text: str,
    voice: str,
    rate: str,
    volume: str,
    out_mp3: str,
    max_tries: int = 4
) -> bool:
    if not text.strip():
        return False

    delay = 0.35
    for _ in range(max_tries):
        try:
            _run_coro_blocking(_edge_tts_to_file(text, voice, rate, volume, out_mp3))
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                return True
        except edge_tts.exceptions.NoAudioReceived:
            pass
        except Exception:
            pass

        time.sleep(delay)
        delay *= 1.8

    return False


def _ffmpeg_mp3_to_wav16k(mp3_path: str, wav_path: str, sample_rate: int = 16000) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", mp3_path,
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        wav_path
    ]
    p = _run(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)


def _make_silence_wav(wav_path: str, duration_s: float, sample_rate: int = 16000) -> None:
    duration_s = max(0.2, float(duration_s))
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate={sample_rate}",
        "-t", f"{duration_s:.3f}",
        "-c:a", "pcm_s16le",
        wav_path
    ]
    p = _run(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)


def _probe_duration_s(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    p = _run(cmd)
    if p.returncode != 0:
        return 0.0
    try:
        return float((p.stdout or "").strip())
    except Exception:
        return 0.0


def _build_atempo_chain(speed: float) -> str:
    """
    ffmpeg atempo supports roughly 0.5 to 2.0 per filter.
    Chain filters if needed.
    """
    speed = max(0.5, min(4.0, float(speed)))
    parts = []

    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0

    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5

    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)


def _fit_wav_to_duration(
    in_wav: str,
    out_wav: str,
    target_duration_s: float,
    sample_rate: int = 16000,
    max_speedup: float = 1.35,
) -> None:
    """
    Make a segment fit its subtitle slot:
    - if slightly too long, speed it up a bit
    - if still long, trim gently
    """
    target_duration_s = max(0.15, float(target_duration_s))
    current = _probe_duration_s(in_wav)

    if current <= 0:
        _make_silence_wav(out_wav, target_duration_s, sample_rate)
        return

    # Already short enough
    if current <= target_duration_s:
        cmd = [
            "ffmpeg", "-y",
            "-i", in_wav,
            "-ac", "1",
            "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            out_wav
        ]
        p = _run(cmd)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)
        return

    needed_speed = current / target_duration_s
    speed = min(max_speedup, needed_speed)
    af = _build_atempo_chain(speed)

    # If after max speed-up it may still be too long, trim to slot
    cmd = [
        "ffmpeg", "-y",
        "-i", in_wav,
        "-filter:a", af,
        "-t", f"{target_duration_s:.3f}",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        out_wav
    ]
    p = _run(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)


def synthesize_voiceover_wav(
    *,
    segments: List[Dict],
    out_wav: str,
    voice: str,
    base_wav: Optional[str] = None,
    rate: str = "+0%",
    volume: str = "+0%",
    voice_gain_db: float = 6.0,
    bg_volume: float = 0.25,
    sample_rate: int = 16000,
) -> str:
    """
    Build one mixed WAV:
    - Generate TTS per segment
    - Fit each segment to its subtitle window
    - Delay each line to its start time
    - Mix all voices + optional ducked original audio
    """
    _ensure_dir(os.path.dirname(out_wav) or ".")
    tmp_dir = os.path.join(OUTPUT_DIR, "dub_tmp")
    _ensure_dir(tmp_dir)

    max_end = 0.0
    cleaned_items = []

    for s in segments or []:
        start = float(s.get("start", 0.0))
        end = float(s.get("end", start + 0.2))
        max_end = max(max_end, end)

        raw_text = str(s.get("text") or "").strip()
        t = _clean_tts_text(raw_text)
        if not t:
            continue

        parts = _split_for_tts(t, max_len=180)
        if not parts:
            continue

        cleaned_items.append((start, end, " ".join(parts).strip()))

    if not cleaned_items:
        _make_silence_wav(out_wav, duration_s=max(1.0, max_end + 0.5), sample_rate=sample_rate)
        return out_wav

    voice_wavs = []
    created_tmp_files = []

    try:
        for idx, (start, end, text) in enumerate(cleaned_items):
            mp3_path = os.path.join(tmp_dir, f"tts_{idx}_{uuid.uuid4().hex[:6]}.mp3")
            raw_wav_path = os.path.join(tmp_dir, f"tts_{idx}_{uuid.uuid4().hex[:6]}_raw.wav")
            fit_wav_path = os.path.join(tmp_dir, f"tts_{idx}_{uuid.uuid4().hex[:6]}_fit.wav")

            created_tmp_files.extend([mp3_path, raw_wav_path, fit_wav_path])

            ok = _tts_with_retry(text, voice, rate, volume, mp3_path, max_tries=4)
            if not ok:
                continue

            _ffmpeg_mp3_to_wav16k(mp3_path, raw_wav_path, sample_rate=sample_rate)

            # Fit inside subtitle slot, leaving a tiny gap
            slot = max(0.18, (end - start) - 0.04)
            _fit_wav_to_duration(
                raw_wav_path,
                fit_wav_path,
                target_duration_s=slot,
                sample_rate=sample_rate,
                max_speedup=1.35,
            )

            voice_wavs.append((start, fit_wav_path))
            time.sleep(0.05)

        if not voice_wavs:
            _make_silence_wav(out_wav, duration_s=max(1.0, max_end + 0.5), sample_rate=sample_rate)
            return out_wav

        inputs = []
        has_bg = bool(base_wav and os.path.exists(base_wav))
        if has_bg:
            inputs.append(base_wav)

        for _, wp in voice_wavs:
            inputs.append(wp)

        fc = []
        labels = []

        input_idx_offset = 0
        if has_bg:
            fc.append(f"[0:a]volume={bg_volume}[bg]")
            labels.append("[bg]")
            input_idx_offset = 1

        for i, (start, wp) in enumerate(voice_wavs):
            ms = max(0, int(start * 1000))
            src = f"[{input_idx_offset + i}:a]"
            out = f"[v{i}]"
            fc.append(f"{src}adelay={ms}|{ms},volume={voice_gain_db}dB{out}")
            labels.append(out)

        n = len(labels)
        if n == 1:
            fc.append(f"{labels[0]}anull[mix]")
        else:
            fc.append(f"{''.join(labels)}amix=inputs={n}:dropout_transition=0:normalize=0[mix]")

        total_dur = max(1.0, max_end + 0.8)

        cmd = ["ffmpeg", "-y"]
        for p in inputs:
            cmd += ["-i", p]

        cmd += [
            "-filter_complex", ";".join(fc),
            "-map", "[mix]",
            "-t", f"{total_dur:.3f}",
            "-ac", "1",
            "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            out_wav
        ]

        p = _run(cmd)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)

        return out_wav

    finally:
        for fp in created_tmp_files:
            _safe_unlink(fp)