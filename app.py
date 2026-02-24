import streamlit as st
import time

st.set_page_config(page_title="AI Subtitle & Dubbing Tool", page_icon="🎬")

st.title("🎬 AI Subtitle & Multilingual Dubbing Tool")
st.write("Automatically generate subtitles, translate them, and create AI voice dubbing.")

st.markdown("---")

uploaded_file = st.file_uploader("Upload your video file", type=["mp4", "mov", "avi"])

if uploaded_file:
    st.success("Video uploaded successfully!")

    st.subheader("Step 1: Generating Subtitles...")
    with st.spinner("Transcribing audio using AI..."):
        time.sleep(2)

    sample_subtitles = """1
00:00:01,000 --> 00:00:04,000
Hello and welcome to our video.

2
00:00:05,000 --> 00:00:08,000
This content is generated using AI technology.
"""

    st.text_area("Generated Subtitles (SRT format)", sample_subtitles, height=200)

    st.download_button(
        label="Download Subtitles (.srt)",
        data=sample_subtitles,
        file_name="subtitles.srt",
        mime="text/plain"
    )

    st.markdown("---")
    st.subheader("Step 2: Translating Subtitles...")

    language = st.selectbox(
        "Select target language",
        ["Spanish", "French", "German", "Japanese", "Arabic"]
    )

    if st.button("Translate Subtitles"):
        with st.spinner("Translating using AI model..."):
            time.sleep(2)

        translated_text = f"(Translated to {language})\n\nHola y bienvenidos a nuestro video."
        st.text_area("Translated Subtitles", translated_text, height=150)

    st.markdown("---")
    st.subheader("Step 3: Generate AI Voice Dubbing")

    if st.button("Generate AI Dubbing"):
        with st.spinner("Creating AI voiceover..."):
            time.sleep(3)

        st.success("AI Dubbing generated successfully!")
        st.audio("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3")

else:
    st.info("Please upload a video file to begin.")
