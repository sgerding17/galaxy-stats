# video2log — draft game logs from game film

Generates a **first-cut** Galaxy game log from a game video using Google's
Gemini API. The output is a draft in the same format as the files in
`game_logs/` — expect to review and correct it by hand; the goal is to replace
typing a log from scratch, not to replace you.

## How it works

```
YouTube video ──(yt-dlp)──▶ game.mp4 ──(Files API upload)──▶ Gemini
                                                               │
   Pass 1: "watch" the video in ~10-minute segments and emit   │
           timestamped JSON observations (shots, rebounds,     │
           scoreboard readings, substitutions, ...)            │
                                                               ▼
   Pass 2: compile all observations into the log grammar (video2log/GRAMMAR.md)
                                                               │
                                                               ▼
   Pass 3: validate with the real parser (scripts/stats.py); feed any
           assertion failures back to Gemini for up to 3 repair rounds
                                                               │
                                                               ▼
                                                         draft game log
```

## One-time setup

### 1. Python environment

**Python 3.10 or newer is required** (both `google-genai` and current `yt-dlp`
need it). Check first:

```sh
python3 --version
```

If that prints 3.9 or older, install a newer Python (`brew install
python@3.12` on macOS, `sudo apt install python3.12 python3.12-venv` on
Debian/Ubuntu, or use pyenv) and substitute `python3.12` for `python3` below.

From the repo root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r video2log/requirements.txt
```

Also install **ffmpeg** if you don't have it (`brew install ffmpeg` on macOS,
`sudo apt install ffmpeg` on Debian/Ubuntu). It provides `ffprobe`, which the
pipeline uses to read the video duration, and yt-dlp uses it to merge
audio+video. (Without it, pass `--duration-minutes` to `generate_log.py`.)

### 2. Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/) and sign in with any
   Google account (it does **not** need to be the account that owns the
   YouTube videos).
2. Click **Get API key** → **Create API key**. This creates a key tied to a
   Google Cloud project (AI Studio can create the project for you).
3. Put the key in your environment:

   ```sh
   export GEMINI_API_KEY="your-key-here"
   ```

   Add that line to your `~/.bashrc` / `~/.zshrc` to make it permanent. Treat
   the key like a password — don't commit it to the repo.

4. **Billing:** there is a free tier, but video processing burns tokens fast
   (roughly 300 tokens per second of video at default resolution — a 40-minute
   game is several hundred thousand input tokens). You will likely need to
   enable billing on the key's Google Cloud project: in AI Studio, open the
   API-keys page and follow the "set up billing" link for your project.
   Ballpark cost: **a few dollars per game** at the default settings; more if
   you raise `--fps` or `--media-resolution`.

### 3. About unlisted YouTube videos

The Gemini API can ingest YouTube URLs directly, **but only public videos —
unlisted (and private) videos are rejected**. Since the team's videos are
unlisted, this pipeline downloads them first with `yt-dlp`, which works for
unlisted videos because having the link is sufficient. You do not need to
control or log in to the YouTube account.

Two notes on that:
- Downloading is technically against YouTube's Terms of Service, so get the
  account owner's OK first — for team film this is normally a formality.
- If a download fails with an age/region/membership wall, the video may
  actually be private rather than unlisted; only the account owner can fix
  that.

## Generating a draft log

```sh
# 1. Download the video (skip if you already have a local file)
python3 video2log/download_video.py "https://www.youtube.com/watch?v=VIDEO_ID" -o game.mp4

# 2. Generate the draft (this is the slow, costs-money step)
python3 video2log/generate_log.py game.mp4 -o draft.log \
    --team-hint "Galaxy wears the dark jerseys"

# 3. Check it parses (generate_log.py already does this, but it's re-runnable)
python3 video2log/validate_log.py draft.log

# 4. If you also kept a log by hand, score the draft against it
python3 video2log/eval_log.py draft.log game_logs/20260524.Tigers_Gold_Fifth_Place.Shooting_Stars

# 5. A parsing draft works with all the existing tooling
python3 scripts/print_box_score.py draft.log
```

### Useful flags for `generate_log.py`

| Flag | Default | Notes |
|---|---|---|
| `--team-hint` | — | Free text shown to the model. Jersey colors, scoreboard location, "clock not visible on camera", etc. The single cheapest way to improve accuracy. |
| `--fps` | 1.0 | Frames per second the model sees. Raise to 2-3 if steals/blocks/rebound attribution are bad. Token cost scales linearly. |
| `--media-resolution` | medium | `high` is much better at reading jersey numbers and the scoreboard, at ~2x the cost of medium. Try `high` if attribution is wrong. |
| `--segment-minutes` | 10 | Video minutes per request. Smaller segments = more requests but better attention to detail. |
| `--model` | `gemini-3-pro-preview` | Or set `GEMINI_MODEL`. Model names change as Google ships new versions — if you get a 404, list current models at [AI Studio](https://aistudio.google.com/) and pass the new ID. |
| `--observations-out` | — | Saves the raw pass-1 JSON. Useful for debugging whether errors come from *seeing* (pass 1) or *compiling* (pass 2). |
| `--observations-in` | — | Skips the (expensive) video pass and compiles a log from previously saved observations. Use to iterate on the compile step or try a different `--model` for it at near-zero cost. |
| `--video-start-minute` / `--video-end-minute` | full video | Process only a slice of the video. Cheap way to A/B test fps/resolution settings on the first 10 minutes before paying for a full game. |

### Tuning recipe

Generate against a game you have a hand-kept log for, then look at
`eval_log.py`'s box-score diff and fix the worst failure mode first:

1. **Scores assigned to the wrong team** → the scoreboard calibration failed.
   Add a `--team-hint` like `"Galaxy is the HOME score on the scoreboard"`.
2. **Missing steals/blocks/turnovers** → raise `--fps` to 2-3 (cost scales
   linearly with fps).
3. **Wrong player attribution** → `--media-resolution high` (about 2x cost).
4. **Counts roughly right but the log won't validate** → re-run the compile
   step alone with a stronger model:
   `--observations-in obs.json --model gemini-3.1-pro-preview`
   (save `--observations-out obs.json` on the video pass to enable this).

### Iterating without re-uploading

Uploads are cached: Gemini keeps uploaded files for 48 hours, and the script
writes a `<video>.gemini_upload.json` sidecar next to the video recording the
upload. Re-runs within 48 hours reuse the upload and skip straight to the
model calls. Even without the sidecar (e.g. a previous run was killed), the
script scans your existing Gemini uploads for one matching the video's
filename and size and adopts it. Delete the sidecar AND the server-side file
to truly force a re-upload — list and delete uploads with:

```sh
python3 -c "
from google import genai
client = genai.Client()
for f in client.files.list():
    print(f.name, f.display_name, f.size_bytes, f.state.name)
    # client.files.delete(name=f.name)  # uncomment to delete
"
```

## What to expect from a draft

Roughly in descending order of reliability:

1. **Score and made baskets** — good, because the model cross-checks against
   the scoreboard.
2. **Shot attempts, free throws, rebounds** — decent.
3. **Player attribution (who shot/rebounded)** — depends entirely on how
   legible jersey numbers are in the footage. Try `--media-resolution high`.
4. **Steals, blocks, turnovers** — fair; fast plays at 1 fps get missed, so
   raise `--fps` if these matter.
5. **Assists, lineups (`ig`), jump-ball bookkeeping** — weakest; expect to fix
   these by hand. Substitutions in particular are hard to spot on game film.

The validator guarantees a clean draft *parses*, not that it's *correct* —
`eval_log.py`'s box-score diff against a hand-kept log is the real quality
measure. If you try a game we already have a log for, that diff tells you
whether the pipeline is worth running on new games.

## Troubleshooting

- **`No matching distribution found for yt-dlp` (or `google-genai`)** — your
  Python is older than 3.10; pip hides packages that need a newer Python. See
  setup step 1.
- **`GEMINI_API_KEY is not set`** — see setup step 2; remember `export`.
- **404 / model not found** — the model ID has rotated. The script checks the
  model before doing any work and prints the models your key can use; pass one
  of those with `--model` (or set `GEMINI_MODEL` in your environment so you
  don't have to repeat it).
- **429 / quota errors** — the free tier is too small for video; enable
  billing (setup step 2.4), or wait and retry.
- **Upload fails / file too large** — the Files API caps files at 2 GB.
  Shrink the video first:
  `ffmpeg -i game.mp4 -vf scale=-2:720 -c:v libx264 -crf 28 -c:a copy small.mp4`
- **Draft never passes validation** — save it anyway (the script does), then
  run `validate_log.py` and fix the remaining lines by hand; they're usually
  missing rebounds or possession mismatches near the end of the file.
