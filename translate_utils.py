# translate_utils.py
from __future__ import annotations

from typing import List
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# ---------- JA -> EN (offline) ----------
_ja_en_pipe = None

def _load_ja_en():
    global _ja_en_pipe
    if _ja_en_pipe is None:
        tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-ja-en")
        mdl = AutoModelForSeq2SeqLM.from_pretrained("Helsinki-NLP/opus-mt-ja-en")
        _ja_en_pipe = pipeline("translation", model=mdl, tokenizer=tok)
    return _ja_en_pipe

def translate_lines_ja_to_en(lines: List[str]) -> List[str]:
    """
    Translate a list of Japanese strings to English (offline MarianMT).
    Safe fallback: if translation fails, returns original line.
    """
    nlp = _load_ja_en()
    out_lines: List[str] = []

    for t in lines:
        t = (t or "").strip()
        if not t:
            out_lines.append("")
            continue
        try:
            out = nlp(t, max_length=256)[0]["translation_text"]
            out_lines.append(out)
        except Exception:
            out_lines.append(t)

    return out_lines

def translate_en_to(text: str, lang_code: str) -> str:
    """
    Placeholder for future multilingual subtitles.
    Right now: returns English unchanged.
    """
    _ = lang_code
    return text
