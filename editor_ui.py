# editor_ui.py
import os
import json
import streamlit as st
from correction_memory import remember_phrase


def fmt_time(t: float) -> str:
    m = int(t // 60)
    s = t % 60
    return f"{m:02}:{s:05.2f}"


def _is_low_conf(seg: dict) -> tuple[bool, str]:
    """
    Whisper segment confidence hints:
      - avg_logprob: closer to 0 is better; very negative is worse (ex: -2.0 bad)
      - no_speech_prob: higher means whisper thinks it's silence

    Returns: (is_risky, reason_text)
    """
    avg_lp = seg.get("avg_logprob", None)
    nsp = seg.get("no_speech_prob", None)

    reasons = []

    # These thresholds are practical defaults (tweak if needed)
    if isinstance(avg_lp, (int, float)) and avg_lp < -1.2:
        reasons.append(f"low confidence (avg_logprob={avg_lp:.2f})")
    if isinstance(nsp, (int, float)) and nsp > 0.60:
        reasons.append(f"maybe silence (no_speech_prob={nsp:.2f})")

    return (len(reasons) > 0, ", ".join(reasons))


def render_editor(segments, chosen, *, max_chars: int = 80):
    if not segments:
        st.info("No segments loaded yet. Generate subtitles first.")
        return chosen, 0

    if "idx" not in st.session_state:
        st.session_state.idx = 0

    # optional: allow "review flags"
    if "review_flags" not in st.session_state:
        st.session_state.review_flags = {}

    idx = max(0, min(int(st.session_state.idx), len(segments) - 1))
    seg = segments[idx]

    whisper_line = seg.get("raw_text", seg.get("text", ""))
    auto_line = seg.get("text", "")

    # ---- Header ----
    st.subheader(f"Line {idx+1}/{len(segments)}")
    st.write(f"**Time:** {fmt_time(float(seg['start']))} → {fmt_time(float(seg['end']))}")

    # ---- Confidence badge ----
    risky, why = _is_low_conf(seg)
    if risky:
        st.error(f"⚠️ Low confidence: {why}. This line may have wrong words (names, attacks, etc).")
    else:
        st.success("✅ Confidence looks okay.")

    # show raw + auto
    st.write(f"**Whisper (original transcript):** {whisper_line}")
    st.write(f"**Auto (English subtitle):** {auto_line}")

    if len(auto_line) > max_chars:
        st.warning(f"Line is long ({len(auto_line)} chars). Consider shortening (~{max_chars}).")

    # ---- Quick tools row ----
    t1, t2, t3 = st.columns([1.2, 1.2, 2.6])

    with t1:
        # Mark for review (stored in session only)
        checked = bool(st.session_state.review_flags.get(idx, False))
        st.session_state.review_flags[idx] = st.checkbox(
            "Mark for review",
            value=checked,
            key=f"review_{idx}",
        )

    with t2:
        # quick revert to auto
        if st.button("↩️ Reset to auto", key=f"reset_{idx}"):
            chosen[idx] = auto_line
            st.rerun()

    with t3:
        # show extra debug if present
        avg_lp = seg.get("avg_logprob", None)
        nsp = seg.get("no_speech_prob", None)
        extras = []
        if isinstance(avg_lp, (int, float)):
            extras.append(f"avg_logprob={avg_lp:.2f}")
        if isinstance(nsp, (int, float)):
            extras.append(f"no_speech_prob={nsp:.2f}")
        if extras:
            st.caption(" | ".join(extras))

    st.markdown("---")

    # ---- Editable final line ----
    key = f"final_{idx}"
    default_val = chosen[idx] if (chosen and chosen[idx]) else auto_line

    final = st.text_input(
        "Final subtitle (edit if needed):",
        value=default_val,
        key=key
    )

    chosen[idx] = final.strip() if final.strip() else auto_line

    # ---- Navigation ----
    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        if st.button("⬅️ Prev", disabled=(idx == 0), key=f"prev_{idx}"):
            st.session_state.idx -= 1
            st.rerun()

    with c2:
        if st.button("Next ➡️", disabled=(idx >= len(segments) - 1), key=f"next_{idx}"):
            st.session_state.idx += 1
            st.rerun()

    with c3:
        done = sum(1 for x in chosen if x)
        marked = sum(1 for v in st.session_state.review_flags.values() if v)
        st.write(f"✅ Done: {done}/{len(segments)}  |  🏷️ Marked: {marked}")

    return chosen, st.session_state.idx


def load_segments_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_chosen_json(segments, chosen, out_path: str):
    chosen_segments = []
    for i, s in enumerate(segments):
        auto_en = (s.get("text", "") or "").strip()
        raw_txt = (s.get("raw_text", "") or "").strip()
        final = ((chosen[i] or "").strip() or auto_en)

        # ✅ learn if user changed something
        if final and auto_en and final.lower() != auto_en.lower():
            remember_phrase(auto_en=auto_en, final_en=final, raw_text=raw_txt)

        chosen_segments.append({**s, "text": final})

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chosen_segments, f, ensure_ascii=False, indent=2)
    return chosen_segments
