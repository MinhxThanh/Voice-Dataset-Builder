"""Acquire audio from YouTube URLs or local files, plus optional subtitles.

YouTube increasingly forces SABR streaming, which makes audio-only formats
return HTTP 403. To stay robust we download a progressive video stream (with
an alternate player client) and convert it to mp3 with ffmpeg ourselves,
rather than relying on yt-dlp's audio-only extraction.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Player clients that still hand out working progressive URLs without a PO token.
_PLAYER_CLIENTS = "android,ios,web_safari"
# Prefer a single progressive file (has audio+video, no SABR), then fall back
# to merging, then to anything.
_FORMAT = "b[acodec!=none][vcodec!=none]/bv*+ba/b"


@dataclass
class AudioSource:
    origin: str
    title: str
    source_id: str
    audio_path: Path            # mp3 we produced
    subtitle_path: Optional[Path] = None
    input_index: int = 0


# Backwards-compatible alias.
DownloadedAudio = AudioSource


def _have_python_ytdlp() -> bool:
    try:
        import yt_dlp  # noqa: F401

        return True
    except Exception:
        return False


def _have_cli() -> bool:
    return shutil.which("yt-dlp") is not None


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError("`ffmpeg` not found on PATH. Install it (e.g. `brew install ffmpeg`).")
    return path


def _sanitize(name: str) -> str:
    keep = "-_.() "
    cleaned = "".join(ch if ch.isalnum() or ch in keep else "_" for ch in name)
    return cleaned.strip().strip(".") or "audio"


def _to_mp3(src: Path, dst: Path, sample_rate: int) -> None:
    """Convert any downloaded media (video or audio) to mono mp3."""
    ffmpeg = _require_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-ar", str(sample_rate), "-ac", "1",
        "-c:a", "libmp3lame", "-q:a", "2", str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mp3 conversion failed:\n{proc.stderr}")


def download_audio(
    url: str,
    work_dir: Path,
    sample_rate: int = 24000,
    audio_format: str = "mp3",
    want_subtitles: bool = False,
    languages: Optional[List[str]] = None,
) -> AudioSource:
    """Download a URL to a local mp3 (via video) and optionally subtitles."""

    work_dir.mkdir(parents=True, exist_ok=True)
    if _have_python_ytdlp():
        return _download_python(url, work_dir, sample_rate, want_subtitles, languages)
    if _have_cli():
        return _download_cli(url, work_dir, sample_rate, want_subtitles, languages)
    raise RuntimeError(
        "yt-dlp is not available. Install it with `pip install yt-dlp` "
        "or the standalone CLI binary."
    )


def _find_subtitle(
    work_dir: Path,
    video_id: str,
    languages: Optional[List[str]] = None,
) -> Optional[Path]:
    matches = []
    for ext in ("vtt", "srt"):
        matches.extend(sorted(work_dir.glob(f"{video_id}*.{ext}")))
    if not matches:
        return None

    wanted = [lang.lower() for lang in (languages or []) if lang]
    for lang in wanted:
        for p in matches:
            name = p.name.lower()
            if f".{lang}." in name or f".{lang}-" in name or f".{lang}_" in name:
                return p
    return matches[0]
    return None


def _find_media(work_dir: Path, video_id: str) -> Optional[Path]:
    for p in sorted(work_dir.glob(f"{video_id}.*")):
        if p.suffix.lower()[1:] not in ("vtt", "srt") and not p.name.endswith(".audio.mp3"):
            return p
    return None


def _download_python(
    url: str,
    work_dir: Path,
    sample_rate: int,
    want_subtitles: bool,
    languages: Optional[List[str]],
) -> AudioSource:
    import yt_dlp

    outtmpl = str(work_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": _FORMAT,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_args": {"youtube": {"player_client": _PLAYER_CLIENTS.split(",")}},
    }
    if want_subtitles:
        ydl_opts.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitlesformat": "vtt",
                "subtitleslangs": languages or ["en"],
            }
        )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id = info.get("id", "audio")
    title = info.get("title", video_id)
    media = _find_media(work_dir, video_id)
    if media is None:
        raise RuntimeError(f"Download succeeded but no media file found for {url}")
    mp3_path = work_dir / f"{video_id}.audio.mp3"
    _to_mp3(media, mp3_path, sample_rate)
    sub = _find_subtitle(work_dir, video_id, languages) if want_subtitles else None
    return AudioSource(
        origin=url, title=title, source_id=video_id, audio_path=mp3_path,
        subtitle_path=sub,
    )


def _download_cli(
    url: str,
    work_dir: Path,
    sample_rate: int,
    want_subtitles: bool,
    languages: Optional[List[str]],
) -> AudioSource:
    yt = shutil.which("yt-dlp")
    meta_proc = subprocess.run(
        [yt, "--no-warnings", "--dump-single-json",
         "--extractor-args", f"youtube:player_client={_PLAYER_CLIENTS}", url],
        capture_output=True, text=True,
    )
    if meta_proc.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata fetch failed for {url}:\n{meta_proc.stderr}")
    info = json.loads(meta_proc.stdout)
    video_id = info.get("id", "audio")
    title = info.get("title", video_id)

    outtmpl = str(work_dir / "%(id)s.%(ext)s")
    cmd = [
        yt, "--no-warnings", "--no-progress",
        "--extractor-args", f"youtube:player_client={_PLAYER_CLIENTS}",
        "-f", _FORMAT, "--retries", "5", "--fragment-retries", "5",
    ]
    if want_subtitles:
        cmd += [
            "--write-subs", "--write-auto-subs",
            "--sub-format", "vtt", "--sub-langs", ",".join(languages or ["en"]),
        ]
    cmd += ["-o", outtmpl, url]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed for {url}:\n{proc.stderr}")

    media = _find_media(work_dir, video_id)
    if media is None:
        raise RuntimeError(f"Download succeeded but no media file found for {url}")
    mp3_path = work_dir / f"{video_id}.audio.mp3"
    _to_mp3(media, mp3_path, sample_rate)
    sub = _find_subtitle(work_dir, video_id, languages) if want_subtitles else None
    return AudioSource(
        origin=url, title=title, source_id=video_id, audio_path=mp3_path,
        subtitle_path=sub,
    )


def ingest_local(path: str, work_dir: Path) -> AudioSource:
    p = Path(path).expanduser()
    if not p.exists():
        raise RuntimeError(f"Local source not found: {p}")
    return AudioSource(
        origin=str(p), title=p.stem, source_id=_sanitize(p.stem), audio_path=p,
        subtitle_path=None,
    )


def collect_sources(
    urls: List[str],
    local_sources: List[str],
    work_dir: Path,
    sample_rate: int = 24000,
    audio_format: str = "mp3",
    want_subtitles: bool = False,
    languages: Optional[List[str]] = None,
    input_start: int = 0,
    on_error: str = "warn",
    log=print,
) -> List[AudioSource]:
    sources: List[AudioSource] = []
    for offset, url in enumerate(urls):
        try:
            log(f"Downloading video + extracting mp3: {url}")
            source = download_audio(
                url, work_dir, sample_rate, audio_format, want_subtitles, languages
            )
            source.input_index = input_start + offset
            sources.append(source)
        except Exception as exc:  # noqa: BLE001
            if on_error == "raise":
                raise
            log(f"[warn] failed to download {url}: {exc}")
    local_start = input_start + len(urls)
    for offset, path in enumerate(local_sources):
        try:
            source = ingest_local(path, work_dir)
            source.input_index = local_start + offset
            sources.append(source)
        except Exception as exc:  # noqa: BLE001
            if on_error == "raise":
                raise
            log(f"[warn] failed to ingest {path}: {exc}")
    return sources
