# AI Anime Subtitle Generator (Prototype) – W2026203

**Student:** Md Mahdi Ahmed  
**Student ID:** W2026203  
**Module:** 6COSC023W – Computer Science Final Project (IPD Prototype)

## Overview
This prototype generates subtitles from any video audio using Whisper (Speech-to-Text + Translation) and provides:
- Draft subtitle generation
- Manual correction via an editor (human override)
- Export to .ASS subtitles and burn subtitles into the video
- Optional English dub (Text-to-Speech) using Edge-TTS

## Features (Implemented)
- Upload video (MP4/MKV/AVI/MOV)
- Auto subtitle generation from audio (universal)
- Subtitle editor (single-line override)
- Create final .ASS subtitle file
- Burn subtitles into video (FFmpeg)
- Optional: generate English dub track and mux into video

## Requirements
- Python 3.10+ recommended (works best on 3.10/3.11)
- FFmpeg installed and added to PATH

### Install FFmpeg (Windows)
1) Install FFmpeg (any standard build)
2) Add FFmpeg `bin` folder to Environment Variables -> PATH
3) Restart terminal

## Setup & Run Instructions
Vs code terminal : run - { python -m venv .venv }

windows powershell inside terminal of the folder : run it -{ .venv\Scripts\Activate } 
then -

1. Install Python (3.10 or 3.11 recommended)

2. Install dependencies:
pip install -r requirements.txt

3. Install :
 pip install deep-translator

4. Install :
  pip install streamlit

5. Run the application:
streamlit run app.py

## Important Notes
- This system runs locally due to high computational requirements (Whisper, FFmpeg)
- FFmpeg must be installed and added to system PATH
- Full functionality is demonstrated in the submitted video
