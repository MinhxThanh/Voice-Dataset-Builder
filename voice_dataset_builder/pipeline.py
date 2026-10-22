"""End-to-end pipeline: sources -> audio -> transcript -> clean clips -> dataset."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, List, Optional

from . import audio as audio_utils
from .config import BuildConfig
from .downloader import AudioSource, collect_sources
from .metadata import (
    Record,
    ensure_ljspeech_wavs_link,
    split_records,
    write_fish_labs,
    write_gpt_sovits,
    write_jsonl,
    write_ljspeech_csv,
)
from .transcribe import (
    Transcript,
    parse_subtitles,
    shape_segments,
    transcribe,
)

LogFn = Callable[[str], None]
# progress(phase_name, fraction_0_to_1)
ProgressFn = Callable[[str, float], None]
PreviewFn = Callable[[dict], None]
# should_cancel() -> True means the caller asked to stop.
CancelFn = Callable[[], bool]


class BuildCancelled(Exception):
    """Raised internally when a build is cancelled by the caller."""

PHASES = ["download", "transcribe", "segment", "clean", "save"]


def _default_log(msg: str) -> None:
    print(f"[voice-dataset] {msg}")


def _load_resume_state(config: BuildConfig, log: LogFn) -> Optional[dict]:
    """Return saved resume state when it matches this build, else None."""
    path = config.resume_state_json
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log(f"resume state unreadable ({exc}) - starting fresh")
        return None
    saved_fingerprint = state.get("fingerprint")
    if saved_fingerprint not in {
        config.resume_fingerprint(), config.resume_fingerprint(legacy=True)
    }:
        log("resume state stale - starting fresh")
        return None
    if saved_fingerprint == config.resume_fingerprint(legacy=True):
        log("legacy resume state accepted; it will be upgraded on the next save")
    log(
        f"resume state found: source_idx={state.get('source_idx', 0)} "
        f"chunk_idx={state.get('chunk_idx', 0)} "
        f"clip_index={state.get('clip_index', 0)}"
    )
    return state


def _save_resume_state(
    config: BuildConfig,
    source_idx: int,
    chunk_idx: int,
    clip_index: int,
    records: List[Record],
    log: LogFn,
) -> None:
    """Persist progress so a matching rebuild can fast-forward."""
    path = config.resume_state_json
    payload = {
        "fingerprint": config.resume_fingerprint(),
        "source_idx": source_idx,
        "chunk_idx": chunk_idx,
        "clip_index": clip_index,
        "records": [
            {
                "audio_path": r.audio_path,
                "text": r.text,
                "speaker_id": r.speaker_id,
                "language": r.language,
                "duration": r.duration,
            }
            for r in records
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)
        log(f"resume state saved ({len(records)} records)")
    except Exception as exc:  # noqa: BLE001
        log(f"could not save resume state: {exc}")


def _clear_resume_state(config: BuildConfig) -> None:
    """Remove resume state after a successful completion."""
    try:
        config.resume_state_json.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _flush_metadata(
    config: BuildConfig,
    records: List[Record],
    formats,
    log: LogFn,
    partial: bool = False,
) -> dict:
    """Write metadata files + references for the records gathered so far.

    Used both on clean completion and when a build is stopped early, so a
    partial dataset is immediately usable. Returns a summary dict.
    """
    # Reconcile generated files with this record set so rebuilding an existing
    # project cannot leave stale clips or formats from an older build.
    keep_audio = {config.output_dir / r.audio_path for r in records}
    for wav in config.audios_dir.glob("*.wav"):
        if wav not in keep_audio:
            wav.unlink()

    def _remove(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)

    train, val = split_records(records, config.val_ratio, config.seed)
    write_jsonl(train, config.train_jsonl)
    if val:
        write_jsonl(val, config.val_jsonl)
    else:
        config.val_jsonl.unlink(missing_ok=True)

    wavs_dir = config.output_dir / "wavs"
    if "csv" in formats:
        _remove(wavs_dir)
        write_ljspeech_csv(records, config.metadata_csv, config.csv_delimiter)
        # Materialize ``wavs/`` so XTTS-v2's official LJSpeech formatter finds
        # clips at ``wavs/<id>.wav`` without the user editing paths.
        link = ensure_ljspeech_wavs_link(config.output_dir, "audios")
        log(f"  LJSpeech wavs at: {link.name}/ (-> audios/)")
    else:
        config.metadata_csv.unlink(missing_ok=True)
        _remove(wavs_dir)

    if "gpt-sovits" in formats:
        write_gpt_sovits(records, config.sovits_list)
    else:
        config.sovits_list.unlink(missing_ok=True)

    fish_dir = config.output_dir / "fish"
    _remove(fish_dir)
    if "fish" in formats:
        n_lab = write_fish_labs(records, config.output_dir)
        log(f"  wrote {n_lab} Fish Speech .lab files at fish/{config.speaker_id}/")
    log(f"  formats: {', '.join(sorted(formats))}")

    _remove(config.references_dir)
    ref_count = 0
    if config.make_references and records:
        ref_count = _make_references(records, config, log)

    total_dur = sum(r.duration for r in records)
    summary = {
        "output_dir": str(config.output_dir),
        "clips": len(records),
        "train_clips": len(train),
        "val_clips": len(val),
        "references": ref_count,
        "total_audio_sec": round(total_dur, 1),
        "total_audio_min": round(total_dur / 60.0, 2),
        "speaker_id": config.speaker_id,
        "sample_rate": config.sample_rate,
        "formats": sorted(formats),
        "partial": partial,
        "preview": [
            {"audio_path": r.audio_path, "text": r.text,
             "duration": round(r.duration, 2)}
            for r in records
        ],
    }
    _write_config_json(config, summary)
    return summary


def build_dataset(
    config: BuildConfig,
    log: Optional[LogFn] = None,
    progress: Optional[ProgressFn] = None,
    preview: Optional[PreviewFn] = None,
    should_cancel: Optional[CancelFn] = None,
) -> dict:
    """Run the full pipeline and return a summary dict.

    ``log`` receives human-readable lines. ``progress`` receives (phase, frac)
    so a UI can render a progress bar.
    """

    _log = log or _default_log

    def _progress(phase: str, frac: float) -> None:
        if progress:
            progress(phase, max(0.0, min(1.0, frac)))

    def _preview(item: dict) -> None:
        if preview:
            preview(item)

    def _save_state(source_idx: int, chunk_idx: int, clip_idx: int) -> None:
        _save_resume_state(
            config, source_idx, chunk_idx, clip_idx, records, _log
        )

    def _check_cancel() -> None:
        if should_cancel and should_cancel():
            raise BuildCancelled()

    if not config.urls and not config.local_sources:
        raise ValueError("No URLs or local sources provided.")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.audios_dir.mkdir(parents=True, exist_ok=True)

    records: List[Record] = []
    clip_index = 0
    resume_state = _load_resume_state(config, _log)
    resume_source_idx = 0
    resume_chunk_idx = 0
    if resume_state:
        resume_source_idx = int(resume_state.get("source_idx", 0))
        resume_chunk_idx = int(resume_state.get("chunk_idx", 0))
        clip_index = int(resume_state.get("clip_index", 0))
        for rec in resume_state.get("records", []):
            records.append(
                Record(
                    audio_path=rec["audio_path"],
                    text=rec["text"],
                    speaker_id=rec["speaker_id"],
                    language=rec["language"],
                    duration=rec["duration"],
                )
            )

    # Keep downloads only while a build is resumable. yt-dlp reuses files in
    # this directory, so stopping mid-source does not fetch the media again.
    work_dir = config.output_dir / ".resume_cache"
    if not resume_state:
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    source_dir = config.output_dir / "source_audio"
    formats = config.resolved_formats()
    completed = False

    try:
        # ---------- 1. acquire sources ----------
        _progress("download", 0.0)
        n_inputs = len(config.urls) + len(config.local_sources)
        if not 0 <= resume_source_idx <= n_inputs:
            raise RuntimeError("Resume source position is invalid for these inputs.")
        if resume_source_idx < len(config.urls):
            pending_urls = config.urls[resume_source_idx:]
            pending_local = config.local_sources
        else:
            pending_urls = []
            pending_local = config.local_sources[resume_source_idx - len(config.urls):]
        pending_count = len(pending_urls) + len(pending_local)
        if resume_state:
            _log(
                f"Resume: keeping {len(records)} clip(s); acquiring only "
                f"{pending_count} unfinished source(s)."
            )
        else:
            _log(f"Acquiring {pending_count} source(s) (yt-dlp + local)...")
        sub_langs = [config.language] if config.language else ["vi", "en"]
        sources = collect_sources(
            urls=pending_urls,
            local_sources=pending_local,
            work_dir=work_dir,
            sample_rate=config.sample_rate,
            audio_format="mp3",
            want_subtitles=config.prefer_subtitles,
            languages=sub_langs,
            input_start=resume_source_idx,
            log=_log,
        )
        if not sources and pending_count:
            raise RuntimeError("No audio sources were acquired successfully.")
        _check_cancel()
        _progress("download", 1.0)
        _log(f"Acquired {len(sources)} unfinished source(s).")
        total = n_inputs

        # ---------- resume: restore saved preview ----------
        if resume_state:
            for rec in records:
                _preview(
                    {
                        "clip_id": rec.audio_path.split("/")[-1].rsplit(".", 1)[0],
                        "audio_path": rec.audio_path,
                        "text": rec.text,
                        "duration": round(rec.duration, 2),
                        "status": "done",
                    }
                )
            _log(
                f"resumed with {len(records)} existing clip(s); continuing "
                f"from source {min(resume_source_idx + 1, total)}/{total}"
            )

        for src in sources:
            idx = src.input_index
            _check_cancel()
            base = idx / total

            # ---------- optional denoise ----------
            audio_path = src.audio_path
            if config.denoise:
                _log(f"Denoising: {src.title}")
                audio_path = audio_utils.denoise_demucs(
                    audio_path, work_dir, log=_log,
                    model=config.demucs_model, device=config.device,
                )

            # ---------- 2. transcript (subs or whisper) ----------
            _progress("transcribe", base)
            if _should_chunk_before_ai(config):
                clip_index = _transcribe_chunked_ai(
                    src=src,
                    audio_path=audio_path,
                    config=config,
                    work_dir=work_dir,
                    records=records,
                    clip_index=clip_index,
                    source_idx=idx,
                    resume_chunk_idx=resume_chunk_idx if idx == resume_source_idx else 0,
                    source_base=base,
                    source_total=total,
                    log=_log,
                    progress=_progress,
                    preview=_preview,
                    save_state=_save_state,
                    should_cancel=should_cancel,
                )
                if config.keep_source_audio:
                    _keep_source_audio(src, source_dir, _log)
                # Source finished: advance resume pointer to the next source.
                _save_state(idx + 1, 0, clip_index)
                continue
            transcript = _get_transcript(src, audio_path, config, _log)
            lang = config.language or transcript.language
            _log(f"  language={lang}, raw_segments={len(transcript.segments)}")

            # ---------- 3. segment shaping ----------
            _progress("segment", base)
            segs = _maybe_limit(transcript.segments, config.limit_seconds)
            if _is_full_audio_single_segment(segs, audio_path, config.max_clip_sec):
                shaped = segs
                _log(
                    "  model returned one full-audio transcript; keeping one full-length "
                    "clip to avoid text/audio mismatch."
                )
            else:
                shaped = shape_segments(
                    segs,
                    min_sec=config.min_clip_sec,
                    max_sec=config.max_clip_sec,
                    merge_gap_sec=config.merge_gap_sec,
                    min_confidence=config.min_confidence,
                )
            _log(f"  shaped_segments={len(shaped)}")

            # ---------- 4. clean + cut clips ----------
            source_resume_chunk = resume_chunk_idx if idx == resume_source_idx else 0
            for i, seg in enumerate(shaped, start=1):
                _check_cancel()
                if i <= source_resume_chunk:
                    continue
                clip_index += 1
                clip_name = f"{config.clip_prefix}_{clip_index:04d}.wav"
                clip_path = config.audios_dir / clip_name
                audio_utils.extract_clip(
                    src=audio_path,
                    dst=clip_path,
                    start=seg.start,
                    end=seg.end,
                    sample_rate=config.sample_rate,
                    channels=config.channels,
                    sample_width_bits=config.sample_width_bits,
                    loudnorm=config.loudnorm,
                    loudnorm_lufs=config.loudnorm_lufs,
                    remove_silence=config.remove_silence,
                    silence_threshold_db=config.silence_threshold_db,
                    highpass_hz=config.highpass_hz or None,
                    loudnorm_two_pass=config.loudnorm_two_pass,
                )
                actual_dur = audio_utils.probe_duration(clip_path)
                records.append(
                    Record(
                        audio_path=f"audios/{clip_name}",
                        text=seg.text,
                        speaker_id=config.speaker_id,
                        language=lang,
                        duration=actual_dur,
                    )
                )
                _preview(
                    {
                        "clip_id": clip_name.rsplit(".", 1)[0],
                        "audio_path": f"audios/{clip_name}",
                        "text": seg.text,
                        "duration": round(actual_dur, 2),
                        "status": "done",
                    }
                )
                if shaped:
                    _progress("clean", base + (i / len(shaped)) / total)
                if i % 10 == 0 or i == len(shaped):
                    _log(f"  clips written: {i}/{len(shaped)}")
                _save_state(idx, i, clip_index)

            if config.keep_source_audio:
                _keep_source_audio(src, source_dir, _log)

            # Source finished: advance the resume pointer past it.
            _save_state(idx + 1, 0, clip_index)

        if not records:
            raise RuntimeError(
                "Pipeline produced 0 clips. Try a lower min_clip_sec, a different "
                "Whisper model, or disable the confidence filter."
            )

        # ---------- 5. write metadata + references ----------
        _progress("save", 0.2)
        summary = _flush_metadata(config, records, formats, _log, partial=False)
        summary["sources"] = n_inputs
        _progress("save", 1.0)

        # Build completed cleanly: drop resume state so the next run starts fresh.
        _clear_resume_state(config)
        completed = True

        _log("Done.")
        _log(json.dumps({k: v for k, v in summary.items() if k != "preview"},
                        ensure_ascii=False, indent=2))
        return summary
    except BuildCancelled:
        # Stopped early: flush whatever we have so the partial dataset is usable,
        # and keep the resume state so it can be continued later.
        if records:
            _log(f"Stopped: saving {len(records)} clip(s) gathered so far...")
            try:
                _flush_metadata(config, records, formats, _log, partial=True)
            except Exception as exc:  # noqa: BLE001
                _log(f"  [warn] could not flush partial metadata: {exc}")
        else:
            _log("Stopped before any clips were produced.")
        raise
    finally:
        if completed:
            shutil.rmtree(work_dir, ignore_errors=True)


def _get_transcript(
    src: AudioSource, audio_path: Path, config: BuildConfig, log: LogFn
) -> Transcript:
    if config.prefer_subtitles and src.subtitle_path and src.subtitle_path.exists():
        log(f"Using subtitles: {src.subtitle_path.name}")
        try:
            t = parse_subtitles(src.subtitle_path, config.language or "unknown")
            if t.segments:
                return t
            log("  subtitles empty; falling back to Whisper.")
        except Exception as exc:  # noqa: BLE001
            log(f"  subtitle parse failed ({exc}); falling back to Whisper.")

    log(f"Transcribing: {src.title} ({src.source_id})")
    return transcribe(
        audio_path,
        model=config.whisper_model,
        backend=config.whisper_backend,
        language=config.language,
        device=config.device,
        compute_type=config.compute_type,
        initial_prompt=config.initial_prompt,
    )


def _should_chunk_before_ai(config: BuildConfig) -> bool:
    if config.prefer_subtitles:
        return False
    model = config.whisper_model
    if model in ("Qwen/Qwen3-ASR-1.7B", "Qwen/Qwen3-ASR-0.6B"):
        return True
    if model == "CohereLabs/cohere-transcribe-03-2026":
        return True
    return False


def _chunk_ranges(duration: float, min_sec: float, max_sec: float) -> List[tuple[float, float]]:
    chunk_len = max(min(max_sec, 12.0), min_sec)
    ranges = []
    start = 0.0
    while start < duration:
        end = min(duration, start + chunk_len)
        if end - start < 1.0:
            break
        if ranges and end - start < min_sec:
            prev_start, _ = ranges[-1]
            if end - prev_start <= max_sec or end - min_sec - prev_start < min_sec:
                ranges[-1] = (prev_start, end)
            else:
                ranges[-1] = (prev_start, end - min_sec)
                ranges.append((end - min_sec, end))
        else:
            ranges.append((start, end))
        start = end
    return ranges


def _transcribe_chunked_ai(
    src: AudioSource,
    audio_path: Path,
    config: BuildConfig,
    work_dir: Path,
    records: List[Record],
    clip_index: int,
    source_idx: int,
    resume_chunk_idx: int,
    source_base: float,
    source_total: int,
    log: LogFn,
    progress: ProgressFn,
    preview: PreviewFn,
    save_state: Callable[[int, int, int], None],
    should_cancel: Optional[CancelFn] = None,
) -> int:
    duration = audio_utils.probe_duration(audio_path)
    if config.limit_seconds:
        duration = min(duration, config.limit_seconds)
    ranges = _chunk_ranges(duration, config.min_clip_sec, config.max_clip_sec)
    lang = config.language or "unknown"
    log(
        f"AI chunk transcription: {src.title} ({len(ranges)} chunks, "
        f"{duration:.1f}s total)"
    )
    chunks_dir = work_dir / "ai_chunks"
    for i, (start, end) in enumerate(ranges, start=1):
        if should_cancel and should_cancel():
            raise BuildCancelled()
        # Resume: skip chunks already completed in a prior run of this source.
        if i <= resume_chunk_idx:
            continue
        progress("transcribe", source_base + ((i - 1) / max(1, len(ranges))) / source_total)
        safe_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in src.source_id)
        chunk_path = chunks_dir / f"{safe_id or 'source'}_{i:04d}.wav"
        audio_utils.extract_clip(
            src=audio_path,
            dst=chunk_path,
            start=start,
            end=end,
            sample_rate=16000,
            channels=1,
            sample_width_bits=16,
            loudnorm=False,
            remove_silence=False,
        )
        # Cut the final clip up front so its audio is playable while text decodes.
        clip_index += 1
        clip_name = f"{config.clip_prefix}_{clip_index:04d}.wav"
        clip_id = clip_name.rsplit(".", 1)[0]
        clip_path = config.audios_dir / clip_name
        audio_utils.extract_clip(
            src=audio_path,
            dst=clip_path,
            start=start,
            end=end,
            sample_rate=config.sample_rate,
            channels=config.channels,
            sample_width_bits=config.sample_width_bits,
            loudnorm=config.loudnorm,
            loudnorm_lufs=config.loudnorm_lufs,
            remove_silence=config.remove_silence,
            silence_threshold_db=config.silence_threshold_db,
            highpass_hz=config.highpass_hz or None,
            loudnorm_two_pass=config.loudnorm_two_pass,
        )
        try:
            actual_dur = audio_utils.probe_duration(clip_path)
        except RuntimeError:
            if i != len(ranges):
                raise
            log(f"  chunk {i}/{len(ranges)} has no playable audio; skipped")
            clip_path.unlink(missing_ok=True)
            clip_index -= 1
            save_state(source_idx, i, clip_index)
            continue
        rel_path = f"audios/{clip_name}"
        # Streaming row 1: audio is ready, text is still decoding.
        preview(
            {
                "clip_id": clip_id,
                "audio_path": rel_path,
                "text": "",
                "duration": round(actual_dur, 2),
                "status": "transcribing",
            }
        )

        # Streaming text: push partial transcript as each segment decodes.
        partial: List[str] = []

        def _on_segment(seg, _clip_id=clip_id, _rel=rel_path,
                        _dur=actual_dur, _acc=partial) -> None:
            piece = (seg.text or "").strip()
            if not piece:
                return
            _acc.append(piece)
            preview(
                {
                    "clip_id": _clip_id,
                    "audio_path": _rel,
                    "text": " ".join(_acc),
                    "duration": round(_dur, 2),
                    "status": "transcribing",
                }
            )

        try:
            transcript = transcribe(
                chunk_path,
                model=config.whisper_model,
                backend=config.whisper_backend,
                language=config.language,
                device=config.device,
                compute_type=config.compute_type,
                initial_prompt=config.initial_prompt,
                on_segment=_on_segment,
            )
        except Exception:
            clip_path.unlink(missing_ok=True)
            preview(
                {
                    "clip_id": clip_id,
                    "audio_path": rel_path,
                    "text": "",
                    "duration": round(actual_dur, 2),
                    "status": "removed",
                }
            )
            raise
        text = " ".join(seg.text for seg in transcript.segments if seg.text).strip()
        if not text:
            # Empty chunk: drop the row and the orphan clip, reuse the index.
            log(f"  chunk {i}/{len(ranges)} empty; skipped")
            try:
                clip_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
            preview(
                {
                    "clip_id": clip_id,
                    "audio_path": rel_path,
                    "text": "",
                    "duration": round(actual_dur, 2),
                    "status": "removed",
                }
            )
            clip_index -= 1
            save_state(source_idx, i, clip_index)
            continue
        lang = config.language or transcript.language or lang
        records.append(
            Record(
                audio_path=rel_path,
                text=text,
                speaker_id=config.speaker_id,
                language=lang,
                duration=actual_dur,
            )
        )
        # Streaming row 2: final text in place.
        preview(
            {
                "clip_id": clip_id,
                "audio_path": rel_path,
                "text": text,
                "duration": round(actual_dur, 2),
                "status": "done",
            }
        )
        log(f"  chunk {i}/{len(ranges)} -> {clip_name}: {text}")
        progress("clean", source_base + (i / max(1, len(ranges))) / source_total)
        # Persist progress after each completed chunk so resume is chunk-accurate.
        save_state(source_idx, i, clip_index)
    return clip_index


def _keep_source_audio(src: AudioSource, source_dir: Path, log: LogFn) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src.audio_path, source_dir / src.audio_path.name)
    except Exception as exc:  # noqa: BLE001
        log(f"  [warn] could not keep source audio: {exc}")


def _is_full_audio_single_segment(
    segments: List,
    audio_path: Path,
    max_clip_sec: float,
) -> bool:
    if len(segments) != 1:
        return False
    seg = segments[0]
    if seg.duration <= max_clip_sec:
        return False
    try:
        audio_dur = audio_utils.probe_duration(audio_path)
    except Exception:
        audio_dur = seg.duration
    return seg.start <= 0.5 and abs(seg.end - audio_dur) <= max(1.0, audio_dur * 0.05)


def _maybe_limit(segments, limit_seconds: Optional[float]):
    if not limit_seconds:
        return segments
    return [s for s in segments if s.end <= limit_seconds]


def _make_references(records: List[Record], config: BuildConfig, log: LogFn) -> int:
    """Copy the best long-ish clips into references/ for voice cloning prompts."""
    candidates = [
        r for r in records
        if config.reference_min_sec <= r.duration <= config.reference_max_sec
    ]
    # Prefer clips with more text (more content) as cleaner references.
    candidates.sort(key=lambda r: len(r.text), reverse=True)
    if not candidates:
        # Fall back to longest available clips.
        candidates = sorted(records, key=lambda r: r.duration, reverse=True)
    config.references_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in candidates[: config.reference_count]:
        src = config.output_dir / r.audio_path
        dst = config.references_dir / f"ref_{n + 1:02d}.wav"
        try:
            shutil.copy2(src, dst)
            n += 1
        except Exception as exc:  # noqa: BLE001
            log(f"  [warn] reference copy failed: {exc}")
    log(f"  references: {n} clip(s) -> references/")
    return n


def _write_config_json(config: BuildConfig, summary: dict) -> None:
    payload = {
        "speaker_id": config.speaker_id,
        "language": config.language,
        "sample_rate": config.sample_rate,
        "channels": config.channels,
        "sample_width_bits": config.sample_width_bits,
        "min_clip_sec": config.min_clip_sec,
        "max_clip_sec": config.max_clip_sec,
        "whisper_model": config.whisper_model,
        "loudnorm_lufs": config.loudnorm_lufs,
        "loudnorm_two_pass": config.loudnorm_two_pass,
        "remove_silence": config.remove_silence,
        "silence_threshold_db": config.silence_threshold_db,
        "highpass_hz": config.highpass_hz,
        "denoise": config.denoise,
        "demucs_model": config.demucs_model,
        "output_formats": sorted(config.resolved_formats()),
        "summary": {k: v for k, v in summary.items() if k != "preview"},
    }
    config.config_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
