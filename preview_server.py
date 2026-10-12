"""Serve the project locally with byte ranges for video seeking."""

import argparse
import os
from pathlib import Path
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class PreviewHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if os.path.isfile(self.translate_path(self.path)):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        self.bytes_remaining = None
        path = self.translate_path(self.path)
        range_header = self.headers.get("Range", "")
        # Multiple ranges and If-Range requests may fall back to a full response.
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if (
            not match
            or not any(match.groups())
            or self.headers.get("If-Range")
            or not os.path.isfile(path)
        ):
            return super().send_head()

        try:
            file = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            stat = os.fstat(file.fileno())
            size = stat.st_size
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                start = max(0, size - int(last))
                end = size - 1

            if start >= size or end < start:
                file.close()
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None

            file.seek(start)
            self.bytes_remaining = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(self.bytes_remaining))
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            return file
        except Exception:
            file.close()
            raise

    def copyfile(self, source, outputfile):
        try:
            if self.bytes_remaining is None:
                return super().copyfile(source, outputfile)
            remaining = self.bytes_remaining
            while remaining:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers cancel an active transfer when the viewer seeks again.
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    root = str(Path(__file__).resolve().parent)

    def handler(*arguments, **keywords):
        return PreviewHandler(*arguments, directory=root, **keywords)

    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f"Local preview: http://{args.bind}:{args.port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
