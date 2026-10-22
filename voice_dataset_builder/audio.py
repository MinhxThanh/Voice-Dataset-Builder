"""Audio helpers built on ffmpeg/ffprobe (+ optional Demucs denoise)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

# Sensible bounds for cleaning knobs exposed in the UI.
LUFS_MIN, LUFS_MAX = -36.0, -9.0       # EBU R128 / streaming sweet spot
SILENCE_DB_MIN, SILENCE_DB_MAX = -60.0, -20.0
HIGHPASS_HZ_DEFAULT = 80               # voice-friendly DC + rumble cut


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise RuntimeError(
            f"`{tool}` not found on PATH. Install ffmpeg (which bundles {tool})."
        )
    return path


def probe_duration(path: Path) -> float:
    ffprobe = _require("ffprobe")
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{proc.stderr}")
    duration = (json.loads(proc.stdout).get("format") or {}).get("duration")
    if duration is None:
        raise RuntimeError(f"ffprobe returned no duration for {path}")
    return float(duration)


def _codec_for_bits(sample_width_bits: int) -> str:
    return {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}[sample_width_bits]


def _build_filters(
    loudnorm: bool,
    loudnorm_lufs: float,
    remove_silence: bool,
    silence_threshold_db: float = -45.0,
    highpass_hz: Optional[int] = None,
    loudnorm_measured: Optional[dict] = None,
) -> List[str]:
    filters: List[str] = []
    if highpass_hz:
        # Single-pole high-pass: cheap, transparent, removes DC + rumble so
        # loudnorm's integrated measurement isn't biased by inaudible energy.
        filters.append(f"highpass=f={int(highpass_hz)}")
    if remove_silence:
        # Trim leading + trailing near-silence (keeps internal pauses).
        # RMS with a 20 ms window is more forgiving on transients than peak.
        th = f"{silence_threshold_db:.1f}dB"
        trim = (
            f"silenceremove=start_periods=1:start_silence=0.1:start_threshold={th}:"
            f"detection=rms:window=0.02"
        )
        filters.append(f"{trim},areverse,{trim},areverse")
    if loudnorm:
        base = f"loudnorm=I={loudnorm_lufs:.1f}:LRA=7:TP=-2"
        if loudnorm_measured:
            # Second pass: feed in measurements from pass 1 so ffmpeg hits the
            # target precisely (linear-mode normalization).
            m = loudnorm_measured
            base += (
                f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                f"offset={m['target_offset']}:linear=true:print_format=summary"
            )
        filters.append(base)
    return filters


def _measure_loudnorm(
    ffmpeg: str,
    src: Path,
    start: float,
    duration: float,
    sample_rate: int,
    channels: int,
    loudnorm_lufs: float,
    silence_filters: List[str],
) -> Optional[dict]:
    """Run loudnorm in analyze mode and return the measured stats, or None."""
    pre = ",".join(silence_filters) + "," if silence_filters else ""
    af = (
        f"{pre}loudnorm=I={loudnorm_lufs:.1f}:LRA=7:TP=-2:print_format=json"
    )
    cmd = [
        ffmpeg, "-hide_banner", "-nostats",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
        "-ar", str(sample_rate), "-ac", str(channels),
        "-af", af, "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # ffmpeg writes the JSON block to stderr.
    text = proc.stderr
    try:
        start_brace = text.rindex("{")
        end_brace = text.rindex("}") + 1
        return json.loads(text[start_brace:end_brace])
    except (ValueError, json.JSONDecodeError):
        return None


def extract_clip(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    sample_rate: int,
    channels: int,
    sample_width_bits: int,
    loudnorm: bool = True,
    loudnorm_lufs: float = -23.0,
    remove_silence: bool = False,
    silence_threshold_db: float = -45.0,
    highpass_hz: Optional[int] = None,
    loudnorm_two_pass: bool = False,
) -> None:
    """Cut [start, end] from ``src`` into a cleaned mono WAV at ``dst``."""

    ffmpeg = _require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.0, end - start)

    measured = None
    if loudnorm and loudnorm_two_pass and duration > 0:
        # Build the pre-loudnorm chain (silence trim + highpass) so the
        # measurement matches what the final clip will contain.
        pre = _build_filters(
            loudnorm=False,
            loudnorm_lufs=loudnorm_lufs,
            remove_silence=remove_silence,
            silence_threshold_db=silence_threshold_db,
            highpass_hz=highpass_hz,
        )
        measured = _measure_loudnorm(
            ffmpeg, src, start, duration, sample_rate, channels,
            loudnorm_lufs, pre,
        )

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
        "-ar", str(sample_rate), "-ac", str(channels),
        "-c:a", _codec_for_bits(sample_width_bits),
    ]
    filters = _build_filters(
        loudnorm=loudnorm,
        loudnorm_lufs=loudnorm_lufs,
        remove_silence=remove_silence,
        silence_threshold_db=silence_threshold_db,
        highpass_hz=highpass_hz,
        loudnorm_measured=measured,
    )
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd.append(str(dst))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg clip extraction failed:\n{proc.stderr}")


def to_wav(
    src: Path, dst: Path, sample_rate: int, channels: int, sample_width_bits: int
) -> None:
    ffmpeg = _require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-ar", str(sample_rate), "-ac", str(channels),
        "-c:a", _codec_for_bits(sample_width_bits), str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed:\n{proc.stderr}")


def have_demucs() -> bool:
    if shutil.which("demucs"):
        return True
    try:
        import demucs  # noqa: F401

        return True
    except Exception:
        return False


def denoise_demucs(
    src: Path,
    work_dir: Path,
    log=print,
    model: str = "htdemucs",
    device: Optional[str] = None,
) -> Path:
    """Isolate vocals with Demucs (htdemucs 2-stem). Returns the vocals file.

    Falls back to returning ``src`` unchanged if Demucs is unavailable or fails,
    so the pipeline never hard-stops on an optional cleaning step.
    """

    if not have_demucs():
        log("[denoise] Demucs not installed; skipping. `pip install demucs` to enable.")
        return src

    out_dir = work_dir / "demucs"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["demucs", "-n", model, "--two-stems", "vocals", "-o", str(out_dir)]
    if device and device != "auto":
        cmd += ["-d", device]
    cmd.append(str(src))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"[denoise] Demucs failed, using original audio:\n{proc.stderr.strip()[:300]}")
        return src

    matches = list(out_dir.glob("**/vocals.wav"))
    if not matches:
        log("[denoise] Demucs produced no vocals stem; using original audio.")
        return src
    log(f"[denoise] Demucs ({model}) vocals isolated: {matches[0].name}")
    return matches[0]
