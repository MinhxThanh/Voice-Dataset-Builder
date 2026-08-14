"""Optional Hugging Face ASR model registry + local downloader."""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


MODELS_DIR = Path("models")


ASR_MODELS = {
    "Qwen/Qwen3-ASR-1.7B": {
        "label": "Qwen3-ASR-1.7B",
        "local_dir": "Qwen3-ASR-1.7B",
        "requires_token": False,
        "type": "qwen3_asr",
    },
    "CohereLabs/cohere-transcribe-03-2026": {
        "label": "Cohere Transcribe 03-2026",
        "local_dir": "Cohere-Transcribe-03-2026",
        "requires_token": True,
        "type": "cohere",
    },
    "Qwen/Qwen3-ASR-0.6B": {
        "label": "Qwen3-ASR-0.6B",
        "local_dir": "Qwen3-ASR-0.6B",
        "requires_token": False,
        "type": "qwen3_asr",
    },
}


def model_local_path(model_id: str) -> Path:
    meta = ASR_MODELS[model_id]
    return MODELS_DIR / meta["local_dir"]


def is_model_downloaded(model_id: str) -> bool:
    """Return true when the model folder has real downloaded content."""

    local = model_local_path(model_id)
    return local.is_dir() and any(local.iterdir())


def is_asr_model(model: str) -> bool:
    return model in ASR_MODELS or model.startswith("models/") or model.startswith("./models/")


def resolve_model_path(model: str) -> str:
    if model in ASR_MODELS:
        local = model_local_path(model)
        return str(local) if is_model_downloaded(model) else model
    return model


def list_asr_models() -> List[dict]:
    models = []
    for model_id, meta in ASR_MODELS.items():
        local = model_local_path(model_id)
        models.append(
            {
                "id": model_id,
                "label": meta["label"],
                "local_dir": str(local),
                "downloaded": is_model_downloaded(model_id),
                "requires_token": meta["requires_token"],
                "type": meta["type"],
            }
        )
    return models


@dataclass
class DownloadJob:
    id: str
    model_id: str
    status: str = "running"  # running | done | error
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, line: str) -> None:
        with self.lock:
            self.logs.append(line)

    def snapshot(self, since: int) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "model_id": self.model_id,
                "logs": self.logs[since:],
                "total": len(self.logs),
                "error": self.error,
                "models": list_asr_models(),
            }


class AsrDownloadManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, DownloadJob] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def create(self, model_id: str, token: Optional[str]) -> DownloadJob:
        if model_id not in ASR_MODELS:
            raise ValueError("Unknown ASR model.")
        if ASR_MODELS[model_id]["requires_token"] and not token:
            raise ValueError("This model needs a Hugging Face token with access.")
        with self._lock:
            self._counter += 1
            job = DownloadJob(id=str(self._counter), model_id=model_id)
            self._jobs[job.id] = job
        self._run(job, token)
        return job

    def get(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)

    def _run(self, job: DownloadJob, token: Optional[str]) -> None:
        def _worker() -> None:
            try:
                from huggingface_hub import snapshot_download

                local = model_local_path(job.model_id)
                local.parent.mkdir(parents=True, exist_ok=True)
                job.append(f"Downloading {job.model_id}...")
                job.append(f"Saving to {local}")
                snapshot_download(
                    repo_id=job.model_id,
                    local_dir=str(local),
                    token=token or None,
                    ignore_patterns=["*.msgpack", "*.h5"],
                    resume_download=True,
                )
                job.append("Download complete.")
                with job.lock:
                    job.status = "done"
            except Exception as exc:  # noqa: BLE001
                job.append(f"ERROR: {exc}")
                job.append(traceback.format_exc())
                with job.lock:
                    job.error = str(exc)
                    job.status = "error"

        threading.Thread(target=_worker, daemon=True).start()


ASR_DOWNLOADS = AsrDownloadManager()
