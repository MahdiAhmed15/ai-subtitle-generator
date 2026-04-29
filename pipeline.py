# pipeline.py
import os
import uuid
import json
import subprocess
import re
from typing import List, Dict, Optional

from stt_whisper import transcribe_audio_auto
from segment_merge import merge_segments
from timing_fix import (
    detect_first_voice_time,
    fix_first_subtitle_start,
    refine_starts_to_voice,
    nudge_starts,
    clamp_ends,
    dedupe_segments,
)
from subtitle_cleaner import clean_subtitle_text
from ass_utils import segments_to_ass
from av_merge import burn_subtitles
from json_io import save_segments_json, load_segments_json
from dub_utils import synthesize_voiceover_wav

# 🔥 Translator
from deep_translator import GoogleTranslator

OUTPUT_DIR = "outputs"


# ----------------------------
# 🔥 SMART LANGUAGE FIX
# ----------------------------
JP_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")

def _has_jp(text: str) -> bool:
    return bool(text and JP_CHAR_RE.search(text))


def force_target_language(segments: List[Dict], target_lang: str) -> List[Dict]:
    """
    🔥 IMPORTANT:
    - Keeps good Whisper translations
    - ONLY fixes leftover Japanese lines
    """

    if not segments:
        return segments

    out = []

    for s in segments:
        ns = dict(s)
        text = str(ns.get("text", "")).strip()

        if not text:
            out.append(ns)
            continue

        # ✅ English selected → only fix Japanese leftovers
        if target_lang == "en":
            if _has_jp(text):
                try:
                    ns["text"] = GoogleTranslator(source="auto", target="en").translate(text)
                except:
                    pass
            out.append(ns)
            continue

        # ✅ Other languages → translate everything
        try:
            ns["text"] = GoogleTranslator(source="auto", target=target_lang).translate(text)
        except:
            pass

        out.append(ns)

    return out


# ----------------------------
# UTILS
# ----------------------------
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except:
        return default


def _ffprobe_streams(video_path: str):
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", video_path]
    p = _run(cmd)
    if p.returncode != 0:
        return []
    try:
        return json.loads(p.stdout).get("streams", [])
    except:
        return []


def choose_audio_stream(video_path: str) -> int:
    streams = _ffprobe_streams(video_path)
    audios = []

    for s in streams:
        if s.get("codec_type") == "audio":
            lang = (s.get("tags", {}).get("language") or "").lower()
            audios.append((s, lang))

    if not audios:
        return 0

    for pref in ("eng", "jpn"):
        for s, lang in audios:
            if lang == pref:
                return [a for a, _ in audios].index(s)

    return 0


# ----------------------------
# AUDIO
# ----------------------------
def extract_audio_wav(video_path, wav_out, audio_index=None, *, boost_dialogue=True):
    os.makedirs(os.path.dirname(wav_out) or ".", exist_ok=True)

    if audio_index is None:
        audio_index = choose_audio_stream(video_path)

    af = (
        "highpass=f=90,lowpass=f=8000,"
        "acompressor=threshold=-18dB:ratio=6,"
        "dynaudnorm=f=200:g=20,"
        "aresample=async=1:first_pts=0"
        if boost_dialogue else
        "aresample=async=1:first_pts=0"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-map", f"0:a:{audio_index}?",
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        "-af", af,
        wav_out
    ]

    if _run(cmd).returncode != 0:
        raise RuntimeError("Audio extraction failed")


# ----------------------------
# CLEANING
# ----------------------------
def _clean_segments_text(segments):
    out = []
    for s in segments:
        ns = dict(s)
        ns["text"] = clean_subtitle_text(str(ns.get("text", "")))
        ns["raw_text"] = clean_subtitle_text(str(ns.get("raw_text", "")))
        out.append(ns)
    return out


def improve_readability(segments):
    out = []
    for s in segments:
        ns = dict(s)
        t = str(ns.get("text", "")).strip()

        if t:
            if t[0].isalpha():
                t = t[0].upper() + t[1:]
            if t[-1] not in ".!?":
                t += "."

        ns["text"] = t
        out.append(ns)

    return out


# ----------------------------
# MAIN PIPELINE
# ----------------------------
def run_pipeline(
    video_path: str,
    *,
    mode="draft",
    target_lang="en",
    model_size="small",
    preset="auto",
    boost_dialogue=True,
):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    job_id = uuid.uuid4().hex[:8]

    wav_path = os.path.join(OUTPUT_DIR, f"{job_id}_audio.wav")
    segments_json = os.path.join(OUTPUT_DIR, f"{job_id}_segments.json")
    chosen_json = os.path.join(OUTPUT_DIR, f"{job_id}_chosen.json")
    ass_path = os.path.join(OUTPUT_DIR, f"{job_id}_subtitles.ass")

    # ---------------- DRAFT ----------------
    if mode == "draft":
        a_idx = choose_audio_stream(video_path)
        extract_audio_wav(video_path, wav_path, a_idx, boost_dialogue=boost_dialogue)

        segments = transcribe_audio_auto(
            wav_path,
            model_size=model_size,
            preset=preset,
        ) or []

        if not segments:
            raise RuntimeError("No subtitles generated")

        # ✅ KEEP ORIGINAL PIPELINE QUALITY
        segments = merge_segments(segments)
        segments = _clean_segments_text(segments)

        # 🔥 FIX ONLY WRONG JAPANESE LINES
        segments = force_target_language(segments, target_lang)

        segments = dedupe_segments(segments)
        segments = improve_readability(segments)

        save_segments_json(segments, segments_json)

        return {
            "job_id": job_id,
            "video": video_path,
            "wav": wav_path,
            "segments_json": segments_json,
            "chosen_json_expected": chosen_json,
            "ass_will_be": ass_path,
            "target_lang": target_lang,
        }

    # ---------------- FINALIZE ----------------
    if mode == "finalize":
        chosen_segments = load_segments_json(chosen_json)
        segments_to_ass(chosen_segments, ass_path)

        return {
            "video": video_path,
            "subtitle": ass_path,
        }

    raise ValueError("Invalid mode")


# ----------------------------
# EXPORT VIDEO
# ----------------------------
def burn_selected_subtitle(video_path, ass_path):
    out_video = os.path.join(OUTPUT_DIR, "final_subbed.mp4")
    burn_subtitles(video_path, ass_path, out_video)
    return out_video


# ----------------------------
# DUB
# ----------------------------
def mux_dubbed_audio(video_path, dubbed_wav, out_video):
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", dubbed_wav,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        out_video
    ]
    p = _run(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return out_video


def make_dubbed_video(video_path, *, base_wav, segments, voice, keep_original=False):
    out_video = os.path.join(OUTPUT_DIR, "final_dubbed.mp4")
    dubbed_wav = os.path.join(OUTPUT_DIR, "dubbed_mix.wav")

    synthesize_voiceover_wav(
        segments=segments,
        out_wav=dubbed_wav,
        voice=voice,
        base_wav=(base_wav if keep_original else None),
        rate="+0%",
        volume="+0%",
        voice_gain_db=6.0,
        bg_volume=(0.25 if keep_original else 0.0),
        sample_rate=16000,
    )

    return mux_dubbed_audio(video_path, dubbed_wav, out_video)