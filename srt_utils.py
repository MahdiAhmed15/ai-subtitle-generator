from typing import List, Dict

def _fmt_time(seconds: float) -> str:
    ms = int(seconds * 1000)
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def segments_to_srt(segments: List[Dict], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(
                f"{i}\n"
                f"{_fmt_time(seg['start'])} --> {_fmt_time(seg['end'])}\n"
                f"{seg['text']}\n\n"
            )
