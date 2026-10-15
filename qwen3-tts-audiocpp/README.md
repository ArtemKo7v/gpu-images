# qwen3-tts-audiocpp

Qwen3-TTS Base voice cloning (GGUF) served by the audio.cpp `audiocpp_server` on CUDA 12.9,
linux/amd64.

- Base image: official audio.cpp `full-cuda12-20261010-715108a`, pinned by digest.
- Models: `model.json` lists every model with its revision, size and SHA-256; all of them
  are included in the image and loaded at start. Currently: `qwen3-tts-0.6b-base` (Q8_0).
- The HTTP server listens on `127.0.0.1:8011` only. Access it through an SSH tunnel as user `worker`.
- `WORKER_SSH_PUBLIC_KEY` env: one ED25519 public key installed for `worker`.
- `GGML_CUDA_DISABLE_GRAPHS=1` is set by default.
- SSH host keys are not part of the image: create them per container with `ssh-keygen -A`
  before starting sshd.

Use an immutable digest, not the `cuda12` tag.

```bash
docker run --rm --gpus all -e WORKER_SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)" \
  ghcr.io/artemko7v/gpu-images/qwen3-tts-audiocpp@sha256:<digest>
```

On hosts that replace the entrypoint (e.g. Vast.ai SSH mode), use an on-start script like:

```bash
ssh-keygen -A; mkdir -p /run/sshd; pgrep -x sshd >/dev/null || /usr/sbin/sshd
python3 /opt/qwen3-tts/start.py > /home/worker/server.log 2>&1 &
```

Request example (through the tunnel):

```bash
curl -o out.wav http://127.0.0.1:8011/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"model": "qwen3-tts-0.6b-base", "input": "Hello.", "language": "English",
       "voice_ref": {"type": "path", "path": "/home/worker/voices/ref.wav"},
       "reference_text": "Transcript of ref.wav.", "seed": 42}'
```

## Licenses

Qwen3-TTS-12Hz-0.6B-Base: Apache License 2.0. audio.cpp: Apache License 2.0. ggml: MIT.
Full texts are in `licenses/` and in the image under `/opt/qwen3-tts/licenses/`.
