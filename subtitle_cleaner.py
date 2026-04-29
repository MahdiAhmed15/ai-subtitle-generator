# subtitle_cleaner.py
import re

# OPTIONAL glossary (works for any anime if you expand it)
GLOSSARY = {
    r"\bnarita\b": "Naruto",
    r"\buzumaki\b": "Uzumaki",
}

def norm(t: str) -> str:
    t = (t or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t

def fix_punctuation(s: str) -> str:
    s = norm(s)
    s = re.sub(r"\s+([?.!,])", r"\1", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    if s and s[-1] not in ".?!":
        s += "."
    if s:
        s = s[0].upper() + s[1:]
    return norm(s)

def apply_glossary(s: str) -> str:
    out = s
    for pat, repl in GLOSSARY.items():
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out

def remove_repeated_words(s: str) -> str:
    s = norm(s)
    return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", s, flags=re.IGNORECASE)

def collapse_repeated_clauses(s: str) -> str:
    s = norm(s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) > 1:
        out = []
        last = None
        for p in parts:
            key = re.sub(r"[^\w\s]", "", p.lower())
            key = re.sub(r"\s+", " ", key).strip()
            if key != last:
                out.append(p)
                last = key
        s = ", ".join(out)
    s = re.sub(r"\b(.+?)\b(?:\s+\1\b)+", r"\1", s, flags=re.IGNORECASE)
    return norm(s)

def clean_subtitle_text(t: str) -> str:
    t = norm(t)
    if not t:
        return ""
    t = apply_glossary(t)
    t = remove_repeated_words(t)
    t = collapse_repeated_clauses(t)
    t = fix_punctuation(t)
    t = remove_repeated_words(t)
    return norm(t)
