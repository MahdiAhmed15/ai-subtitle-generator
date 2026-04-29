# ass_utils.py
import os

def seconds_to_ass(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))  # centiseconds
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def segments_to_ass(segments, out_path: str):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    header = """[Script Info]
ScriptType: v4.00+
Collisions: Normal
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,Arial,48,&H00FFFFFF,&H00000000,1,3,1,2,80,80,70

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]

    for seg in segments:
        start = seconds_to_ass(float(seg.get("start", 0.0)))
        end = seconds_to_ass(float(seg.get("end", 0.1)))
        text = (seg.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
