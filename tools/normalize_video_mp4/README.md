# normalize_video_mp4

Normalizes a downloaded movie or episode into an `.mp4` file and embeds external subtitles as selectable tracks.

> Integration status: this working standalone utility was imported into
> Subtitles Bridge without changing its Python implementation. It will be
> covered by characterization tests and split into focused modules before it is
> connected to the batch pipeline.

The subtitles are not burned into the image. Players such as VLC should let you choose Spanish, English, another embedded subtitle track, or disable subtitles.

## Recent update

The script can now preserve compatible embedded text subtitles and select the
default audio track by language. This was added so remuxing a multilingual video
does not discard its existing subtitles or leave an unintended language as the
default audio in VLC.

## Requirements

- `ffmpeg` and `ffprobe` available in the shell.
- No Python virtual environment is needed; the script uses only the Python standard library and calls `ffmpeg`.

## Behavior

- Accepts either a video file or a folder.
- The script location and the media location are independent. You can run the script
  from `/path/A/normalize_video_mp4.py` and pass videos/subtitles from another
  folder such as `/path/B/Downloads/movie.mkv`.
- If a folder is provided, it selects the largest non-sample video inside it.
  This is useful for a single movie folder, but it is not a batch mode.
- When scanning a folder, it ignores files that already look like generated outputs, such as `*.normalized.mp4`.
- If subtitle files are not passed explicitly, it includes all `.srt`, `.ass`, `.ssa`, and `.vtt` files next to the selected video.
- If the input is already `.mp4`, it copies the existing video and audio streams without recompressing them, then adds the subtitle tracks.
- Existing subtitle tracks embedded in the input video are omitted by default.
  Pass `--preserve-embedded-subtitles` to retain compatible text subtitle
  tracks and convert them to MP4 `mov_text` tracks.
- If the input file already looks like `*.normalized.mp4`, the script stops unless you choose an explicit `--output` path.
- If the input is not `.mp4`, it creates an `.mp4` with H.264 video, AAC audio, and `mov_text` subtitle tracks.
- This is not a simple file extension rename. The script calls `ffmpeg` to create
  a new MP4 container. With `--video-codec copy --audio-codec copy`, the video
  and audio streams are copied without recompression, while subtitles are added
  as selectable MP4 subtitle tracks.
- Each subtitle becomes a separate selectable track in the output `.mp4`.
- `--default-audio eng` (or another language/track number) changes which audio
  VLC selects initially without removing the other audio tracks.
- Detects common subtitle language names in filenames, including `Spanish`, `Español`, `Espanol`, `spa`, `es`, `English`, `Inglés`, `Ingles`, `eng`, and `en`.
- Writes a new output file; it does not replace an existing file unless `--overwrite` is used.
- By default, output files are written next to the input video. For a non-MP4
  input such as `episode.mkv`, the default output is `episode.mp4`.

## Usage

Preview what would happen without creating a file:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py --dry-run "/path/to/movie-folder"
```

Normalize a folder containing one video and one or more subtitles:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py "/path/to/movie-folder"
```

Run the script from one location while processing media from another location:

```bash
/path/to/subtitles-srt-bridge/tools/normalize_video_mp4/normalize_video_mp4.py \
  "/Users/jd/Downloads/Movie.Folder/Movie.mkv" \
  "/Users/jd/Downloads/Movie.Folder/Movie.es.srt" \
  "/Users/jd/Downloads/Movie.Folder/Movie.en.srt"
```

Embed Spanish and English subtitles explicitly:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py "/path/to/movie.avi" \
  "/path/to/movie.es.srt" \
  "/path/to/movie.en.srt" \
  --language spa \
  --language eng \
  --title "Spanish" \
  --title "English"
```

Add subtitles to an existing `.mp4` without recompressing video or audio:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py "/path/to/movie.mp4" \
  "/path/to/movie.es.srt" \
  "/path/to/movie.en.srt"
```

Add subtitles to an `.mkv` as an `.mp4` without recompressing video or audio:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py \
  --video-codec copy \
  --audio-codec copy \
  "/path/to/episode.mkv" \
  "/path/to/episode.es.srt" \
  "/path/to/episode.en.srt" \
  --language spa \
  --language eng \
  --title "Spanish" \
  --title "English"
```

Preserve embedded text subtitles, make English the default audio, and make the
first external subtitle (English in this example) the default subtitle:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py \
  --video-codec copy \
  --audio-codec copy \
  --preserve-embedded-subtitles \
  --default-audio eng \
  --default-subtitle first \
  --language eng \
  --language spa \
  --title "English" \
  --title "Spanish" \
  "/path/to/episode.mkv" \
  "/path/to/episode.en.srt" \
  "/path/to/episode.es.srt"
```

Normalize a season or folder with multiple episodes by running the script once
per episode. Passing the season folder directly processes only one selected
video, not the whole season:

```bash
SCRIPT="/path/to/subtitles-srt-bridge/tools/normalize_video_mp4/normalize_video_mp4.py"
MEDIA_DIR="/Users/jd/Downloads/Show.S01"

for ep in 01 02 03 04 05 06 07 08; do
  "$SCRIPT" \
    --video-codec copy \
    --audio-codec copy \
    --language spa \
    --language eng \
    --title "Spanish" \
    --title "English" \
    "$MEDIA_DIR/Show.S01E${ep}.mkv" \
    "$MEDIA_DIR/Show.S01E${ep}.es.srt" \
    "$MEDIA_DIR/Show.S01E${ep}.en.srt"
done
```

Choose a custom output path:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py "/path/to/movie-folder" \
  --output "/path/to/Movie.normalized.mp4"
```

Replace an existing output file:

```bash
./tools/normalize_video_mp4/normalize_video_mp4.py "/path/to/movie-folder" --overwrite
```

## Notes

In the context of this script, "embed subtitles" means adding subtitle streams inside the `.mp4`. It does not permanently draw the text over the video frames.

If a subtitle filename contains multiple language-looking tokens, for example
`en[sdh].es.srt`, pass `--language` and `--title` explicitly so players such as
VLC show the tracks with the intended names.

Use `--dry-run` first when testing a new download layout. It prints the exact `ffmpeg` command before any output file is created.

## Embedded subtitle compatibility

`--preserve-embedded-subtitles` is intended for text tracks such as SubRip/SRT.
MP4 uses `mov_text`, so bitmap subtitle formats such as PGS cannot be preserved
with this option without converting or extracting them separately.
