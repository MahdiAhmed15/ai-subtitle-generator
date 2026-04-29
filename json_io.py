# json_io.py
import json
import os

def save_segments_json(segments, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)

def load_segments_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
