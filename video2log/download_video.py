"""Download a (possibly unlisted) YouTube video for the video2log pipeline.

Usage: python3 video2log/download_video.py YOUTUBE_URL -o game.mp4

The Gemini API can only read PUBLIC YouTube URLs natively, so unlisted videos
must be downloaded first. yt-dlp can download unlisted videos because having
the link is sufficient — make sure you have the account owner's permission.
"""
import argparse
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="YouTube URL (unlisted is fine)")
    parser.add_argument("-o", "--output", default="game.mp4")
    parser.add_argument("--max-height", type=int, default=1080,
                        help="cap video resolution (default: 1080)")
    args = parser.parse_args()

    assert shutil.which("yt-dlp"), \
        "yt-dlp not found. Install it with: pip install -r video2log/requirements.txt"

    command = [
        "yt-dlp",
        "-f", f"bv*[height<={args.max_height}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "-o", args.output,
        args.url,
    ]
    print(" ".join(command))
    sys.exit(subprocess.run(command).returncode)


if __name__ == "__main__":
    main()
