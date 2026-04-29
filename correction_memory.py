# correction_memory.py
import os
import json
import re
from typing import Dict, Any, Optional

DEFAULT_PATH = os.path.join("outputs", "correction_memory.json")

def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _norm_jp(s: str) -> str:
    # keep Japanese chars; just normalize spaces
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _load(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"phrases": {}, "jp_phrases": {}}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # backward compatible: old format { "narita": "Naruto" }
        if isinstance(data, dict) and "phrases" not in data and "jp_phrases" not in data:
            return {"phrases": data, "jp_phrases": {}}

        if not isinstance(data, dict):
            return {"phrases": {}, "jp_phrases": {}}

        data.setdefault("phrases", {})
        data.setdefault("jp_phrases", {})
        return data
    except Exception:
        return {"phrases": {}, "jp_phrases": {}}

def _save(data: Dict[str, Any], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def remember_phrase(
    *,
    auto_en: Optional[str],
    final_en: Optional[str],
    raw_text: Optional[str],
    path: str = DEFAULT_PATH
) -> None:
    """
    Universal learning:
    - Save mapping from auto English -> final English
    - If raw_text is Japanese, also save raw Japanese -> final English (strongest)
    """
    auto_en = (auto_en or "").strip()
    final_en = (final_en or "").strip()
    raw_text = (raw_text or "").strip()

    if not final_en:
        return
    if auto_en and auto_en.lower() == final_en.lower():
        auto_en = ""  # no need to store same thing

    data = _load(path)

    if auto_en:
        k = _norm_key(auto_en)
        if len(k) >= 3:
            data["phrases"][k] = final_en

    # store raw japanese phrase mapping too (best for jutsu names)
    if raw_text:
        # if it contains any non-ascii (Japanese/Chinese), store it
        if re.search(r"[^\x00-\x7F]", raw_text):
            kj = _norm_jp(raw_text)
            if len(kj) >= 2:
                data["jp_phrases"][kj] = final_en

    _save(data, path)

def apply_phrase_memory(
    *,
    raw_text: str,
    auto_en: str,
    path: str = DEFAULT_PATH
) -> str:
    """
    Apply learned fixes:
    1) If raw Japanese phrase seen before -> return mapped English directly
    2) Else if auto English phrase seen before -> replace whole line
    """
    raw_text = (raw_text or "").strip()
    auto_en = (auto_en or "").strip()
    if not auto_en:
        return ""

    data = _load(path)

    # 1) exact JP phrase match
    if raw_text and re.search(r"[^\x00-\x7F]", raw_text):
        kj = _norm_jp(raw_text)
        hit = data.get("jp_phrases", {}).get(kj)
        if hit:
            return hit

    # 2) exact EN phrase match
    k = _norm_key(auto_en)
    hit2 = data.get("phrases", {}).get(k)
    if hit2:
        return hit2

    return auto_en
