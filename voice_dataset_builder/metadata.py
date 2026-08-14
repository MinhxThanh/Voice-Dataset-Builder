"""Dataset record model and metadata writers for multiple TTS formats."""

from __future__ import annotations

import csv
import json
import random
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class Record:
    audio_path: str   # relative to dataset root, e.g. "audios/thanh_0001.wav"
    text: str
    speaker_id: str
    language: str
    duration: float

    def to_jsonl_obj(self) -> dict:
        return {
            "audio_path": self.audio_path,
            "text": self.text,
            "speaker_id": self.speaker_id,
            "language": self.language,
            "duration": round(self.duration, 3),
        }


def split_records(
    records: List[Record], val_ratio: float, seed: int
) -> Tuple[List[Record], List[Record]]:
    if val_ratio <= 0 or len(records) < 2:
        return records, []
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    n_val = max(1, int(round(len(shuffled) * val_ratio)))
    n_val = min(n_val, len(shuffled) - 1)
    return shuffled[n_val:], shuffled[:n_val]


def write_jsonl(records: List[Record], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_jsonl_obj(), ensure_ascii=False) + "\n")


def write_ljspeech_csv(
    records: List[Record], path: Path, delimiter: str = "|"
) -> None:
    """LJSpeech ``metadata.csv``: ``ID|Transcription|NormalizedTranscription``.

    Matches the official LJ-Speech spec (one record per line, pipe-delimited,
    three fields) and the Coqui TTS ``formatter="ljspeech"`` parser, which
    reads ``cols[0]`` as the clip ID and ``cols[2]`` as the text. ``ID`` is the
    wav basename without the ``.wav`` extension. We duplicate the text into the
    Normalized column because we don't run a separate text normalizer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        for rec in records:
            clip_id = rec.audio_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            writer.writerow([clip_id, rec.text, rec.text])


def ensure_ljspeech_wavs_link(dataset_root: Path, audios_dirname: str = "audios") -> Path:
    """Materialize ``<dataset_root>/wavs`` so XTTS's ``formatter="ljspeech"``
    finds clips at ``wavs/<id>.wav`` without the user touching paths.

    Prefers a symlink (free, ~0 bytes). Falls back to copying the wavs on
    filesystems that reject symlinks (e.g. exFAT, some Windows configs). Safe
    to call repeatedly: an existing valid link/dir is left alone, and the
    audios directory remains the source of truth so partial-build edits keep
    working.
    """
    dataset_root = Path(dataset_root)
    src = dataset_root / audios_dirname
    link = dataset_root / "wavs"
    if not src.is_dir():
        return link

    # Already correct? leave it alone.
    if link.is_symlink():
        try:
            if (dataset_root / os.readlink(link)).resolve() == src.resolve():
                return link
        except OSError:
            pass
        try:
            link.unlink()
        except OSError:
            pass
    elif link.exists():
        # A real directory (likely a previous copy fallback). Refresh it so new
        # clips show up without orphaning old ones.
        if link.is_dir() and not link.is_symlink():
            for wav in src.glob("*.wav"):
                dst = link / wav.name
                if not dst.exists():
                    try:
                        shutil.copy2(wav, dst)
                    except OSError:
                        pass
            return link
        return link

    try:
        os.symlink(audios_dirname, link, target_is_directory=True)
        return link
    except (OSError, NotImplementedError):
        # Filesystem doesn't allow symlinks; copy instead so XTTS still works.
        link.mkdir(parents=True, exist_ok=True)
        for wav in src.glob("*.wav"):
            try:
                shutil.copy2(wav, link / wav.name)
            except OSError:
                pass
        return link


# GPT-SoVITS only accepts these language tokens (case-insensitive upstream):
# zh, ja, en, ko, yue.  Anything else is mapped to en with a fallback.
_SOVITS_LANG_MAP = {
    "zh": "zh", "zh-cn": "zh", "zh-tw": "zh", "cmn": "zh",
    "ja": "ja", "jp": "ja",
    "en": "en", "en-us": "en", "en-gb": "en",
    "ko": "ko", "kr": "ko",
    "yue": "yue", "cantonese": "yue",
}


def _sovits_lang(lang: str) -> str:
    key = (lang or "").strip().lower().split("-")[0]
    return _SOVITS_LANG_MAP.get(key) or _SOVITS_LANG_MAP.get((lang or "").lower(), "en")


def write_gpt_sovits(records: List[Record], path: Path) -> None:
    """GPT-SoVITS ``.list`` format: ``wav_path|speaker|language|text``.

    Audio paths are resolved from the dataset folder and written as native
    absolute paths, so the list works regardless of GPT-SoVITS's working
    directory on macOS, Linux, or Windows.

    Upstream (`GPT_SoVITS/prepare_datasets/1-get-text.py`) accepts language
    tokens in {zh, ja, en, ko, yue} (case-insensitive) and rejects everything
    else with a "language not supported" warning. We coerce here so a Vietnamese
    or French build still trains (mapped to ``en``) instead of being silently
    dropped during preprocessing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset_root = path.parent.resolve()
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            lang = _sovits_lang(rec.language)
            audio_path = (dataset_root / rec.audio_path).resolve()
            fh.write(f"{audio_path}|{rec.speaker_id}|{lang}|{rec.text}\n")


def write_fish_labs(records: List[Record], dataset_root: Path) -> int:
    """Fish Speech style: ``<dataset_root>/fish/<speaker>/<clip>.{wav,lab}``.

    Matches the layout in Fish Speech's `docs/en/finetune.md` ("per-speaker
    subfolder with paired ``.lab`` + audio"), so users can point the build
    scripts straight at ``<dataset_root>/fish`` without re-arranging files.

    The wav under ``audios/`` stays the source of truth; we materialize the
    Fish layout with symlinks when the filesystem allows it (free) and fall
    back to copies otherwise. Returns the number of ``.lab`` files written.
    """
    dataset_root = Path(dataset_root)
    fish_root = dataset_root / "fish"
    count = 0
    for rec in records:
        clip_name = rec.audio_path.rsplit("/", 1)[-1]
        stem = clip_name.rsplit(".", 1)[0]
        spk_dir = fish_root / (rec.speaker_id or "speaker_01")
        spk_dir.mkdir(parents=True, exist_ok=True)

        # Pair: <stem>.lab (transcript) + <stem>.wav (audio link/copy).
        lab = spk_dir / f"{stem}.lab"
        lab.write_text(rec.text, encoding="utf-8")

        wav_src = dataset_root / rec.audio_path
        wav_dst = spk_dir / clip_name
        if wav_src.exists() and not wav_dst.exists():
            try:
                rel = os.path.relpath(wav_src, spk_dir)
                os.symlink(rel, wav_dst)
            except (OSError, NotImplementedError):
                try:
                    shutil.copy2(wav_src, wav_dst)
                except OSError:
                    pass
        count += 1
    return count


def update_clip_text(
    dataset_root: Path,
    audio_path: str,
    new_text: str,
    csv_delimiter: str = "|",
) -> bool:
    """Rewrite a single clip's transcription across whatever dataset files exist.

    Matches rows by ``audio_path`` (relative, e.g. ``audios/clip_0001.wav``) and
    updates train/val JSONL, LJSpeech CSV, the GPT-SoVITS list, and the Fish
    ``.lab`` sidecar when present. Returns True if at least one file changed.
    """
    root = Path(dataset_root)
    new_text = (new_text or "").strip()
    changed = False

    def _rewrite_jsonl(path: Path) -> None:
        nonlocal changed
        if not path.exists():
            return
        out = []
        hit = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            if (obj.get("audio_path") or obj.get("file_name")) == audio_path:
                obj["text"] = new_text
                hit = True
            out.append(json.dumps(obj, ensure_ascii=False))
        if hit:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
            changed = True

    def _rewrite_delimited(path: Path, text_index: int, delim: str) -> None:
        nonlocal changed
        if not path.exists():
            return
        out = []
        hit = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                out.append(line)
                continue
            parts = line.split(delim)
            if parts and parts[0] == audio_path and len(parts) > text_index:
                parts[text_index] = new_text
                hit = True
            out.append(delim.join(parts))
        if hit:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
            changed = True

    def _rewrite_ljspeech_csv(path: Path, delim: str) -> None:
        """LJSpeech rows are ``clip_id|text|normalized_text`` keyed by clip_id."""
        nonlocal changed
        if not path.exists():
            return
        clip_id = audio_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        out, hit = [], False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                out.append(line); continue
            parts = line.split(delim)
            if parts and parts[0] == clip_id and len(parts) >= 2:
                parts[1] = new_text
                if len(parts) >= 3:
                    parts[2] = new_text
                hit = True
            out.append(delim.join(parts))
        if hit:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
            changed = True

    _rewrite_jsonl(root / "metadata_train.jsonl")
    _rewrite_jsonl(root / "metadata_val.jsonl")
    # LJSpeech CSV: clip_id<delim>text<delim>normalized_text
    _rewrite_ljspeech_csv(root / "metadata.csv", csv_delimiter)
    # GPT-SoVITS list: audio_path|speaker|lang|text
    _rewrite_delimited(root / "metadata.list", 3, "|")
    # Fish Speech .lab sidecar. Current layout: fish/<speaker>/<stem>.lab.
    # We don't know the speaker here, so update every matching .lab found
    # under fish/* (typically one). Also support legacy builds that wrote
    # the .lab next to the wav under audios/.
    stem = audio_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for lab in (root / "fish").glob(f"*/{stem}.lab"):
        lab.write_text(new_text, encoding="utf-8")
        changed = True
    legacy_lab = (root / audio_path).with_suffix(".lab")
    if legacy_lab.exists():
        legacy_lab.write_text(new_text, encoding="utf-8")
        changed = True

    # Resume state: keep partial-build records in sync so a later Resume
    # (and the partial dataset view) reflect the edit.
    state_path = root / ".resume_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            hit = False
            for rec in state.get("records", []):
                if (rec.get("audio_path") or rec.get("file_name")) == audio_path:
                    rec["text"] = new_text
                    hit = True
            if hit:
                state_path.write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8"
                )
                changed = True
        except Exception:  # noqa: BLE001
            pass
    return changed
