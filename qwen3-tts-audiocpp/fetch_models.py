"""Download every model in model.json at build time and verify its size and SHA-256."""

import hashlib
import json
from pathlib import Path
import subprocess

for model in json.loads(Path("/opt/qwen3-tts/model.json").read_text())["models"]:
    path = Path(model["path"])
    subprocess.run(["curl", "--fail", "--location", "--connect-timeout", "30", "--max-time", "900",
                    "--retry", "2", "--retry-max-time", "1200", "--speed-limit", "1048576",
                    "--speed-time", "120", "--output", str(path), model["url"]], check=True)
    if path.stat().st_size != model["size_bytes"]:
        raise SystemExit(f"{path.name}: size mismatch")
    with path.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != model["sha256"]:
            raise SystemExit(f"{path.name}: SHA-256 mismatch")
