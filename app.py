# app.py
import os
import json
import streamlit as st

from pipeline import (
    run_pipeline,
    burn_selected_subtitle,
    make_dubbed_video_burned_subs,   # ✅ this exists in your pipeline.py
)

from ass_utils import segments_to_ass
from subtitle_cleaner import clean_subtitle_text
from editor_ui import render_editor, load_segments_json, save_chosen_json

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

st.set_page_config(page_title="AI Anime Subtitle Generator", page_icon="🎌", layout="centered")
st.title("🎌 AI Anime Subtitle Generator")
st.caption("Universal audio → subtitles + Human Override (single line) + Optional Dub")

LANG_CHOICES = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Arabic": "ar",
    "Italian": "it",
}

MODEL_CHOICES = {
    "Small (fast)": "small",
    "Medium (better)": "medium",
    "Large (best accuracy)": "large",
}

PRESET_CHOICES = {
    "Auto (recommended)": "auto",
    "English dub priority (exact words)": "dub_en",
    "Japanese raw priority (better translation)": "jp_raw",
}

# ✅ voice pack (future-proof: male/female/default)
VOICE_CHOICES = {
    "UK (Male Ryan + Female Sonia)": {
        "male": "en-GB-RyanNeural",
        "female": "en-GB-SoniaNeural",
        "default": "en-GB-RyanNeural",
    },
    "US (Male Guy + Female Jenny)": {
        "male": "en-US-GuyNeural",
        "female": "en-US-JennyNeural",
        "default": "en-US-GuyNeural",
    },
}


def init_state():
    defaults = {
        "outputs": None,
        "segments": None,
        "chosen": None,
        "idx": 0,
        "ass_path": None,
        "final_video": None,
        "dub_video": None,
        "dub_video_edited": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

tab1, tab2, tab3 = st.tabs(["🎬 Generate", "✍️ Editor", "🗣️ Dub"])


# ---------------- TAB 1: Generate ----------------
with tab1:
    st.markdown("""
### Instructions
1. Upload a video (anime, dub, any language — no hardcoded subs)
2. Choose output subtitle language + quality options
3. Click **Generate Subtitles**
4. Go to **Editor** tab and adjust lines if needed
5. Create subtitle file and burn video
(Optional: go to **Dub** tab to create English voice-over + burned subtitles.)
""")

    colA, colB = st.columns(2)
    with colA:
        out_lang_name = st.selectbox("Subtitle output language", list(LANG_CHOICES.keys()), index=0)
        target_lang = LANG_CHOICES[out_lang_name]

        model_name = st.selectbox("Whisper accuracy", list(MODEL_CHOICES.keys()), index=0)
        model_size = MODEL_CHOICES[model_name]

    with colB:
        preset_name = st.selectbox("Preset", list(PRESET_CHOICES.keys()), index=0)
        preset = PRESET_CHOICES[preset_name]

        boost_dialogue = st.checkbox("Boost dialogue (recommended)", value=True)
        st.caption("If audio sounds distorted, turn this OFF.")

    video_file = st.file_uploader("Upload video (NO hardcoded subs)", type=["mp4", "mov", "mkv", "avi"])

    if video_file:
        video_path = os.path.join(UPLOAD_DIR, video_file.name)
        if not os.path.exists(video_path):
            with open(video_path, "wb") as f:
                f.write(video_file.read())

        st.video(video_path)

        if st.button("Generate Subtitles"):
            with st.spinner("Extracting audio + transcribing + timing align..."):
                outputs = run_pipeline(
                    video_path,
                    mode="draft",
                    target_lang=target_lang,
                    model_size=model_size,
                    preset=preset,
                    boost_dialogue=boost_dialogue,
                )

            st.session_state.outputs = outputs

            with open(outputs["segments_json"], "r", encoding="utf-8") as f:
                segments = json.load(f)

            for s in segments:
                s["text"] = clean_subtitle_text(s.get("text", ""))

            st.session_state.segments = segments
            st.session_state.chosen = [None] * len(segments)
            st.session_state.idx = 0
            st.session_state.ass_path = None
            st.session_state.final_video = None
            st.session_state.dub_video = None
            st.session_state.dub_video_edited = None

            st.success("Draft ready ✅ Go to the Editor tab (optional) or Dub tab.")


# ---------------- TAB 2: Editor ----------------
with tab2:
    st.subheader("Editor Mode (single line + override)")

    default_path = st.session_state.outputs["segments_json"] if st.session_state.outputs else ""
    load_path = st.text_input("Segments JSON path (optional)", value=default_path)

    if st.button("Load Segments JSON"):
        if load_path and os.path.exists(load_path):
            segs = load_segments_json(load_path)
            for s in segs:
                s["text"] = clean_subtitle_text(s.get("text", ""))
            st.session_state.segments = segs
            st.session_state.chosen = [None] * len(segs)
            st.session_state.idx = 0
            st.session_state.ass_path = None
            st.session_state.final_video = None
            st.session_state.dub_video_edited = None
            st.success("Loaded ✅")
        else:
            st.error("Path not found. Generate first or enter a valid outputs/..._segments.json path.")

    st.markdown("---")

    if st.session_state.segments is not None:
        st.session_state.chosen, st.session_state.idx = render_editor(
            st.session_state.segments,
            st.session_state.chosen or [None] * len(st.session_state.segments),
            max_chars=80,
        )

    st.markdown("---")

    if st.session_state.segments and st.session_state.outputs:
        outputs = st.session_state.outputs
        chosen_json = outputs["chosen_json_expected"]
        ass_path = outputs["ass_will_be"]

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Save chosen JSON"):
                save_chosen_json(st.session_state.segments, st.session_state.chosen, chosen_json)
                st.success(f"Saved: {chosen_json}")

        with c2:
            if st.button("✅ Create Final Subtitle (.ass)"):
                chosen_segments = save_chosen_json(st.session_state.segments, st.session_state.chosen, chosen_json)
                segments_to_ass(chosen_segments, ass_path)
                st.session_state.ass_path = ass_path
                st.success(f"Created: {ass_path}")

    if st.session_state.ass_path and st.session_state.outputs:
        if st.button("Burn Subtitles Into Video"):
            with st.spinner("Burning subtitles into video..."):
                final_video = burn_selected_subtitle(st.session_state.outputs["video"], st.session_state.ass_path)
            st.session_state.final_video = final_video
            st.success("🎬 Final video ready!")
            st.video(final_video)


# ---------------- TAB 3: Dub (Burned subtitles = ALWAYS visible) ----------------
with tab3:
    st.subheader("Dub Mode (English voice-over) ✅ Dub + burned subtitles (always visible)")

    if not st.session_state.outputs or not st.session_state.segments:
        st.info("Generate subtitles first in the 🎬 Generate tab.")
    else:
        voice_pack_name = st.selectbox("Dub voice pack", list(VOICE_CHOICES.keys()), index=0)
        voice_pack = VOICE_CHOICES[voice_pack_name]

        keep_original = st.checkbox("Keep original audio under dub (ducked)", value=False)

        st.caption("Dub uses subtitle timing. If timing looks off, tweak subtitles first in Editor.")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("🗣️ Generate Dubbed MP4 (Auto subtitles + Burned Subs)"):
                outputs = st.session_state.outputs
                ass_path = outputs["ass_will_be"]

                # Ensure ASS exists
                if not os.path.exists(ass_path):
                    segments_to_ass(st.session_state.segments, ass_path)

                with st.spinner("Generating dub + burning subtitles into MP4..."):
                    dubbed_mp4 = make_dubbed_video_burned_subs(
                        outputs["video"],
                        base_wav=outputs["wav"],          # keep for future voice logic, ok to pass always
                        segments=st.session_state.segments,
                        voice=voice_pack,
                        ass_path=ass_path,
                        keep_original=keep_original,
                    )

                st.session_state.dub_video = dubbed_mp4
                st.success("Dubbed MP4 with subtitles ready ✅")
                st.video(dubbed_mp4)

                with open(dubbed_mp4, "rb") as f:
                    st.download_button(
                        "Download Dubbed MP4 (Subtitles Burned)",
                        data=f,
                        file_name=os.path.basename(dubbed_mp4)
                    )

        with c2:
            st.write("Optional: dub the *edited* subtitles (chosen JSON)")
            if st.button("🗣️ Generate Dubbed MP4 (EDITED subtitles + Burned Subs)"):
                outputs = st.session_state.outputs
                chosen_json = outputs["chosen_json_expected"]
                ass_path = outputs["ass_will_be"]

                if not os.path.exists(chosen_json):
                    st.error("Chosen JSON not found. Go to Editor tab and click 💾 Save chosen JSON first.")
                else:
                    chosen_segments = load_segments_json(chosen_json) or []
                    if not chosen_segments:
                        st.error("Chosen JSON is empty. Save edits first.")
                    else:
                        # Build ASS from edited segments
                        segments_to_ass(chosen_segments, ass_path)

                        with st.spinner("Generating dub from edited subtitles + burning into MP4..."):
                            dubbed2_mp4 = make_dubbed_video_burned_subs(
                                outputs["video"],
                                base_wav=outputs["wav"],
                                segments=chosen_segments,
                                voice=voice_pack,
                                ass_path=ass_path,
                                keep_original=keep_original,
                            )

                        st.session_state.dub_video_edited = dubbed2_mp4
                        st.success("Dubbed (edited) MP4 with subtitles ready ✅")
                        st.video(dubbed2_mp4)

                        with open(dubbed2_mp4, "rb") as f:
                            st.download_button(
                                "Download Dubbed MP4 (Edited Subs Burned)",
                                data=f,
                                file_name=os.path.basename(dubbed2_mp4)
                            )
