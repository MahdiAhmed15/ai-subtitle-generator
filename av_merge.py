import subprocess
import os


def run(cmd):
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc


def _escape_path(p: str) -> str:
    # FFmpeg filter-safe path (Windows)
    p = os.path.abspath(p)
    p = p.replace("\\", "/")
    p = p.replace(":", r"\:")
    p = p.replace("'", r"\'")
    return p


def burn_subtitles(video_in: str, ass_path: str, out_video: str):
    """
    Burn ASS subtitles cleanly into video (English only).
    No original_size. No Japanese leakage.
    """

    video_in = os.path.abspath(video_in)
    ass_path = _escape_path(ass_path)
    out_video = os.path.abspath(out_video)

    filter_arg = f"ass='{ass_path}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_in,
        "-vf", filter_arg,
        "-c:a", "copy",
        out_video
    ]

    run(cmd)
