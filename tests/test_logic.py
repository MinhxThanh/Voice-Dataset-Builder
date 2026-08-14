"""Unit tests for pure logic (no network or ML deps required)."""

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
from voice_dataset_builder import pipeline
from voice_dataset_builder.downloader import _find_subtitle
from voice_dataset_builder.pipeline import _chunk_ranges
from voice_dataset_builder import projects
from upload_to_hf import _metadata_files


def test_merge_short_segments():
    segs = [Segment(0.0, 1.0, "a"), Segment(1.1, 2.0, "b"), Segment(2.1, 4.0, "c")]
    out = shape_segments(segs, 3.0, 12.0, 0.4)
    assert len(out) == 1 and out[0].text == "a b c" and out[0].duration >= 3.0


def test_split_long_segment():
    out = shape_segments([Segment(0.0, 30.0, "long")], 3.0, 12.0, 0.4)
    assert len(out) == 1 and out[0].duration <= 12.0


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


def test_chunk_ranges_cover_audio_without_tiny_tail():
    ranges = _chunk_ranges(98.0, 3.0, 12.0)
    assert ranges[0] == (0.0, 12.0)
    assert ranges[-1][1] == 98.0
    assert all(end > start for start, end in ranges)
    assert all((end - start) >= 3.0 for start, end in ranges)


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
