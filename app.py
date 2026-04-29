# app.py
import os
import json
import time
import streamlit as st

from pipeline import run_pipeline, make_dubbed_video
from subtitle_cleaner import clean_subtitle_text
from editor_ui import render_editor

from ass_utils import segments_to_ass
from pipeline import burn_selected_subtitle

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------- PAGE ----------------
st.set_page_config(
    page_title="AI Anime Subtitle Generator",
    page_icon="🎌",
    layout="centered"
)

# ---------------- STYLING ----------------
st.markdown("""
<style>

/* GLOBAL */
.stApp {
    background: linear-gradient(180deg, #0b0f1a 0%, #111827 100%);
    color: #e5e7eb;
    font-family: Inter, system-ui;
}

.block-container {
    max-width: 900px;
}

/* HEADER */
h1 {
    font-weight: 700;
}

/* CARD */
.card {
    background: #0f172a;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 18px;
    border: 1px solid rgba(255,255,255,0.06);
}

/* BUTTON */
.stButton>button {
    background: linear-gradient(90deg, #ef4444, #f97316);
    color: white;
    border-radius: 12px;
    font-weight: 600;
    height: 3em;
}

/* SELECT */
.stSelectbox div[data-baseweb="select"] {
    background: #111827 !important;
    border-radius: 10px;
}

/* 🔥 FINAL UPLOAD FIX */
div[data-testid="stFileUploader"] {
    background: #ffffff !important;
    border-radius: 16px !important;
    padding: 20px !important;
    border: 2px dashed #f97316 !important;
}

/* text */
div[data-testid="stFileUploader"] * {
    color: #111827 !important;
    font-weight: 500;
}

/* button */
div[data-testid="stFileUploader"] button {
    background: linear-gradient(90deg, #f97316, #ef4444) !important;
    color: white !important;
    font-weight: bold !important;
    border-radius: 10px !important;
    border: none !important;
}

/* remove fade */
div[data-testid="stFileUploader"] button:disabled {
    opacity: 1 !important;
}

</style>
""", unsafe_allow_html=True)

# ---------------- HEADER ----------------
st.title("🎌 AI Anime Subtitle Generator")
st.caption("AI subtitles • Human editing • Multi-language • AI dubbing")

# System status (nice UX)
st.markdown("""
<div style='
padding:10px;
border-radius:10px;
background: rgba(16,185,129,0.1);
border:1px solid rgba(16,185,129,0.3);
margin-bottom:15px;
'>
🟢 System ready — AI subtitle engine active
</div>
""", unsafe_allow_html=True)


# ---------------- CONFIG ----------------
LANG_CHOICES = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "Bengali": "bn",
    "Japanese": "ja"
}
MODEL_CHOICES = {"Small (fast)": "small", "Medium": "medium", "Large": "large"}
PRESET_CHOICES = {
    "Auto": "auto",
    "Dub optimized": "dub_en",
    "Anime (JP Raw)": "jp_raw"
}
DUB_CHOICES = {
    "English Male": "en-GB-RyanNeural",
    "English Female": "en-GB-SoniaNeural",
    "Japanese Male": "ja-JP-KeitaNeural"
}
# -------- HOW IT WORKS --------
st.markdown("""
<div class="card">
<h4>📌 How it works</h4>
<ol style="line-height:1.8;">
<li>Upload your anime video</li>
<li>Generate subtitles using AI</li>
<li>Edit subtitles manually (optional)</li>
<li>Export subtitles or create dub</li>
</ol>
</div>
""", unsafe_allow_html=True)

# -------- TIPS --------
st.markdown("""
<div class="card">
<h4>⚙️ Tips for best results</h4>
<ul style="line-height:1.8;">
<li>Use <b>Medium / Large</b> model for higher accuracy</li>
<li>Use <b>Small</b> model for faster processing</li>
<li>Use <b>Anime (JP Raw)</b> for Japanese dialogue</li>
<li>Edit subtitles for best final output</li>
</ul>
</div>
""", unsafe_allow_html=True)

# ---------------- STATE ----------------
if "segments" not in st.session_state:
    st.session_state.segments = None
if "chosen" not in st.session_state:
    st.session_state.chosen = None
if "outputs" not in st.session_state:
    st.session_state.outputs = None

# ---------------- HELPERS ----------------
def build_final_segments(segs, chosen):
    out = []
    for i, s in enumerate(segs):
        text = chosen[i] if chosen and chosen[i] else s.get("text", "")
        s["text"] = clean_subtitle_text(text)
        out.append(s)
    return out

# ---------------- TABS ----------------
tab1, tab2, tab3 = st.tabs(["🎬 Generate", "✍️ Editor", "🗣️ Dub"])


# ================= TAB 1 =================
with tab1:

    # SETTINGS
    st.markdown('<div class="card">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        lang = LANG_CHOICES[st.selectbox("Subtitle Language", LANG_CHOICES)]
        model = MODEL_CHOICES[st.selectbox("Model", MODEL_CHOICES)]

    with col2:
        preset = PRESET_CHOICES[st.selectbox("Preset", PRESET_CHOICES)]
        boost = st.checkbox("Boost Dialogue", True)

    st.markdown('</div>', unsafe_allow_html=True)

    # UPLOAD
    st.markdown('<div class="card">', unsafe_allow_html=True)

    st.subheader("📤 Upload Video")

    st.markdown(""" <div style=" padding:12px; 
    border-radius:10px; 
    background: rgba(249,115,22,0.1);
     border:1px solid rgba(249,115,22,0.3);
      margin-bottom:10px; "> 📌 Click the box below to upload your video </div> """,
     unsafe_allow_html=True)

    file = st.file_uploader("", type=["mp4","mkv","mov","avi"])

    st.caption("Supported: MP4, MKV, MOV, AVI")

    if file:
        st.success(f"✅ Selected: {file.name}")

        path = os.path.join(UPLOAD_DIR, file.name)
        with open(path, "wb") as f:
            f.write(file.read())

        st.video(path)

        st.success("🎬 Video ready — click below to generate subtitles")

        if st.button("🚀 Generate Subtitles"):
            start = time.time()

            with st.spinner("Processing..."):
                outputs = run_pipeline(
                    path,
                    mode="draft",
                    target_lang=lang,
                    model_size=model,
                    preset=preset,
                    boost_dialogue=boost,
                )

            st.session_state.outputs = outputs

            with open(outputs["segments_json"], encoding="utf-8") as f:
                segs = json.load(f)

            st.session_state.segments = segs
            st.session_state.chosen = [None] * len(segs)

            st.success(f"✅ Completed in {time.time()-start:.2f}s")

    st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 2 =================
with tab2:
    st.subheader("✍️ Subtitle Editor")

    if st.session_state.segments:

        st.session_state.chosen, _ = render_editor(
            st.session_state.segments,
            st.session_state.chosen,
            max_chars=80
        )

        st.markdown("---")
        st.subheader("🎬 Export Options")

        if st.button("🎬 Generate Video with Subtitles"):

            start = time.time()

            # 1️⃣ Build final cleaned subtitles
            final_segments = build_final_segments(
                st.session_state.segments,
                st.session_state.chosen
            )

            with st.spinner("Burning subtitles into video..."):

                # 2️⃣ Create subtitle file (.ASS)
                ass_path = os.path.join(OUTPUT_DIR, "final_subtitles.ass")
                segments_to_ass(final_segments, ass_path)

                # 3️⃣ Burn subtitles into video
                final_video = burn_selected_subtitle(
                    st.session_state.outputs["video"],
                    ass_path
                )

            st.success("✅ Subtitles added inside video!")

            # 🎥 Preview
            st.video(final_video)

            # ⬇ Download
            with open(final_video, "rb") as f:
                st.download_button(
                    "⬇ Download Subtitled Video",
                    f,
                    file_name="subtitled_video.mp4"
                )

            st.info(f"Time: {time.time()-start:.2f}s")

    else:
        st.info("Generate subtitles first.")

# ================= TAB 3 =================
with tab3:
    st.subheader("🗣️ AI Dubbing")

    if st.session_state.segments and st.session_state.outputs:

        voice = st.selectbox("Voice", list(DUB_CHOICES))

        if st.button("🎤 Generate Dub"):

            # ✅ Step 1: prepare subtitles
            base = build_final_segments(
                st.session_state.segments,
                st.session_state.chosen
            )

            start = time.time()

            with st.spinner("Generating dub..."):

                # 🔥 Keep timing (important for sync)
                for seg in base:
                    seg["duration"] = seg["end"] - seg["start"]

                # 1️⃣ Generate dub video
                dub_video = make_dubbed_video(
                    st.session_state.outputs["video"],
                    base_wav=st.session_state.outputs["wav"],
                    segments=base,
                    voice=DUB_CHOICES[voice],
                    keep_original=False
                )

                # 2️⃣ Create subtitle file
                ass_path = os.path.join(OUTPUT_DIR, "dub_subtitles.ass")
                from ass_utils import segments_to_ass
                segments_to_ass(base, ass_path)

                # 3️⃣ Burn subtitles into video
                from pipeline import burn_selected_subtitle
                final_video = burn_selected_subtitle(
                    dub_video,
                    ass_path
                )

            st.success("🎬 Dub + Subtitles perfectly synced")
            st.video(final_video)
            st.info(f"Time: {time.time()-start:.2f}s")

    else:
        st.info("Generate subtitles first.")