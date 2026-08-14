"""Named presets that prefill the UI form for common dataset recipes."""

# Each preset is a partial set of form field values. The UI merges them onto
# the current form. Keep keys aligned with webui_page.py field ids.
PRESETS = {
    "Vietnamese Voice": {
        "language": "vi",
        "whisper_model": "large-v3",
        "initial_prompt": "Xin chào, đây là bản ghi âm tiếng Việt có dấu đầy đủ.",
        "remove_silence": True,
        "loudnorm": True,
        "loudnorm_lufs": -23,
        "min_clip": 3,
        "max_clip": 12,
        "output_formats": "universal",
    },
    "English Podcast": {
        "language": "en",
        "whisper_model": "small",
        "remove_silence": True,
        "loudnorm": True,
        "loudnorm_lufs": -16,
        "min_clip": 4,
        "max_clip": 12,
        "output_formats": "universal",
    },
    "Audiobook": {
        "language": "",
        "whisper_model": "medium",
        "remove_silence": True,
        "loudnorm": True,
        "loudnorm_lufs": -20,
        "min_clip": 5,
        "max_clip": 14,
        "output_formats": "jsonl",
    },
    "MOSS Optimized": {
        "whisper_model": "large-v3",
        "sample_rate": 24000,
        "remove_silence": True,
        "loudnorm": True,
        "loudnorm_lufs": -23,
        "min_clip": 3,
        "max_clip": 20,
        "output_formats": "jsonl",
    },
    "XTTS Ready": {
        "whisper_model": "medium",
        "sample_rate": 22050,
        "remove_silence": True,
        "loudnorm": True,
        "loudnorm_lufs": -23,
        "min_clip": 3,
        "max_clip": 11,
        "output_formats": "ljspeech",
        "make_references": True,
    },
}
