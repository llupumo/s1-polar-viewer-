#!/usr/bin/env python3
"""Serve site/ on http://localhost:8000 with caching disabled (so edits always show up).
   python serve.py [port]"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
site = Path(__file__).parent / "site"
print(f"Serving {site} at http://localhost:{port}  (Ctrl+C to stop)")
ThreadingHTTPServer(("", port), partial(NoCache, directory=str(site))).serve_forever()
