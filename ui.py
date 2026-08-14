#!/usr/bin/env python3
"""Launch the local web UI: `python ui.py` (then open the printed URL)."""
import argparse

from voice_dataset_builder.webui import serve

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Voice Dataset Builder web UI")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    serve(host=a.host, port=a.port, open_browser=not a.no_browser)
