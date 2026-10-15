"""Minimal HTTP server for Chatterbox Multilingual TTS: one loaded model, one request at a time.

Endpoints (a subset of the audio.cpp server API):
  GET  /health            -> {"status": "ok", "backend": <device>, "models": 1}
  GET  /v1/models         -> {"object": "list", "data": [{"id": <model id>, "loaded": bool}]}
  POST /v1/audio/speech   -> audio/wav (PCM16 mono, model sample rate)
       JSON: {"model", "input", "voice_ref": {"type": "path", "path"}, "seed", "language"}
Errors are JSON {"error": {"message", "type"}}. The model loads in the background after the
port opens; /v1/models reports "loaded": true when it is ready. Voice conditionals are
cached per reference file. Request bodies are never logged.
"""

import argparse
from collections import OrderedDict
import io
import json
import logging
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY_BYTES = 1 << 20
MAX_INPUT_CHARS = 2000
logger = logging.getLogger("chatterbox-server")


class RequestError(Exception):
    """Client error reported as HTTP status with an error type."""

    def __init__(self, status: int, kind: str, message: str) -> None:
        super().__init__(message)
        self.status, self.kind, self.message = status, kind, message


class ChatterboxEngine:
    """Loads ChatterboxMultilingualTTS once and synthesizes one sentence per call.

    synthesize() is serialized by a lock; voice conditionals are cached by
    (path, size, mtime) for the last cache_size voices.
    """

    def __init__(self, model_dir: Path, device: str, t3_model: str, threads: int,
                 exaggeration: float = 0.5, cache_size: int = 4) -> None:
        self.model_dir, self.device, self.t3_model = model_dir, device, t3_model
        self.threads, self.exaggeration, self.cache_size = threads, exaggeration, cache_size
        self.model = None
        self.error: str | None = None
        self.sample_rate = 0
        self._lock = threading.Lock()
        self._conditionals: OrderedDict = OrderedDict()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        """Import torch/chatterbox and load the model; failures are kept in self.error."""
        try:
            import torch
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            if self.device == "cpu":
                torch.set_num_threads(self.threads)
            started = time.monotonic()
            model = ChatterboxMultilingualTTS.from_local(self.model_dir, device=self.device,
                                                         t3_model=self.t3_model)
            self.sample_rate = model.sr
            self.model = model
            logger.info("model loaded on %s in %.1f s", self.device, time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001 - reported by /health and request errors
            self.error = f"{type(exc).__name__}: {exc}"
            logger.exception("model load failed")

    def synthesize(self, text: str, voice_path: str, seed: int, language: str) -> bytes:
        """Return WAV bytes for one sentence; RequestError for bad input, RuntimeError otherwise."""
        import soundfile
        import torch

        path = Path(voice_path)
        if not path.is_file():
            raise RequestError(400, "invalid_request_error", f"voice_ref not found: {voice_path}")
        with self._lock:
            stat = path.stat()
            key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
            if key in self._conditionals:
                self._conditionals.move_to_end(key)
                self.model.conds = self._conditionals[key]
            else:
                self.model.prepare_conditionals(str(path), exaggeration=self.exaggeration)
                self._conditionals[key] = self.model.conds
                while len(self._conditionals) > self.cache_size:
                    self._conditionals.popitem(last=False)
            torch.manual_seed(seed)
            if self.device.startswith("cuda"):
                torch.cuda.manual_seed_all(seed)
            try:
                with torch.inference_mode():
                    wav = self.model.generate(text, language_id=language)
            except (ValueError, AssertionError) as exc:
                raise RequestError(400, "invalid_request_error", str(exc)) from exc
            samples = wav.squeeze().detach().cpu().numpy()
        buffer = io.BytesIO()
        soundfile.write(buffer, samples, self.sample_rate, format="WAV", subtype="PCM_16")
        return buffer.getvalue()


def make_handler(engine, model_id: str):
    """HTTP handler class bound to an engine object with loaded/error/synthesize()."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "chatterbox-server"

        def log_message(self, *args) -> None:
            pass

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, kind: str, message: str) -> None:
            self._json(status, {"error": {"message": message, "type": kind}})

        def do_GET(self) -> None:
            if self.path == "/health":
                status = "error" if engine.error else "ok"
                self._json(200, {"status": status, "backend": engine.device, "models": 1,
                                 **({"error": engine.error} if engine.error else {})})
            elif self.path == "/v1/models":
                self._json(200, {"object": "list",
                                 "data": [{"id": model_id, "loaded": engine.loaded}]})
            else:
                self._error(404, "not_found", "unknown path")

        def do_POST(self) -> None:
            if self.path != "/v1/audio/speech":
                self._error(404, "not_found", "unknown path")
                return
            started = time.monotonic()
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY_BYTES:
                    raise RequestError(413, "invalid_request_error", "request body too large")
                try:
                    request = json.loads(self.rfile.read(length))
                except ValueError as exc:
                    raise RequestError(400, "invalid_request_error", "body is not JSON") from exc
                if request.get("model") != model_id:
                    raise RequestError(400, "invalid_request_error", f"unknown model {request.get('model')!r}")
                text = str(request.get("input") or "").strip()
                if not text or len(text) > MAX_INPUT_CHARS:
                    raise RequestError(400, "invalid_request_error",
                                       f"input must be 1..{MAX_INPUT_CHARS} characters")
                ref = request.get("voice_ref") or {}
                if ref.get("type") != "path" or not ref.get("path"):
                    raise RequestError(400, "invalid_request_error", "voice_ref must be {type: path, path}")
                seed = request.get("seed", 0)
                if type(seed) is not int or seed < 0:
                    raise RequestError(400, "invalid_request_error", "seed must be a non-negative integer")
                if not engine.loaded:
                    raise RequestError(503, "server_busy", engine.error or "model is loading")
                audio = engine.synthesize(text, ref["path"], seed, str(request.get("language") or "ru"))
            except RequestError as exc:
                self._error(exc.status, exc.kind, exc.message)
                return
            except Exception as exc:  # noqa: BLE001 - reported to the client, process keeps serving
                logger.exception("synthesis failed")
                self._error(500, "server_error", f"{type(exc).__name__}: {exc}")
                return
            logger.info("speech: %d chars, %d bytes, %.2f s", len(text), len(audio),
                        time.monotonic() - started)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-id", default="chatterbox-multilingual-v3")
    parser.add_argument("--t3-model", default="v3")
    parser.add_argument("--device", default="auto", help="cpu, cuda or auto")
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 1, help="CPU threads")
    args = parser.parse_args()
    os.environ.setdefault("TQDM_DISABLE", "1")  # no per-token progress bars in service logs
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Stress marks come with the input text; the optional upstream Russian stresser is not
    # installed on purpose, and its per-request warning would flood the log.
    for handler in logging.getLogger().handlers:
        handler.addFilter(lambda record: "russian_text_stresser" not in record.getMessage())
    device = args.device
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    engine = ChatterboxEngine(args.model_dir, device, args.t3_model, args.threads)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(engine, args.model_id))
    threading.Thread(target=engine.load, name="load", daemon=True).start()
    logger.info("listening on %s:%d, model %s", args.host, args.port, args.model_id)
    server.serve_forever()


if __name__ == "__main__":
    main()
