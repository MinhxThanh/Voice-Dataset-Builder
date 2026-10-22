"""Transcription (faster-whisper / openai-whisper / subtitles) + segment shaping."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .asr_models import ASR_MODELS, is_asr_model, resolve_model_path


_QWEN_CACHE = {}
_COHERE_CACHE = {}


@dataclass
class Segment:
    start: float
    end: float
    text: str
    confidence: Optional[float] = None  # avg_logprob when available

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Transcript:
    language: str
    segments: List[Segment]


# on_segment(segment) fires as each segment decodes (streaming).
OnSegmentFn = Callable[[Segment], None]


def _select_backend(preferred: str) -> str:
    if preferred in ("faster-whisper", "openai-whisper"):
        return preferred
    try:
        import faster_whisper  # noqa: F401

        return "faster-whisper"
    except Exception:
        pass
    try:
        import whisper  # noqa: F401

        return "openai-whisper"
    except Exception:
        pass
    raise RuntimeError(
        "No Whisper backend installed. Install one of:\n"
        "  pip install faster-whisper   (recommended)\n"
        "  pip install openai-whisper"
    )


def transcribe(
    audio_path: Path,
    model: str = "base",
    backend: str = "auto",
    language: Optional[str] = None,
    device: str = "auto",
    compute_type: str = "auto",
    initial_prompt: Optional[str] = None,
    on_segment: Optional[OnSegmentFn] = None,
) -> Transcript:
    if is_asr_model(model):
        return _transcribe_hf_asr(
            audio_path, model, language, device, compute_type, initial_prompt
        )
    chosen = _select_backend(backend)
    if chosen == "faster-whisper":
        return _transcribe_faster(
            audio_path, model, language, device, compute_type, initial_prompt,
            on_segment=on_segment,
        )
    return _transcribe_openai(audio_path, model, language, device, initial_prompt)


def _dtype_for_device(dev: str):
    import torch

    return torch.float16 if dev == "cuda" else torch.float32


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _transcribe_hf_asr(
    audio_path: Path,
    model: str,
    language: Optional[str],
    device: str,
    compute_type: str,
    initial_prompt: Optional[str],
) -> Transcript:
    resolved = resolve_model_path(model)
    meta = ASR_MODELS.get(model, {})
    if meta.get("type") == "cohere":
        return _transcribe_cohere(audio_path, resolved, language, device)
    if meta.get("type") == "qwen3_asr":
        return _transcribe_qwen3_asr(audio_path, resolved, language, device)
    return _transcribe_transformers_pipeline(
        audio_path, resolved, language, device, compute_type, initial_prompt
    )


def _transcribe_transformers_pipeline(
    audio_path: Path,
    model: str,
    language: Optional[str],
    device: str,
    compute_type: str,
    initial_prompt: Optional[str],
) -> Transcript:
    try:
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "Hugging Face ASR models need transformers and torch. Install with: "
            "pip install transformers torch torchaudio soundfile accelerate"
        ) from exc

    dev = _resolve_device(device)
    pipe_device = 0 if dev == "cuda" else -1
    kwargs = {}
    if language:
        kwargs["language"] = language
    if initial_prompt:
        kwargs["prompt"] = initial_prompt
    asr = pipeline(
        "automatic-speech-recognition",
        model=model,
        device=pipe_device,
        torch_dtype=_dtype_for_device(dev),
    )
    result = asr(str(audio_path), return_timestamps=True, generate_kwargs=kwargs)
    chunks = result.get("chunks") or []
    segments: List[Segment] = []
    for chunk in chunks:
        ts = chunk.get("timestamp") or (None, None)
        text = (chunk.get("text") or "").strip()
        if not text or ts[0] is None or ts[1] is None:
            continue
        segments.append(Segment(start=float(ts[0]), end=float(ts[1]), text=text))
    if not segments and (result.get("text") or "").strip():
        duration = _audio_duration(audio_path)
        segments = [Segment(start=0.0, end=duration, text=result["text"].strip())]
    return Transcript(language=language or "unknown", segments=segments)


def _transcribe_qwen3_asr(
    audio_path: Path,
    model: str,
    language: Optional[str],
    device: str,
) -> Transcript:
    try:
        import torch
        from qwen_asr import Qwen3ASRModel
    except ImportError as exc:
        raise RuntimeError(
            "Qwen3-ASR needs the official qwen-asr package. Install with: "
            "pip install qwen-asr torch torchaudio soundfile accelerate"
        ) from exc

    dev = _resolve_device(device)
    dtype = torch.float16 if dev == "cuda" else torch.float32
    device_map = "cuda:0" if dev == "cuda" else "cpu"
    cache_key = (model, dev)
    qwen = _QWEN_CACHE.get(cache_key)
    if qwen is None:
        qwen = Qwen3ASRModel.from_pretrained(
            model,
            dtype=dtype,
            device_map=device_map,
            max_new_tokens=256,
        )
        _QWEN_CACHE[cache_key] = qwen
    result = qwen.transcribe(audio=str(audio_path), language=_qwen_language(language))[0]
    text = (getattr(result, "text", None) or "").strip()
    detected = getattr(result, "language", None) or language or "unknown"
    if not text:
        return Transcript(language=detected, segments=[])
    return Transcript(
        language=detected,
        segments=[Segment(start=0.0, end=_audio_duration(audio_path), text=text)],
    )


def _qwen_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    mapping = {
        "ar": "Arabic",
        "cs": "Czech",
        "da": "Danish",
        "de": "German",
        "el": "Greek",
        "en": "English",
        "es": "Spanish",
        "fa": "Persian",
        "fi": "Finnish",
        "fil": "Filipino",
        "fr": "French",
        "hi": "Hindi",
        "hu": "Hungarian",
        "id": "Indonesian",
        "it": "Italian",
        "ja": "Japanese",
        "ko": "Korean",
        "mk": "Macedonian",
        "ms": "Malay",
        "nl": "Dutch",
        "pl": "Polish",
        "pt": "Portuguese",
        "ro": "Romanian",
        "ru": "Russian",
        "sv": "Swedish",
        "th": "Thai",
        "tr": "Turkish",
        "vi": "Vietnamese",
        "yue": "Cantonese",
        "zh": "Chinese",
    }
    return mapping.get(language.strip().lower(), language)


def _transcribe_cohere(
    audio_path: Path,
    model: str,
    language: Optional[str],
    device: str,
) -> Transcript:
    try:
        import torch
        import torchaudio
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
    except ImportError as exc:
        raise RuntimeError(
            "Cohere Transcribe needs transformers, torch, and torchaudio. Install with: "
            "pip install transformers torch torchaudio soundfile accelerate"
        ) from exc

    dev = _resolve_device(device)
    cache_key = (model, dev)
    cached = _COHERE_CACHE.get(cache_key)
    if cached is None:
        processor = AutoProcessor.from_pretrained(model)
        cohere = AutoModelForSpeechSeq2Seq.from_pretrained(
            model,
            torch_dtype=_dtype_for_device(dev),
        ).to(dev)
        cached = (processor, cohere)
        _COHERE_CACHE[cache_key] = cached
    processor, cohere = cached
    waveform, sr = torchaudio.load(str(audio_path))
    if sr != 16000:
        waveform = torchaudio.transforms.Resample(sr, 16000)(waveform)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    inputs = processor(
        waveform.squeeze(), sampling_rate=16000, return_tensors="pt"
    ).to(dev)
    generate_kwargs = {}
    if language:
        generate_kwargs["language"] = language
    with torch.no_grad():
        generated = cohere.generate(**inputs, **generate_kwargs)
    text = processor.batch_decode(generated, skip_special_tokens=True)[0].strip()
    if not text:
        return Transcript(language=language or "unknown", segments=[])
    return Transcript(
        language=language or "unknown",
        segments=[Segment(start=0.0, end=_audio_duration(audio_path), text=text)],
    )


def _audio_duration(audio_path: Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        if info.samplerate:
            return max(0.01, float(info.frames) / float(info.samplerate))
    except Exception:
        pass
    return 1.0


def _transcribe_faster(
    audio_path: Path,
    model: str,
    language: Optional[str],
    device: str,
    compute_type: str,
    initial_prompt: Optional[str],
    on_segment: Optional[OnSegmentFn] = None,
) -> Transcript:
    from faster_whisper import WhisperModel

    dev = _resolve_device(device)
    if compute_type == "auto":
        compute_type = "float16" if dev == "cuda" else "int8"

    wm = WhisperModel(model, device=dev, compute_type=compute_type)
    segments_iter, info = wm.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        word_timestamps=False,
        initial_prompt=initial_prompt,
    )
    segments = []
    for s in segments_iter:
        if not (s.text and s.text.strip()):
            continue
        seg = Segment(
            start=float(s.start),
            end=float(s.end),
            text=s.text.strip(),
            confidence=getattr(s, "avg_logprob", None),
        )
        segments.append(seg)
        if on_segment is not None:
            try:
                on_segment(seg)
            except Exception:
                pass
    return Transcript(language=info.language or (language or "unknown"), segments=segments)


def _transcribe_openai(
    audio_path: Path,
    model: str,
    language: Optional[str],
    device: str,
    initial_prompt: Optional[str],
) -> Transcript:
    import whisper

    dev = _resolve_device(device)
    wm = whisper.load_model(model, device=None if dev == "cpu" else dev)
    result = wm.transcribe(
        str(audio_path), language=language, verbose=False, initial_prompt=initial_prompt
    )
    segments = [
        Segment(
            start=float(s["start"]),
            end=float(s["end"]),
            text=s["text"].strip(),
            confidence=s.get("avg_logprob"),
        )
        for s in result.get("segments", [])
        if s.get("text", "").strip()
    ]
    lang = result.get("language", language or "unknown")
    return Transcript(language=lang, segments=segments)


# ----------------------------- subtitles -----------------------------

_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_subtitles(path: Path, language: str = "unknown") -> Transcript:
    """Parse a .vtt or .srt subtitle file into a Transcript.

    Handles the common WebVTT/SRT cue format. Inline tags and cue settings are
    stripped. Duplicate consecutive lines (common in auto-captions) are merged.
    """

    raw = path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", raw)
    segments: List[Segment] = []
    last_text = None
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        ts_line = next((ln for ln in lines if "-->" in ln), None)
        if not ts_line:
            continue
        stamps = _TS.findall(ts_line)
        if len(stamps) < 2:
            continue
        start = _ts_to_sec(*stamps[0])
        end = _ts_to_sec(*stamps[1])
        text_lines = [ln for ln in lines if "-->" not in ln and not ln.isdigit()
                      and not ln.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION"))]
        text = " ".join(text_lines)
        text = re.sub(r"<\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}>", "", text)
        text = re.sub(r"<\d{1,2}:\d{2}[.,]\d{1,3}>", "", text)
        text = re.sub(r"<[^>]+>", "", text)  # strip <c>, timestamps, etc.
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text == last_text:
            continue
        last_text = text
        if end > start:
            segments.append(Segment(start=start, end=end, text=text))
    return Transcript(language=language, segments=segments)


# ----------------------------- shaping -----------------------------


def shape_segments(
    segments: List[Segment],
    min_sec: float,
    max_sec: float,
    merge_gap_sec: float,
    min_confidence: Optional[float] = None,
) -> List[Segment]:
    """Merge tiny adjacent segments and filter unusable ones.

    ``min_confidence`` drops low-quality segments (faster-whisper avg_logprob,
    typically in roughly [-1.0, 0.0]) before shaping.
    """

    if not segments:
        return []

    if min_confidence is not None:
        segments = [
            s for s in segments
            if s.confidence is None or s.confidence >= min_confidence
        ]
        if not segments:
            return []

    merged: List[Segment] = []
    cur = Segment(segments[0].start, segments[0].end, segments[0].text)

    for nxt in segments[1:]:
        gap = nxt.start - cur.end
        combined = nxt.end - cur.start
        if gap <= merge_gap_sec and combined <= max_sec:
            cur = Segment(cur.start, nxt.end, (cur.text + " " + nxt.text).strip())
        elif cur.duration < min_sec and combined <= max_sec:
            cur = Segment(cur.start, nxt.end, (cur.text + " " + nxt.text).strip())
        else:
            merged.append(cur)
            cur = Segment(nxt.start, nxt.end, nxt.text)
    merged.append(cur)

    final: List[Segment] = []
    for seg in merged:
        if not seg.text:
            continue
        if seg.duration < 1.0:
            continue
        if seg.duration < min_sec and len(merged) > 1:
            continue
        final.append(seg)
    return final
