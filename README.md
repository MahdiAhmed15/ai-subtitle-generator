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

## Setup
Open a terminal in the project folder and run:

```bash
pip install -r requirements.txt
streamlit run app.py
