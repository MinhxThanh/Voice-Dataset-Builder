"""Configuration for the dataset build pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Output formats the pipeline can emit. "universal" = jsonl + csv + fish + sovits.
OUTPUT_FORMATS = {"jsonl", "csv", "ljspeech", "fish", "gpt-sovits", "universal"}


@dataclass
class BuildConfig:
    """All knobs for a single dataset build.

    Defaults mirror the recommended TTS dataset spec: clean mono WAV clips of
    3-12s, JSONL metadata (+ optional LJSpeech CSV / Fish / GPT-SoVITS), under
    a single speaker id.
    """

    # Inputs / outputs
    urls: List[str] = field(default_factory=list)
    local_sources: List[str] = field(default_factory=list)  # local audio/video paths
    output_dir: Path = Path("my_voice_dataset")

    # Speaker / language
    speaker_id: str = "speaker_01"
    language: Optional[str] = None  # None => let Whisper auto-detect per video

    # Audio target spec
    sample_rate: int = 24000        # 22050 or 24000 recommended
    channels: int = 1               # mono
    sample_width_bits: int = 16     # 16-bit PCM

    # Clip slicing constraints (seconds)
    min_clip_sec: float = 3.0
    max_clip_sec: float = 12.0
    merge_gap_sec: float = 0.4

    # Cleaning
    loudnorm: bool = True
    loudnorm_lufs: float = -23.0    # target integrated loudness (e.g. -14 or -23)
    loudnorm_two_pass: bool = False  # measure-then-normalize for accuracy
    remove_silence: bool = True     # trim leading/trailing silence per clip
    silence_threshold_db: float = -45.0  # quieter than this counts as silence
    highpass_hz: int = 0            # 0 disables; 60-100 Hz is typical for voice
    denoise: bool = False           # Demucs vocal isolation (optional dep)
    demucs_model: str = "htdemucs"  # htdemucs (default) or htdemucs_ft (slower)

    # Transcription
    whisper_model: str = "base"     # tiny/base/small/medium/large-v3/large-v3-turbo
    whisper_backend: str = "auto"   # auto|faster-whisper|openai-whisper
    device: str = "auto"            # auto|cpu|cuda
    compute_type: str = "auto"      # faster-whisper compute type
    initial_prompt: Optional[str] = None   # bias decoding (great for vi diacritics)
    min_confidence: Optional[float] = None  # drop segments below avg_logprob
    prefer_subtitles: bool = False  # use YouTube CC/subs when available

    # Dataset split / output options
    val_ratio: float = 0.1
    output_formats: List[str] = field(default_factory=lambda: ["universal"])
    csv_delimiter: str = "|"
    clip_prefix: Optional[str] = None  # defaults to speaker_id when None
    keep_source_audio: bool = False
    make_references: bool = True       # auto-pick clean reference clips
    reference_count: int = 6
    reference_min_sec: float = 8.0
    reference_max_sec: float = 15.0

    # Quick test: only process the first N seconds of each source
    limit_seconds: Optional[float] = None

    # Misc
    seed: int = 1234

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.clip_prefix is None:
            self.clip_prefix = self.speaker_id
        if self.min_clip_sec <= 0:
            raise ValueError("min_clip_sec must be > 0")
        if self.max_clip_sec < self.min_clip_sec:
            raise ValueError("max_clip_sec must be >= min_clip_sec")
        if not (0.0 <= self.val_ratio < 1.0):
            raise ValueError("val_ratio must be in [0, 1)")
        if self.sample_width_bits not in (16, 24, 32):
            raise ValueError("sample_width_bits must be 16, 24, or 32")
        # Clamp cleaning knobs to sane ranges so a stray "-7" or "-99" in the
        # form can't trash a build.
        from .audio import LUFS_MIN, LUFS_MAX, SILENCE_DB_MIN, SILENCE_DB_MAX
        self.loudnorm_lufs = float(min(max(self.loudnorm_lufs, LUFS_MIN), LUFS_MAX))
        self.silence_threshold_db = float(
            min(max(self.silence_threshold_db, SILENCE_DB_MIN), SILENCE_DB_MAX)
        )
        if self.highpass_hz and not (20 <= self.highpass_hz <= 300):
            self.highpass_hz = 80
        if self.demucs_model not in ("htdemucs", "htdemucs_ft"):
            self.demucs_model = "htdemucs"
        normalized = []
        for fmt in self.output_formats:
            fmt = fmt.strip().lower()
            if fmt and fmt not in OUTPUT_FORMATS:
                raise ValueError(
                    f"Unknown output format '{fmt}'. Choose from {sorted(OUTPUT_FORMATS)}"
                )
            if fmt:
                normalized.append(fmt)
        self.output_formats = normalized or ["universal"]

    def resolved_formats(self) -> set:
        """Expand 'universal' into the concrete writers it implies."""
        out = set()
        for fmt in self.output_formats:
            if fmt == "universal":
                out.update({"jsonl", "csv", "fish", "gpt-sovits"})
            elif fmt == "ljspeech":
                out.add("csv")
            else:
                out.add(fmt)
        out.add("jsonl")  # always keep the canonical jsonl
        return out

    @property
    def audios_dir(self) -> Path:
        return self.output_dir / "audios"

    @property
    def references_dir(self) -> Path:
        return self.output_dir / "references"

    @property
    def train_jsonl(self) -> Path:
        return self.output_dir / "metadata_train.jsonl"

    @property
    def val_jsonl(self) -> Path:
        return self.output_dir / "metadata_val.jsonl"

    @property
    def metadata_csv(self) -> Path:
        return self.output_dir / "metadata.csv"

    @property
    def sovits_list(self) -> Path:
        return self.output_dir / "metadata.list"

    @property
    def config_json(self) -> Path:
        return self.output_dir / "config.json"

    @property
    def resume_state_json(self) -> Path:
        return self.output_dir / ".resume_state.json"

    def resume_fingerprint(self) -> str:
        """Stable hash of the inputs+core settings that define a build.

        Resume only triggers when this matches the saved state, so any
        change to sources or core slicing/transcription settings is
        treated as a fresh build.
        """
        payload = {
            "urls": list(self.urls),
            "local_sources": list(self.local_sources),
            "speaker_id": self.speaker_id,
            "language": self.language,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bits": self.sample_width_bits,
            "min_clip_sec": self.min_clip_sec,
            "max_clip_sec": self.max_clip_sec,
            "merge_gap_sec": self.merge_gap_sec,
            "whisper_model": self.whisper_model,
            "whisper_backend": self.whisper_backend,
            "clip_prefix": self.clip_prefix,
            "limit_seconds": self.limit_seconds,
            "prefer_subtitles": self.prefer_subtitles,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
