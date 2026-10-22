"""Unit tests for pure logic (no network or ML deps required)."""

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_dataset_builder.transcribe import (
    Segment, shape_segments, parse_subtitles,
)
from voice_dataset_builder.metadata import (
    Record, split_records, write_gpt_sovits, write_fish_labs, write_ljspeech_csv,
    ensure_ljspeech_wavs_link, update_clip_text,
)
from voice_dataset_builder.config import BuildConfig
from voice_dataset_builder import asr_models
from voice_dataset_builder import downloader
from voice_dataset_builder import pipeline
from voice_dataset_builder.downloader import _find_media, _find_subtitle
from voice_dataset_builder.pipeline import _chunk_ranges
from voice_dataset_builder import projects
from voice_dataset_builder.webui import Job, _persist_text_overrides
from upload_to_hf import _metadata_files


def test_merge_short_segments():
    segs = [Segment(0.0, 1.0, "a"), Segment(1.1, 2.0, "b"), Segment(2.1, 4.0, "c")]
    out = shape_segments(segs, 3.0, 12.0, 0.4)
    assert len(out) == 1 and out[0].text == "a b c" and out[0].duration >= 3.0


def test_keep_long_segment_aligned():
    out = shape_segments([Segment(0.0, 30.0, "long")], 3.0, 12.0, 0.4)
    assert len(out) == 1 and out[0].duration == 30.0 and out[0].text == "long"


def test_detect_full_audio_single_segment():
    old_probe = pipeline.audio_utils.probe_duration
    pipeline.audio_utils.probe_duration = lambda path: 98.0
    try:
        assert pipeline._is_full_audio_single_segment(
            [Segment(0.0, 98.0, "whole video text")], Path("x.mp3"), 12.0
        )
        assert not pipeline._is_full_audio_single_segment(
            [Segment(0.0, 10.0, "short")], Path("x.mp3"), 12.0
        )
    finally:
        pipeline.audio_utils.probe_duration = old_probe


def test_respects_max_clip():
    segs = [Segment(0,5,"a"), Segment(5.05,10,"b"), Segment(10.05,16,"c")]
    for s in shape_segments(segs, 3.0, 12.0, 0.4):
        assert s.duration <= 12.0 + 1e-6


def test_drop_subsecond_clip():
    out = shape_segments([Segment(0,0.5,"hi"), Segment(5,9,"longer clip")], 3.0, 12.0, 0.4)
    assert all(s.duration >= 1.0 for s in out)


def test_confidence_filter():
    segs = [Segment(0,5,"good",confidence=-0.2), Segment(6,11,"bad",confidence=-1.5)]
    out = shape_segments(segs, 3.0, 12.0, 0.4, min_confidence=-1.0)
    joined = " ".join(s.text for s in out)
    assert "good" in joined and "bad" not in joined


def test_parse_vtt():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000
Xin chào các bạn

00:00:04.000 --> 00:00:07.500
<c>hôm nay</c> trời đẹp
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.vtt"; p.write_text(vtt, encoding="utf-8")
        t = parse_subtitles(p, "vi")
    assert t.language == "vi" and len(t.segments) == 2
    assert t.segments[0].text == "Xin chào các bạn"
    assert t.segments[1].text == "hôm nay trời đẹp"


def test_parse_youtube_vtt_inline_timestamps():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000 align:start position:0%
<00:00:01.200>Xin <00:00:01.800>chào <c>các bạn</c>
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.vi.vtt"; p.write_text(vtt, encoding="utf-8")
        t = parse_subtitles(p, "vi")
    assert len(t.segments) == 1
    assert t.segments[0].text == "Xin chào các bạn"


def test_find_subtitle_prefers_requested_language():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "abc.en.vtt").write_text("WEBVTT", encoding="utf-8")
        vi = root / "abc.vi.vtt"
        vi.write_text("WEBVTT", encoding="utf-8")
        assert _find_subtitle(root, "abc", ["vi"]) == vi


def test_find_media_accepts_downloaded_mp3_but_not_converted_output():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        source = root / "abc.mp3"
        source.write_bytes(b"source")
        (root / "abc.audio.mp3").write_bytes(b"converted")
        assert _find_media(root, "abc") == source


def test_source_indices_survive_failed_inputs():
    old_download = downloader.download_audio

    def fake_download(url, work_dir, *args):
        if url == "bad":
            raise RuntimeError("failed")
        return downloader.AudioSource(url, url, url, Path(f"{url}.mp3"))

    downloader.download_audio = fake_download
    try:
        sources = downloader.collect_sources(
            ["bad", "good"], [], Path("work"), input_start=4, log=lambda _: None
        )
    finally:
        downloader.download_audio = old_download
    assert len(sources) == 1 and sources[0].input_index == 5


def test_chunk_ranges_cover_audio_without_tiny_tail():
    ranges = _chunk_ranges(98.0, 3.0, 12.0)
    assert ranges[0] == (0.0, 12.0)
    assert ranges[-1][1] == 98.0
    assert all(end > start for start, end in ranges)
    assert all((end - start) >= 3.0 for start, end in ranges)
    assert all((end - start) <= 12.0 for start, end in ranges)


def test_limit_drops_segment_crossing_boundary():
    segments = [Segment(170, 179, "inside"), Segment(179, 185, "crosses")]
    assert pipeline._maybe_limit(segments, 180) == segments[:1]


def test_split_records_keeps_train():
    recs = [Record(f"audios/x_{i:04d}.wav", "t", "spk", "en", 5.0) for i in range(10)]
    train, val = split_records(recs, 0.1, 1)
    assert len(val) == 1 and len(train) == 9


def test_format_expansion():
    cfg = BuildConfig(urls=["u"], output_formats=["universal"])
    f = cfg.resolved_formats()
    assert {"jsonl", "csv", "fish", "gpt-sovits"} <= f
    cfg2 = BuildConfig(urls=["u"], output_formats=["ljspeech"])
    assert cfg2.resolved_formats() == {"csv", "jsonl"}


def test_config_rejects_path_traversal_names():
    for kwargs in (
        {"speaker_id": "../../outside"},
        {"clip_prefix": "../outside"},
        {"speaker_id": '<img onerror="alert(1)">'},
        {"csv_delimiter": "\n"},
    ):
        try:
            BuildConfig(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected rejection: {kwargs}")


def test_resume_fingerprint_covers_processing_settings():
    first = BuildConfig(urls=["u"], initial_prompt="first", loudnorm_lufs=-23)
    second = BuildConfig(urls=["u"], initial_prompt="second", loudnorm_lufs=-14)
    assert first.resume_fingerprint() != second.resume_fingerprint()
    assert first.resume_fingerprint(legacy=True) == second.resume_fingerprint(legacy=True)


def test_flush_metadata_removes_stale_outputs():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "audios").mkdir()
        records = [
            Record("audios/x_0001.wav", "one", "spk", "en", 5.0),
            Record("audios/x_0002.wav", "two", "spk", "en", 5.0),
        ]
        for rec in records:
            (root / rec.audio_path).write_bytes(b"RIFF")

        first = BuildConfig(
            output_dir=root, val_ratio=0.5,
            output_formats=["universal"], make_references=False,
        )
        pipeline._flush_metadata(
            first, records, first.resolved_formats(), lambda _: None
        )

        second = BuildConfig(
            output_dir=root, val_ratio=0,
            output_formats=["jsonl"], make_references=False,
        )
        pipeline._flush_metadata(
            second, records[:1], second.resolved_formats(), lambda _: None
        )

        assert (root / "audios/x_0001.wav").exists()
        for stale in (
            "audios/x_0002.wav", "metadata_val.jsonl", "metadata.csv",
            "metadata.list", "wavs", "fish", "references",
        ):
            assert not (root / stale).exists(), stale


def test_asr_registry_reports_empty_model_dir_as_not_downloaded():
    with tempfile.TemporaryDirectory() as d:
        old_dir = asr_models.MODELS_DIR
        asr_models.MODELS_DIR = Path(d) / "models"
        try:
            model_id = "Qwen/Qwen3-ASR-0.6B"
            asr_models.model_local_path(model_id).mkdir(parents=True)
            listed = {m["id"]: m for m in asr_models.list_asr_models()}
            assert listed[model_id]["downloaded"] is False
            (asr_models.model_local_path(model_id) / "config.json").write_text("{}")
            listed = {m["id"]: m for m in asr_models.list_asr_models()}
            assert listed[model_id]["downloaded"] is True
            assert asr_models.resolve_model_path(model_id).endswith("Qwen3-ASR-0.6B")
        finally:
            asr_models.MODELS_DIR = old_dir


def test_asr_registry_includes_requested_models():
    ids = {m["id"] for m in asr_models.list_asr_models()}
    assert {
        "Qwen/Qwen3-ASR-1.7B",
        "CohereLabs/cohere-transcribe-03-2026",
        "Qwen/Qwen3-ASR-0.6B",
    } <= ids


def test_writers_roundtrip():
    # Two records: a supported language (en) and an unsupported one (vi),
    # so we can also assert GPT-SoVITS language coercion.
    recs = [
        Record("audios/a_0001.wav", "hello world", "spk", "en", 5.0),
        Record("audios/a_0002.wav", "xin chao", "spk", "vi", 4.2),
    ]
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "audios").mkdir()
        (root / "audios" / "a_0001.wav").write_bytes(b"RIFF")
        (root / "audios" / "a_0002.wav").write_bytes(b"RIFF")
        write_ljspeech_csv(recs, root / "metadata.csv")
        write_gpt_sovits(recs, root / "metadata.list")
        n = write_fish_labs(recs, root)

        # LJSpeech metadata.csv: ID|Transcription|NormalizedTranscription,
        # ID is the wav basename without extension (matches the Coqui
        # ``formatter="ljspeech"`` and XTTS-v2 recipe expectations).
        csv_lines = (root / "metadata.csv").read_text().splitlines()
        assert csv_lines[0] == "a_0001|hello world|hello world"
        assert csv_lines[1] == "a_0002|xin chao|xin chao"

        # GPT-SoVITS .list: absolute audio_path|speaker|language|text. Language must be
        # one of {zh, ja, en, ko, yue} so upstream training accepts the row;
        # 'vi' is coerced to 'en' instead of being silently dropped.
        sovits = (root / "metadata.list").read_text().splitlines()
        assert sovits[0] == f"{(root / 'audios/a_0001.wav').resolve()}|spk|en|hello world"
        assert sovits[1] == f"{(root / 'audios/a_0002.wav').resolve()}|spk|en|xin chao"

        # Fish Speech: one .lab sidecar per wav, content == transcription.
        assert n == 2
        # Fish layout: fish/<speaker>/<stem>.{lab,wav}
        assert (root / "fish" / "spk" / "a_0001.lab").read_text() == "hello world"
        assert (root / "fish" / "spk" / "a_0002.lab").read_text() == "xin chao"
        for stem in ("a_0001", "a_0002"):
            paired = root / "fish" / "spk" / f"{stem}.wav"
            assert paired.exists() or paired.is_symlink()

        # XTTS expects clips under wavs/<id>.wav; the link/copy must resolve.
        link = ensure_ljspeech_wavs_link(root, "audios")
        assert link == root / "wavs"
        assert (link / "a_0001.wav").exists()
        # Calling again is idempotent and doesn't blow up.
        ensure_ljspeech_wavs_link(root, "audios")
        assert (link / "a_0002.wav").exists()


def test_create_and_list_project():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        target = projects.create_project("My Voice!", base=base)
        assert target.exists() and target.parent.name == "projects"
        assert target.name == "My_Voice"
        names = [p.name for p in projects.list_projects(base=base)]
        assert "My_Voice" in names
        assert projects.resolve_project_dir("My Voice!", base=base) == target


def test_create_project_rejects_duplicate():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        projects.create_project("dup", base=base)
        try:
            projects.create_project("dup", base=base)
        except ValueError:
            return
        raise AssertionError("expected duplicate to raise")


def test_unrelated_root_directory_is_not_a_project():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "voice_dataset_builder").mkdir()
        assert projects.resolve_project_dir("voice_dataset_builder", base=base) is None


def test_build_inputs_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        target = projects.create_project("inp", base=Path(d))
        projects.save_build_inputs(target, {"speaker_id": "x", "output_dir": "drop", "project": "drop"})
        loaded = projects.load_build_inputs(target)
        assert loaded == {"speaker_id": "x"}
        # a folder with saved inputs is recognised as a project
        assert projects._looks_like_project(target)


def test_hf_upload_allows_missing_validation_split():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        train = root / "metadata_train.jsonl"
        train.write_text("{}\n", encoding="utf-8")
        assert _metadata_files(root) == {"train": str(train)}

        validation = root / "metadata_val.jsonl"
        validation.write_text("{}\n", encoding="utf-8")
        assert _metadata_files(root) == {
            "train": str(train), "validation": str(validation),
        }


def test_load_project_clips_prefers_metadata():
    with tempfile.TemporaryDirectory() as d:
        target = projects.create_project("clips", base=Path(d))
        (target / "audios").mkdir()
        (target / "audios" / "a_0001.wav").write_bytes(b"RIFF")
        (target / "audios" / "a_0002.wav").write_bytes(b"RIFF")
        (target / "metadata_train.jsonl").write_text(
            '{"audio_path": "audios/a_0001.wav", "text": "hello", "duration": 2.5}\n',
            encoding="utf-8",
        )
        rows = projects.load_project_clips(target)
        assert len(rows) == 2
        first = next(r for r in rows if r["audio_path"] == "audios/a_0001.wav")
        assert first["text"] == "hello" and first["clip_id"] == "a_0001"
        # the metadata-less wav still surfaces with empty text
        second = next(r for r in rows if r["audio_path"] == "audios/a_0002.wav")
        assert second["text"] == ""


def test_load_project_clips_accepts_file_name():
    with tempfile.TemporaryDirectory() as d:
        target = projects.create_project("legacy", base=Path(d))
        (target / "metadata_train.jsonl").write_text(
            '{"file_name": "audios/a_0001.wav", "text": "hello", "duration": 2.5}\n',
            encoding="utf-8",
        )
        rows = projects.load_project_clips(target)
        assert rows == [{
            "clip_id": "a_0001", "audio_path": "audios/a_0001.wav",
            "text": "hello", "duration": 2.5,
        }]
        assert update_clip_text(target, "audios/a_0001.wav", "edited")
        assert projects.load_project_clips(target)[0]["text"] == "edited"


def test_load_project_clips_from_resume_state():
    with tempfile.TemporaryDirectory() as d:
        target = projects.create_project("rsm", base=Path(d))
        (target / "audios").mkdir()
        (target / "audios" / "a_0001.wav").write_bytes(b"RIFF")
        (target / ".resume_state.json").write_text(
            '{"records": [{"audio_path": "audios/a_0001.wav", "text": "resumed", "duration": 4.0}]}',
            encoding="utf-8",
        )
        rows = projects.load_project_clips(target)
        assert len(rows) == 1 and rows[0]["text"] == "resumed"


def test_edit_ljspeech_csv_preserves_delimiters():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_ljspeech_csv(
            [Record("audios/a.wav", "hello|world", "spk", "en", 1.0)],
            root / "metadata.csv",
        )
        assert update_clip_text(root, "audios/a.wav", "edited|again")
        with (root / "metadata.csv").open(encoding="utf-8", newline="") as fh:
            assert list(csv.reader(fh, delimiter="|")) == [
                ["a", "edited|again", "edited|again"]
            ]


def test_gpt_sovits_removes_field_separators():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        record = Record("audios/a.wav", "hello|world", "spk|one", "en", 1.0)
        write_gpt_sovits([record], root / "metadata.list")
        assert (root / "metadata.list").read_text().count("|") == 3
        assert update_clip_text(root, "audios/a.wav", "edited|again")
        line = (root / "metadata.list").read_text().strip()
        assert line.count("|") == 3 and line.endswith("edited again")


def test_edit_rejects_paths_outside_audios():
    with tempfile.TemporaryDirectory() as d:
        try:
            update_clip_text(Path(d), "audios/../../outside.wav", "bad")
        except ValueError:
            return
        raise AssertionError("expected traversal path to be rejected")


def test_live_edit_is_persisted_after_job_finishes():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "metadata_train.jsonl").write_text(
            '{"audio_path":"audios/a.wav","text":"original"}\n',
            encoding="utf-8",
        )
        job = Job(id="1", output_dir=str(root))
        job.set_text("a", "edited")
        _persist_text_overrides(job)
        assert projects.load_project_clips(root)[0]["text"] == "edited"


def test_resume_acquires_only_unfinished_sources():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "audios").mkdir()
        (root / "audios" / "a.wav").write_bytes(b"RIFF")
        cfg = BuildConfig(
            urls=["done-1", "done-2", "pending"],
            output_dir=root,
            whisper_model="Qwen/Qwen3-ASR-0.6B",
            output_formats=["jsonl"],
            make_references=False,
        )
        rec = Record("audios/a.wav", "saved", "spk", "vi", 4.0)
        pipeline._save_resume_state(cfg, 2, 7, 1, [rec], lambda _: None)
        calls = {}
        old_collect = pipeline.collect_sources
        old_chunked = pipeline._transcribe_chunked_ai

        def fake_collect(**kwargs):
            calls["urls"] = kwargs["urls"]
            return [
                pipeline.AudioSource(
                    "pending", "pending", "p", Path("p.mp3"),
                    input_index=kwargs["input_start"],
                )
            ]

        def fake_chunked(**kwargs):
            calls["chunk"] = kwargs["resume_chunk_idx"]
            return kwargs["clip_index"]

        pipeline.collect_sources = fake_collect
        pipeline._transcribe_chunked_ai = fake_chunked
        try:
            summary = pipeline.build_dataset(cfg, log=lambda _: None)
        finally:
            pipeline.collect_sources = old_collect
            pipeline._transcribe_chunked_ai = old_chunked

        assert calls == {"urls": ["pending"], "chunk": 7}
        assert summary["sources"] == 3


def test_chunked_ai_skips_unplayable_final_tail():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = BuildConfig(output_dir=root)
        records = []
        saved = []
        old_probe = pipeline.audio_utils.probe_duration
        old_extract = pipeline.audio_utils.extract_clip

        def fake_probe(path):
            if Path(path).name == "source.wav":
                return 4.0
            raise RuntimeError("no duration")

        def fake_extract(**kwargs):
            kwargs["dst"].parent.mkdir(parents=True, exist_ok=True)
            kwargs["dst"].write_bytes(b"RIFF")

        pipeline.audio_utils.probe_duration = fake_probe
        pipeline.audio_utils.extract_clip = fake_extract
        try:
            clip_index = pipeline._transcribe_chunked_ai(
                src=pipeline.AudioSource("x", "x", "x", root / "source.wav"),
                audio_path=root / "source.wav",
                config=cfg,
                work_dir=root / "work",
                records=records,
                clip_index=0,
                source_idx=0,
                resume_chunk_idx=0,
                source_base=0,
                source_total=1,
                log=lambda _: None,
                progress=lambda *_: None,
                preview=lambda _: None,
                save_state=lambda *args: saved.append(args),
            )
        finally:
            pipeline.audio_utils.probe_duration = old_probe
            pipeline.audio_utils.extract_clip = old_extract

        assert clip_index == 0 and records == [] and saved == [(0, 1, 0)]


def test_chunked_ai_removes_clip_when_transcription_fails():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = BuildConfig(output_dir=root)
        events = []
        old_probe = pipeline.audio_utils.probe_duration
        old_extract = pipeline.audio_utils.extract_clip
        old_transcribe = pipeline.transcribe

        def fake_probe(path):
            return 4.0

        def fake_extract(**kwargs):
            kwargs["dst"].parent.mkdir(parents=True, exist_ok=True)
            kwargs["dst"].write_bytes(b"RIFF")

        def fake_transcribe(*args, **kwargs):
            raise RuntimeError("ASR failed")

        pipeline.audio_utils.probe_duration = fake_probe
        pipeline.audio_utils.extract_clip = fake_extract
        pipeline.transcribe = fake_transcribe
        try:
            try:
                pipeline._transcribe_chunked_ai(
                    src=pipeline.AudioSource("x", "x", "x", root / "source.wav"),
                    audio_path=root / "source.wav",
                    config=cfg,
                    work_dir=root / "work",
                    records=[],
                    clip_index=0,
                    source_idx=0,
                    resume_chunk_idx=0,
                    source_base=0,
                    source_total=1,
                    log=lambda _: None,
                    progress=lambda *_: None,
                    preview=events.append,
                    save_state=lambda *_: None,
                )
            except RuntimeError as exc:
                assert str(exc) == "ASR failed"
            else:
                raise AssertionError("expected transcription failure")
        finally:
            pipeline.audio_utils.probe_duration = old_probe
            pipeline.audio_utils.extract_clip = old_extract
            pipeline.transcribe = old_transcribe

        assert not (root / "audios" / "speaker_01_0001.wav").exists()
        assert events[-1]["status"] == "removed"


def test_non_ai_resume_skips_finished_clips():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "audios").mkdir()
        (root / "audios" / "speaker_01_0001.wav").write_bytes(b"RIFF")
        cfg = BuildConfig(
            urls=["source"], output_dir=root, output_formats=["jsonl"],
            make_references=False,
        )
        saved = Record("audios/speaker_01_0001.wav", "one", "speaker_01", "en", 4.0)
        pipeline._save_resume_state(cfg, 0, 1, 1, [saved], lambda _: None)
        starts = []
        old_collect = pipeline.collect_sources
        old_transcript = pipeline._get_transcript
        old_extract = pipeline.audio_utils.extract_clip
        old_probe = pipeline.audio_utils.probe_duration

        pipeline.collect_sources = lambda **kwargs: [
            pipeline.AudioSource("source", "source", "s", Path("source.mp3"), input_index=0)
        ]
        pipeline._get_transcript = lambda *args: pipeline.Transcript(
            "en", [Segment(0, 4, "one"), Segment(5, 9, "two")]
        )

        def fake_extract(**kwargs):
            starts.append(kwargs["start"])
            kwargs["dst"].parent.mkdir(parents=True, exist_ok=True)
            kwargs["dst"].write_bytes(b"RIFF")

        pipeline.audio_utils.extract_clip = fake_extract
        pipeline.audio_utils.probe_duration = lambda path: 4.0
        try:
            summary = pipeline.build_dataset(cfg, log=lambda _: None)
        finally:
            pipeline.collect_sources = old_collect
            pipeline._get_transcript = old_transcript
            pipeline.audio_utils.extract_clip = old_extract
            pipeline.audio_utils.probe_duration = old_probe

        assert starts == [5] and summary["clips"] == 2


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except Exception:
                failures += 1; print(f"FAIL {name}"); traceback.print_exc()
    raise SystemExit(1 if failures else 0)
