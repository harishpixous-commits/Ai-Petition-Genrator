import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1] / "app")


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/officer/"):
            self.path = "/static/officer.html"
        elif self.path == "/":
            self.path = "/static/index.html"
        super().do_GET()


ThreadingHTTPServer(("127.0.0.1", 8020), Handler).serve_forever()
