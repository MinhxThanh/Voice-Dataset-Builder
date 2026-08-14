"""Command-line interface for the voice dataset builder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import BuildConfig
from .pipeline import build_dataset


def _read_lines(path: Path) -> List[str]:
    out: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice-dataset-builder",
        description=(
            "Turn YouTube URLs or local files into a TTS-ready voice dataset "
            "(cleaned mono WAV clips + JSONL/CSV/Fish/GPT-SoVITS transcripts)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("urls", nargs="*", help="YouTube (or yt-dlp supported) URLs.")
    p.add_argument("--urls-file", type=Path, help="Text file, one URL per line.")
    p.add_argument(
        "--local", action="append", default=[],
        help="Local audio/video file (repeatable).",
    )
    p.add_argument("--local-file", type=Path, help="Text file, one local path per line.")
    p.add_argument("-o", "--output-dir", type=Path, default=Path("my_voice_dataset"))
    p.add_argument("--speaker-id", default="speaker_01")
    p.add_argument("--language", default=None, help="Force language (vi, en). Default: auto.")

    # audio spec
    p.add_argument("--sample-rate", type=int, default=24000)
    p.add_argument("--channels", type=int, default=1)
    p.add_argument("--bits", type=int, default=16, choices=[16, 24, 32])

    # slicing
    p.add_argument("--min-clip", type=float, default=3.0)
    p.add_argument("--max-clip", type=float, default=12.0)
    p.add_argument("--merge-gap", type=float, default=0.4)
    p.add_argument("--limit-seconds", type=float, default=None,
                   help="Only process the first N seconds of each source (quick test).")

    # cleaning
    p.add_argument("--no-loudnorm", action="store_true", help="Disable loudness normalization.")
    p.add_argument("--loudnorm-lufs", type=float, default=-23.0)
    p.add_argument("--no-remove-silence", action="store_true",
                   help="Keep leading/trailing silence.")
    p.add_argument("--denoise", action="store_true", help="Demucs vocal isolation (optional dep).")

    # transcription
    p.add_argument("--whisper-model", default="base")
    p.add_argument("--whisper-backend", default="auto",
                   choices=["auto", "faster-whisper", "openai-whisper"])
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--compute-type", default="auto")
    p.add_argument("--initial-prompt", default=None,
                   help="Bias decoding (great for vi diacritics).")
    p.add_argument("--min-confidence", type=float, default=None,
                   help="Drop segments below this avg_logprob.")
    p.add_argument("--prefer-subtitles", action="store_true",
                   help="Use YouTube CC/subs when available.")

    # output
    p.add_argument("--val-ratio", type=float, default=0.1)
    p.add_argument("--format", dest="output_formats", action="append", default=[],
                   help="Output format (repeatable): jsonl, csv, ljspeech, fish, "
                        "gpt-sovits, universal. Default: universal.")
    p.add_argument("--csv-delimiter", default="|")
    p.add_argument("--clip-prefix", default=None)
    p.add_argument("--no-references", action="store_true", help="Skip references/ folder.")
    p.add_argument("--keep-source-audio", action="store_true")
    p.add_argument("--seed", type=int, default=1234)

    # web UI
    ui = p.add_argument_group("web UI")
    ui.add_argument("--ui", action="store_true", help="Launch the local web UI.")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8000)
    ui.add_argument("--no-browser", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.ui:
        from .webui import serve

        serve(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0

    urls: List[str] = list(args.urls)
    if args.urls_file:
        urls.extend(_read_lines(args.urls_file))
    local: List[str] = list(args.local)
    if args.local_file:
        local.extend(_read_lines(args.local_file))
    if not urls and not local:
        print("error: provide URLs, --local files, --urls-file, or --ui", file=sys.stderr)
        return 2

    config = BuildConfig(
        urls=urls,
        local_sources=local,
        output_dir=args.output_dir,
        speaker_id=args.speaker_id,
        language=args.language,
        sample_rate=args.sample_rate,
        channels=args.channels,
        sample_width_bits=args.bits,
        min_clip_sec=args.min_clip,
        max_clip_sec=args.max_clip,
        merge_gap_sec=args.merge_gap,
        limit_seconds=args.limit_seconds,
        loudnorm=not args.no_loudnorm,
        loudnorm_lufs=args.loudnorm_lufs,
        remove_silence=not args.no_remove_silence,
        denoise=args.denoise,
        whisper_model=args.whisper_model,
        whisper_backend=args.whisper_backend,
        device=args.device,
        compute_type=args.compute_type,
        initial_prompt=args.initial_prompt,
        min_confidence=args.min_confidence,
        prefer_subtitles=args.prefer_subtitles,
        val_ratio=args.val_ratio,
        output_formats=args.output_formats or ["universal"],
        csv_delimiter=args.csv_delimiter,
        clip_prefix=args.clip_prefix,
        make_references=not args.no_references,
        keep_source_audio=args.keep_source_audio,
        seed=args.seed,
    )

    try:
        build_dataset(config)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
