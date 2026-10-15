# chatterbox-multilingual

Chatterbox Multilingual V3 TTS (Resemble AI, FP32) served by a minimal HTTP server on PyTorch
CUDA 12.4, linux/amd64.

- Base image: official `pytorch/pytorch` 2.6.0 CUDA 12.4 runtime, pinned by digest.
- chatterbox-tts 0.1.7 from source commit `5de7a54`, dependencies pinned in `requirements.txt`.
- Weights: `model.json` lists every file of the pinned Hugging Face revision with its size and
  SHA-256 (T3 `t3_mtl23ls_v3`, `s3gen.pt`, `ve.pt`, tokenizer). They are included in the image,
  together with the pkuseg model the tokenizer loads at start; the server runs offline.
- `server.py` listens on `127.0.0.1:8011` only: `GET /health`, `GET /v1/models`,
  `POST /v1/audio/speech` (JSON `model`, `input`, `voice_ref` `{"type": "path"}`, `seed`,
  `language`, default `ru`) returning WAV PCM16 mono 24 kHz. One request at a time; voice
  conditionals are cached per reference file. Access it through an SSH tunnel as user `worker`.
- `WORKER_SSH_PUBLIC_KEY` env: one ED25519 public key installed for `worker`.
- SSH host keys are not part of the image: create them per container with `ssh-keygen -A`
  before starting sshd.
- Output audio carries the upstream Perth watermark applied by chatterbox-tts.

Use an immutable digest, not the `cuda12` tag.

```bash
docker run --rm --gpus all -e WORKER_SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)" \
  ghcr.io/artemko7v/gpu-images/chatterbox-multilingual@sha256:<digest>
```

On hosts that replace the entrypoint (e.g. Vast.ai SSH mode), use an on-start script like:

```bash
ssh-keygen -A; mkdir -p /run/sshd; pgrep -x sshd >/dev/null || /usr/sbin/sshd
python3 /opt/chatterbox/start.py > /home/worker/server.log 2>&1 &
```

The same `server.py` runs on CPU with `--device cpu` given a virtualenv with
`requirements.txt` and the files fetched by `fetch_models.py`.

## Licenses

Chatterbox and Perth: MIT (`licenses/`, `NOTICE`). The image is built on the official PyTorch
image under its own licenses.
