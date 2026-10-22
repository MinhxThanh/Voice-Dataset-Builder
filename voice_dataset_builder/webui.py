"""Local web UI for the voice dataset builder (stdlib only)."""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .asr_models import ASR_DOWNLOADS, list_asr_models
from .config import BuildConfig
from .metadata import update_clip_text
from .pipeline import PHASES, BuildCancelled, build_dataset
from .projects import (
    create_project,
    list_projects,
    load_build_inputs,
    load_project_clips,
    resolve_project_dir,
    sanitize_name,
    save_build_inputs,
)
from .presets import PRESETS


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error | cancelled
    logs: List[str] = field(default_factory=list)
    phase: str = "download"
    phase_frac: float = 0.0
    overall: float = 0.0
    summary: Optional[dict] = None
    preview: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    output_dir: Optional[str] = None
    text_overrides: Dict[str, str] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def append(self, line: str) -> None:
        with self.lock:
            self.logs.append(line)

    def append_preview(self, item: dict) -> None:
        with self.lock:
            self.preview.append(item)

    def set_text(self, clip_id: str, text: str) -> None:
        with self.lock:
            self.text_overrides[clip_id] = text

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def cancel_requested(self) -> bool:
        return self.cancel_event.is_set()

    def set_progress(self, phase: str, frac: float) -> None:
        with self.lock:
            self.phase = phase
            self.phase_frac = frac
            try:
                idx = PHASES.index(phase)
            except ValueError:
                idx = 0
            self.overall = (idx + frac) / len(PHASES)

    def snapshot(self, since: int, preview_since: int = 0) -> dict:
        with self.lock:
            overrides = self.text_overrides

            def _apply(rows):
                if not overrides:
                    return rows
                out = []
                for r in rows:
                    cid = r.get("clip_id")
                    if cid is None and r.get("audio_path"):
                        cid = r["audio_path"].split("/")[-1].rsplit(".", 1)[0]
                    if cid in overrides:
                        r = {**r, "text": overrides[cid]}
                    out.append(r)
                return out

            summary = self.summary
            if summary and overrides and summary.get("preview"):
                summary = {**summary, "preview": _apply(summary["preview"])}

            return {
                "status": self.status,
                "logs": self.logs[since:],
                "total": len(self.logs),
                "preview": _apply(self.preview[preview_since:]),
                "preview_total": len(self.preview),
                "phase": self.phase,
                "phase_frac": round(self.phase_frac, 3),
                "overall": round(self.overall, 3),
                "summary": summary,
                "error": self.error,
                "output_dir": self.output_dir,
            }


def _persist_text_overrides(job: Job) -> None:
    if not job.output_dir:
        return
    with job.lock:
        for clip_id, text in job.text_overrides.items():
            try:
                update_clip_text(Path(job.output_dir), f"audios/{clip_id}.wav", text)
            except Exception as exc:  # noqa: BLE001
                job.logs.append(f"[warn] could not save edit for {clip_id}: {exc}")


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def create(self) -> Job:
        with self._lock:
            self._counter += 1
            job = Job(id=str(self._counter))
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status == "running":
            job.request_cancel()
        return True

    def run(self, job: Job, config: BuildConfig) -> None:
        job.output_dir = str(config.output_dir)

        def _worker() -> None:
            try:
                summary = build_dataset(
                    config,
                    log=job.append,
                    progress=job.set_progress,
                    preview=job.append_preview,
                    should_cancel=job.cancel_requested,
                )
                _persist_text_overrides(job)
                with job.lock:
                    job.summary = summary
                    job.status = "done"
                    job.overall = 1.0
            except BuildCancelled:
                job.append("Build cancelled by user.")
                _persist_text_overrides(job)
                with job.lock:
                    job.status = "cancelled"
            except Exception as exc:  # noqa: BLE001
                job.append(f"ERROR: {exc}")
                job.append(traceback.format_exc())
                _persist_text_overrides(job)
                with job.lock:
                    job.error = str(exc)
                    job.status = "error"

        threading.Thread(target=_worker, daemon=True).start()


MANAGER = JobManager()
UPLOAD_DIR = Path("uploads")


def _as_bool(val, default=False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _safe_upload_name(name: str) -> str:
    base = Path(name or "audio").name
    path = Path(base)
    keep = "-_.() "
    stem = "".join(ch if ch.isalnum() or ch in keep else "_" for ch in path.stem)
    stem = stem.strip().strip(".") or "audio"
    suffix = path.suffix[:16]
    return f"{stem}{suffix}"


def _unique_upload_path(filename: str) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe_upload_name(filename)
    target = UPLOAD_DIR / safe
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(2, 10000):
        candidate = UPLOAD_DIR / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Too many uploaded files with the same name.")


def _project_output_dir(name: str) -> Path:
    """Resolve the dataset folder for a project name (existing or new)."""
    existing = resolve_project_dir(name)
    if existing is not None:
        return existing
    slug = sanitize_name(name)
    if not slug:
        raise ValueError("Please enter a valid project name.")
    return Path("projects") / slug


def _config_from_payload(data: dict) -> BuildConfig:
    raw_urls = data.get("urls", "")
    if isinstance(raw_urls, str):
        urls = [u.strip() for u in raw_urls.splitlines()
                if u.strip() and not u.strip().startswith("#")]
    else:
        urls = [str(u).strip() for u in raw_urls if str(u).strip()]

    raw_local = data.get("local_sources", "")
    if isinstance(raw_local, str):
        local = [u.strip() for u in raw_local.splitlines() if u.strip()]
    else:
        local = [str(u).strip() for u in raw_local if str(u).strip()]

    def _num(key, cast, default):
        val = data.get(key, "")
        if val in ("", None):
            return default
        try:
            return cast(val)
        except (TypeError, ValueError):
            return default

    language = (data.get("language") or "").strip() or None
    clip_prefix = (data.get("clip_prefix") or "").strip() or None
    initial_prompt = (data.get("initial_prompt") or "").strip() or None

    fmt = data.get("output_formats")
    if isinstance(fmt, str):
        formats = [fmt] if fmt else ["universal"]
    elif isinstance(fmt, list) and fmt:
        formats = fmt
    else:
        formats = ["universal"]

    min_conf = data.get("min_confidence")
    min_conf = None if min_conf in ("", None) else float(min_conf)
    limit = data.get("limit_seconds")
    limit = None if limit in ("", None) else float(limit)

    project_name = (data.get("project") or data.get("output_dir") or "").strip()
    output_dir = _project_output_dir(project_name)
    return BuildConfig(
        urls=urls,
        local_sources=local,
        output_dir=output_dir,
        speaker_id=(data.get("speaker_id") or "speaker_01").strip(),
        language=language,
        sample_rate=_num("sample_rate", int, 24000),
        channels=_num("channels", int, 1),
        sample_width_bits=_num("bits", int, 16),
        min_clip_sec=_num("min_clip", float, 3.0),
        max_clip_sec=_num("max_clip", float, 12.0),
        merge_gap_sec=_num("merge_gap", float, 0.4),
        loudnorm=_as_bool(data.get("loudnorm"), True),
        loudnorm_lufs=_num("loudnorm_lufs", float, -23.0),
        loudnorm_two_pass=_as_bool(data.get("loudnorm_two_pass"), False),
        remove_silence=_as_bool(data.get("remove_silence"), True),
        silence_threshold_db=_num("silence_threshold_db", float, -45.0),
        highpass_hz=_num("highpass_hz", int, 0),
        denoise=_as_bool(data.get("denoise"), False),
        demucs_model=(data.get("demucs_model") or "htdemucs").strip(),
        whisper_model=(data.get("whisper_model") or "base").strip(),
        whisper_backend=(data.get("whisper_backend") or "auto").strip(),
        device=(data.get("device") or "auto").strip(),
        compute_type=(data.get("compute_type") or "auto").strip(),
        initial_prompt=initial_prompt,
        min_confidence=min_conf,
        prefer_subtitles=_as_bool(data.get("prefer_subtitles"), False),
        val_ratio=_num("val_ratio", float, 0.1),
        output_formats=formats,
        clip_prefix=clip_prefix,
        keep_source_audio=_as_bool(data.get("keep_source_audio"), False),
        make_references=_as_bool(data.get("make_references"), True),
        limit_seconds=limit,
    )


def _reveal_in_file_manager(target: Path) -> None:
    """Open ``target`` in the native file manager (Finder/Explorer/xdg).

    For files, this *reveals* them inside their containing folder when the OS
    supports it (macOS Finder, Windows Explorer). For directories, the folder
    itself is opened. Falls back to ``webbrowser.open(file://...)`` so the
    button always does *something* even on unusual desktops.
    """
    target = Path(target)
    plat = sys.platform
    try:
        if plat == "darwin":
            # `-R` reveals a file within its folder; for directories, drop -R.
            args = ["open"] + (["-R"] if target.is_file() else []) + [str(target)]
            subprocess.Popen(args)
            return
        if plat.startswith("win"):
            if target.is_file():
                # explorer /select,"C:\path\to\file"
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                subprocess.Popen(["explorer", str(target)])
            return
        # Linux / *BSD: xdg-open opens the folder; for a file we open the
        # parent so the user lands in the right place.
        opener = shutil.which("xdg-open") or shutil.which("gio") or shutil.which("gnome-open")
        folder = target if target.is_dir() else target.parent
        if opener:
            subprocess.Popen([opener, str(folder)])
            return
    except OSError:
        pass
    # Last resort: file:// URL through the default browser.
    webbrowser.open((target if target.is_dir() else target.parent).as_uri())


class Handler(BaseHTTPRequestHandler):
    server_version = "VoiceDatasetUI/0.2"

    def log_message(self, *args) -> None:
        pass

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "file not found"}, status=404)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def _handle_edit_clip(self, data: dict) -> None:
        job_id = (data.get("job_id") or "").strip()
        project = (data.get("project") or "").strip()
        clip_id = (data.get("clip_id") or "").strip()
        text = data.get("text")
        if not clip_id or text is None or (not job_id and not project):
            self._send_json(
                {"error": "clip_id, text and a job_id or project are required"},
                status=400,
            )
            return
        if clip_id in (".", "..") or "/" in clip_id or "\\" in clip_id:
            self._send_json({"error": "invalid clip_id"}, status=400)
            return
        text = str(text).strip()
        output_dir = None
        job = MANAGER.get(job_id) if job_id else None
        if job:
            output_dir = Path(job.output_dir) if job.output_dir else None
            # Remember the edit so live snapshots/summary reflect it too.
            job.set_text(clip_id, text)
        elif project:
            proj_dir = resolve_project_dir(project)
            if proj_dir is not None:
                output_dir = proj_dir
        if output_dir is None:
            self._send_json({"error": "clip source not found"}, status=404)
            return
        audio_path = f"audios/{clip_id}.wav"
        try:
            persisted = update_clip_text(output_dir, audio_path, text)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"save failed: {exc}"}, status=500)
            return
        self._send_json({"ok": True, "clip_id": clip_id, "persisted": persisted})

    def _handle_open(self, data: dict) -> None:
        """Reveal a project subfolder in the platform-native file manager.

        Body: ``{project: str, subpath: str | optional}``. ``subpath`` is
        resolved relative to the project folder and must stay inside it; if
        omitted, the project folder itself is opened. Returns
        ``{ok, opened}`` with the resolved absolute path on success.
        """
        project = (data.get("project") or "").strip()
        subpath = (data.get("subpath") or "").strip().lstrip("/").lstrip("\\")
        if not project:
            self._send_json({"error": "project is required"}, status=400)
            return
        proj_dir = resolve_project_dir(project)
        if proj_dir is None or not proj_dir.is_dir():
            self._send_json({"error": "project not found"}, status=404)
            return
        root = Path(proj_dir).resolve()
        target = (root / subpath).resolve() if subpath else root
        # No path traversal.
        if target != root and root not in target.parents:
            self._send_json({"error": "forbidden"}, status=403)
            return
        if not target.exists():
            self._send_json(
                {"error": f"path not found: {subpath or '.'}"}, status=404
            )
            return
        try:
            _reveal_in_file_manager(target)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"open failed: {exc}"}, status=500)
            return
        self._send_json({"ok": True, "opened": str(target)})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._send_html(PAGE)
            return
        if path.startswith("/assets/"):
            # Serve bundled static assets (e.g. pet sprite). Clamp to repo assets dir.
            assets_root = (Path(__file__).resolve().parent.parent / "assets").resolve()
            rel = path[len("/assets/"):].lstrip("/")
            target = (assets_root / rel).resolve()
            if assets_root not in target.parents and target != assets_root:
                self._send_json({"error": "forbidden"}, status=403)
                return
            self._send_file(target)
            return
        if path == "/api/projects":
            self._send_json({"projects": [p.to_dict() for p in list_projects()]})
            return
        if path.startswith("/api/project/"):
            name = unquote(path[len("/api/project/"):])
            self._send_project_info(name)
            return
        if path == "/api/presets":
            self._send_json({"presets": PRESETS})
            return
        if path == "/api/asr-models":
            self._send_json({"models": list_asr_models()})
            return
        if path.startswith("/api/asr-download/"):
            job_id = path.rsplit("/", 1)[-1]
            qs = parse_qs(parsed.query)
            since = int(qs.get("since", ["0"])[0] or 0)
            job = ASR_DOWNLOADS.get(job_id)
            if not job:
                self._send_json({"error": "download job not found"}, status=404)
                return
            self._send_json(job.snapshot(since))
            return
        if path.startswith("/api/job/"):
            job_id = path.rsplit("/", 1)[-1]
            qs = parse_qs(parsed.query)
            since = int(qs.get("since", ["0"])[0] or 0)
            preview_since = int(qs.get("preview_since", ["0"])[0] or 0)
            job = MANAGER.get(job_id)
            if not job:
                self._send_json({"error": "job not found"}, status=404)
                return
            self._send_json(job.snapshot(since, preview_since))
            return
        if path == "/api/clip":
            qs = parse_qs(parsed.query)
            job_id = qs.get("job", [""])[0]
            project = unquote(qs.get("project", [""])[0])
            rel = unquote(qs.get("path", [""])[0])
            output_dir = None
            if project:
                proj_dir = resolve_project_dir(project)
                if proj_dir is not None:
                    output_dir = proj_dir
            else:
                job = MANAGER.get(job_id)
                if job and job.output_dir:
                    output_dir = Path(job.output_dir)
            if output_dir is None:
                self._send_json({"error": "clip source not found"}, status=404)
                return
            # Restrict reads to the dataset dir (no path traversal).
            root = Path(output_dir).resolve()
            target = (root / rel).resolve()
            if root not in target.parents and target != root:
                self._send_json({"error": "forbidden"}, status=403)
                return
            self._send_file(target)
            return
        # Any other single-segment path is a project page (addressable by URL).
        if path.startswith("/") and "/" not in path[1:] and not path.startswith("/api"):
            self._send_html(PAGE)
            return
        self._send_json({"error": "not found"}, status=404)

    def _send_project_info(self, name: str) -> None:
        proj_dir = resolve_project_dir(name)
        if proj_dir is None or not proj_dir.is_dir():
            self._send_json({"error": "project not found"}, status=404)
            return
        inputs = load_build_inputs(proj_dir)
        resumable = (proj_dir / ".resume_state.json").exists()
        try:
            clips = load_project_clips(proj_dir)
        except Exception:  # noqa: BLE001
            clips = []
        self._send_json({
            "name": proj_dir.name,
            "path": str(proj_dir),
            "inputs": inputs,
            "resumable": resumable,
            "clips": clips,
        })

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/upload-local":
            filename = self.headers.get("X-Filename", "audio")
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                self._send_json({"error": "empty upload"}, status=400)
                return
            try:
                target = _unique_upload_path(unquote(filename))
                with target.open("wb") as fh:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        fh.write(chunk)
                        remaining -= len(chunk)
                if remaining:
                    raise RuntimeError("upload ended before all bytes were received")
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"path": str(target), "name": target.name, "size": target.stat().st_size})
            return
        if path not in ("/api/build", "/api/asr-download", "/api/cancel",
                        "/api/edit-clip", "/api/create-project", "/api/open"):
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, status=400)
            return
        if path == "/api/open":
            self._handle_open(data)
            return
        if path == "/api/edit-clip":
            self._handle_edit_clip(data)
            return
        if path == "/api/create-project":
            name = (data.get("name") or "").strip()
            try:
                proj = create_project(name)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"name": proj.name, "path": str(proj)})
            return
        if path == "/api/cancel":
            job_id = (data.get("job_id") or "").strip()
            if not MANAGER.cancel(job_id):
                self._send_json({"error": "job not found"}, status=404)
                return
            self._send_json({"ok": True, "job_id": job_id})
            return
        if path == "/api/asr-download":
            model_id = (data.get("model_id") or "").strip()
            token = (data.get("hf_token") or "").strip() or None
            try:
                job = ASR_DOWNLOADS.create(model_id, token)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"job_id": job.id, "models": list_asr_models()})
            return
        try:
            config = _config_from_payload(data)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=400)
            return
        if not config.urls and not config.local_sources:
            self._send_json(
                {"error": "Provide at least one YouTube URL or local file."},
                status=400,
            )
            return
        try:
            save_build_inputs(config.output_dir, data)
        except Exception:  # noqa: BLE001
            pass
        job = MANAGER.create()
        MANAGER.run(job, config)
        self._send_json({"job_id": job.id, "project": config.output_dir.name})


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Voice Dataset Builder UI running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        httpd.server_close()


# PAGE is defined in webui_page.py to keep this module focused on logic.
from .webui_page import PAGE  # noqa: E402
