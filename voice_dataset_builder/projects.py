"""Project (dataset folder) management for the web UI.

A "project" is just a dataset output folder. New projects live under
``projects/<name>/``. Pre-existing datasets at the repo root (e.g. the legacy
``my_voice_dataset``) are also surfaced so nothing is lost.

The folder name *is* the project name, so the UI no longer needs a separate
"output folder" field, and a project is addressable by URL: ``/<name>``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

PROJECTS_DIRNAME = "projects"
BUILD_INPUTS_FILE = "build_inputs.json"

# Folders at the repo root that are never projects.
_ROOT_IGNORE = {
    "projects", "uploads", "models", "tests", "voice_dataset_builder",
    ".venv", ".git", "__pycache__", ".idea", ".vscode",
}


def projects_root(base: Optional[Path] = None) -> Path:
    base = Path(base) if base else Path.cwd()
    return base / PROJECTS_DIRNAME


def sanitize_name(name: str) -> str:
    """Turn a user-entered project name into a safe single folder name."""
    name = (name or "").strip()
    # collapse to a slug: keep alnum, dash, underscore, space -> underscore
    name = name.replace("/", "_").replace("\\", "_")
    keep = []
    for ch in name:
        if ch.isalnum() or ch in "-_":
            keep.append(ch)
        elif ch in " .":
            keep.append("_")
    slug = "".join(keep).strip("._")
    slug = re.sub(r"_{2,}", "_", slug)
    return slug[:64]


def _looks_like_project(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "audios").is_dir():
        return True
    if (path / ".resume_state.json").exists():
        return True
    if (path / "config.json").exists():
        return True
    if (path / BUILD_INPUTS_FILE).exists():
        return True
    if (path / "metadata_train.jsonl").exists():
        return True
    return False


@dataclass
class ProjectInfo:
    name: str
    path: str
    clips: int
    resumable: bool
    partial: bool
    speaker_id: Optional[str]
    sample_rate: Optional[int]
    total_audio_min: Optional[float]
    modified: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "clips": self.clips,
            "resumable": self.resumable,
            "partial": self.partial,
            "speaker_id": self.speaker_id,
            "sample_rate": self.sample_rate,
            "total_audio_min": self.total_audio_min,
            "modified": self.modified,
        }


def _inspect(path: Path, name: str) -> ProjectInfo:
    audios = path / "audios"
    clips = 0
    if audios.is_dir():
        clips = sum(1 for _ in audios.glob("*.wav"))
    resumable = (path / ".resume_state.json").exists()
    partial = False
    speaker_id = None
    sample_rate = None
    total_min = None
    cfg = path / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            speaker_id = data.get("speaker_id")
            sample_rate = data.get("sample_rate")
            summ = data.get("summary") or {}
            partial = bool(summ.get("partial"))
            total_min = summ.get("total_audio_min")
        except Exception:  # noqa: BLE001
            pass
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return ProjectInfo(
        name=name, path=str(path), clips=clips, resumable=resumable,
        partial=partial, speaker_id=speaker_id, sample_rate=sample_rate,
        total_audio_min=total_min, modified=modified,
    )


def list_projects(base: Optional[Path] = None) -> List[ProjectInfo]:
    base = Path(base) if base else Path.cwd()
    found: dict[str, ProjectInfo] = {}

    # 1. projects/<name> -- every folder here is an intentional project.
    root = projects_root(base)
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                found[child.name] = _inspect(child, child.name)

    # 2. legacy datasets sitting at the repo root
    for child in base.iterdir():
        if child.name in _ROOT_IGNORE or child.name.startswith("."):
            continue
        if child.name in found:
            continue
        if _looks_like_project(child):
            found[child.name] = _inspect(child, child.name)

    return sorted(found.values(), key=lambda p: p.modified, reverse=True)


def resolve_project_dir(name: str, base: Optional[Path] = None) -> Optional[Path]:
    """Return the on-disk folder for an existing project, or None."""
    base = Path(base) if base else Path.cwd()
    slug = sanitize_name(name)
    if not slug:
        return None
    candidate = projects_root(base) / slug
    if _looks_like_project(candidate) or candidate.is_dir():
        return candidate
    legacy = base / slug
    if legacy != candidate and (_looks_like_project(legacy) or legacy.is_dir()):
        return legacy
    return None


def project_exists(name: str, base: Optional[Path] = None) -> bool:
    return resolve_project_dir(name, base) is not None


def create_project(name: str, base: Optional[Path] = None) -> Path:
    """Create a new empty project folder under projects/ and return its path."""
    base = Path(base) if base else Path.cwd()
    slug = sanitize_name(name)
    if not slug:
        raise ValueError("Please enter a valid project name.")
    root = projects_root(base)
    root.mkdir(parents=True, exist_ok=True)
    target = root / slug
    if target.exists():
        raise ValueError(f"A project named '{slug}' already exists.")
    target.mkdir(parents=True)
    return target


def save_build_inputs(project_dir: Path, payload: dict) -> None:
    """Remember the form values used for a build so Resume can restore them."""
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in (payload or {}).items()
                if k not in ("output_dir", "project")}
        (project_dir / BUILD_INPUTS_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass


def load_build_inputs(project_dir: Path) -> dict:
    """Return the saved form values for a project, or an empty dict."""
    path = project_dir / BUILD_INPUTS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}

def load_project_clips(project_dir: Path) -> List[dict]:
    """Return the dataset clips for a project for read/edit in the UI.

    Prefers finished metadata (train+val JSONL); falls back to the in-progress
    resume state; finally lists bare ``audios/*.wav`` with empty text. Each row:
    ``{clip_id, audio_path, text, duration}`` with ``audio_path`` relative to
    the project folder (e.g. ``audios/clip_0001.wav``).
    """
    project_dir = Path(project_dir)

    def _cid(audio_path: str) -> str:
        name = audio_path.split("/")[-1]
        return name.rsplit(".", 1)[0]

    rows: List[dict] = []
    seen = set()

    def _add(audio_path: str, text: str, duration) -> None:
        if not audio_path or audio_path in seen:
            return
        seen.add(audio_path)
        rows.append({
            "clip_id": _cid(audio_path),
            "audio_path": audio_path,
            "text": text or "",
            "duration": round(float(duration), 3) if duration else None,
        })

    # 1. finished metadata
    for fname in ("metadata_train.jsonl", "metadata_val.jsonl"):
        path = project_dir / fname
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            _add(
                obj.get("audio_path") or obj.get("file_name", ""),
                obj.get("text", ""),
                obj.get("duration"),
            )

    # 2. in-progress resume state
    if not rows:
        state_path = project_dir / ".resume_state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                state = {}
            for rec in state.get("records", []):
                _add(
                    rec.get("audio_path") or rec.get("file_name", ""),
                    rec.get("text", ""),
                    rec.get("duration"),
                )

    # 3. bare audio files
    audios = project_dir / "audios"
    if audios.is_dir():
        for wav in sorted(audios.glob("*.wav")):
            _add(f"audios/{wav.name}", "", None)

    rows.sort(key=lambda r: r["audio_path"])
    return rows
