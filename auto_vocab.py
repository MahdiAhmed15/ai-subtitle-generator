# auto_vocab.py
import re
from collections import Counter

def extract_candidates(lines: list[str], max_items: int = 80) -> list[str]:
    """
    Pull likely names/terms from transcript itself.
    """
    text = " ".join(lines)
    # multiword capitalized phrases
    phrases = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text)
    # single capitalized tokens
    singles = re.findall(r"\b([A-Z][a-z]{2,})\b", text)

    counts = Counter(phrases + singles)
    # ignore very common English words
    stop = {"The","This","That","You","I","We","He","She","They","It","Please","Yeah","Hey"}
    items = [w for w,_ in counts.most_common() if w not in stop]
    return items[:max_items]
