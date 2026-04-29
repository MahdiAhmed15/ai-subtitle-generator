import os
import io
from typing import List, Dict, Optional
from gtts import gTTS
from pydub import AudioSegment
import requests
from dotenv import load_dotenv

load_dotenv()

def synthesize_tts(
    segments: List[Dict],
    out_wav: str,
    provider: str = "gtts",
    voice_id: Optional[str] = None,
    target_lang: str = "en"
) -> None:
    if provider == "elevenlabs":
        _tts_elevenlabs(segments, out_wav, voice_id, target_lang)
    else:
        _tts_gtts(segments, out_wav, target_lang)


# =========================
# gTTS (offline-friendly)
# =========================
def _tts_gtts(segments: List[Dict], out_wav: str, lang: str) -> None:
    final_audio = AudioSegment.silent(duration=0)
    current_time_ms = 0

    for seg in segments:
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)
        duration_ms = end_ms - start_ms
        text = seg["text"].strip()

        # 🔹 Add silence until this segment starts
        if start_ms > current_time_ms:
            final_audio += AudioSegment.silent(duration=start_ms - current_time_ms)
            current_time_ms = start_ms

        if not text:
            final_audio += AudioSegment.silent(duration=duration_ms)
            current_time_ms += duration_ms
            continue

        # Generate TTS
        tts = gTTS(text=text, lang=lang)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)

        speech = AudioSegment.from_file(buf, format="mp3")

        # 🔹 Fit speech into segment duration
        if len(speech) > duration_ms:
            speech = speech[:duration_ms]
        else:
            speech += AudioSegment.silent(duration=duration_ms - len(speech))

        final_audio += speech
        current_time_ms += duration_ms

    final_audio.export(out_wav, format="wav")


# =========================
# ElevenLabs (premium)
# =========================
def _tts_elevenlabs(
    segments: List[Dict],
    out_wav: str,
    voice_id: Optional[str],
    target_lang: str
):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    if not voice_id:
        voice_id = "21m00Tcm4TlvDq8ikWAM"

    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    final_audio = AudioSegment.silent(duration=0)
    current_time_ms = 0

    for seg in segments:
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)
        duration_ms = end_ms - start_ms
        text = seg["text"].strip()

        if start_ms > current_time_ms:
            final_audio += AudioSegment.silent(duration=start_ms - current_time_ms)
            current_time_ms = start_ms

        if not text:
            final_audio += AudioSegment.silent(duration=duration_ms)
            current_time_ms += duration_ms
            continue

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.7
            }
        }

        r = requests.post(url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()

        speech = AudioSegment.from_file(io.BytesIO(r.content), format="mp3")

        if len(speech) > duration_ms:
            speech = speech[:duration_ms]
        else:
            speech += AudioSegment.silent(duration=duration_ms - len(speech))

        final_audio += speech
        current_time_ms += duration_ms

    final_audio.export(out_wav, format="wav")
