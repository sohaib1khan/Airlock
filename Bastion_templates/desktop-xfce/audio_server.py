#!/usr/bin/env python3
"""Streams PulseAudio monitor as WebM/Opus over HTTP for Airlock browser audio.

Run as kuser with XDG_RUNTIME_DIR and PULSE_SERVER set so ffmpeg can reach
the per-session PulseAudio daemon via its Unix socket.
"""

import http.server
import socketserver
import subprocess

PORT = 8765
SINK_MONITOR = "airlock_sink.monitor"


class AudioHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "audio/webm;codecs=opus")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        proc = subprocess.Popen(
            [
                "ffmpeg",
                "-nostdin",
                "-f", "pulse",
                "-i", SINK_MONITOR,
                "-c:a", "libopus",
                "-b:a", "96k",
                "-vn",
                "-f", "webm",
                "-cluster_size_limit", "131072",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception:
            pass
        finally:
            proc.terminate()
            proc.wait()

    def log_message(self, *_):
        pass


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), AudioHandler) as srv:
    srv.serve_forever()
