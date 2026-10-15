"""Download the Chatterbox files listed in model.json and verify their size and SHA-256.

Usage: python3 fetch_models.py --manifest model.json --model-dir DIR --pkuseg-home DIR
Model files go to DIR at the pinned revision. Files listed in hf_cache_files are placed in
the Hugging Face cache layout inside DIR (the tokenizer resolves them offline), and the
pkuseg model is extracted to PKUSEG_HOME/<model>. Existing verified files are kept.
Exits non-zero on any mismatch.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def fetch(url: str, path: Path, size: int, digest: str) -> None:
    """Download url to path unless a verified copy exists; raise SystemExit on mismatch."""
    if path.is_file() and path.stat().st_size == size and sha256(path) == digest:
        print(f"ok {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    subprocess.run(["curl", "--fail", "--location", "--connect-timeout", "30", "--max-time", "1800",
                    "--retry", "2", "--retry-max-time", "1800", "--speed-limit", "1048576",
                    "--speed-time", "120", "--output", str(partial), url], check=True)
    if partial.stat().st_size != size:
        raise SystemExit(f"{path.name}: size mismatch")
    if sha256(partial) != digest:
        raise SystemExit(f"{path.name}: SHA-256 mismatch")
    partial.replace(path)
    print(f"fetched {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--pkuseg-home", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    base = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/"
    for item in manifest["files"]:
        fetch(base + item["name"], args.model_dir / item["name"], item["size_bytes"], item["sha256"])
    cache = args.model_dir / ("models--" + manifest["repo"].replace("/", "--"))
    for item in manifest["hf_cache_files"]:
        fetch(base + item["name"], cache / "snapshots" / manifest["revision"] / item["name"],
              item["size_bytes"], item["sha256"])
    (cache / "refs").mkdir(parents=True, exist_ok=True)
    (cache / "refs" / "main").write_text(manifest["revision"])
    pkuseg = manifest["pkuseg"]
    archive = args.pkuseg_home / (pkuseg["model"] + ".zip")
    fetch(pkuseg["url"], archive, pkuseg["size_bytes"], pkuseg["sha256"])
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(args.pkuseg_home / pkuseg["model"])
    print(f"pkuseg {pkuseg['model']} ready")


if __name__ == "__main__":
    main()
