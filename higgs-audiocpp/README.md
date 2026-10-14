# higgs-audiocpp

Higgs Audio v3 TTS (Q8_0 GGUF) served by the audio.cpp `audiocpp_server` on CUDA 12.9, linux/amd64.

- Base image: official audio.cpp `full-cuda12-20261010-715108a`, pinned by digest.
- Model revision, size and SHA-256: `model.json`. Weights are included in the image.
- The HTTP server listens on `127.0.0.1:8011` only. Access it through an SSH tunnel as user `worker`.
- `SSH_PUBLIC_KEY` env: one ED25519 public key installed for `worker`.
- `GGML_CUDA_DISABLE_GRAPHS=1` is set by default.
- SSH host keys are not part of the image: create them per container with `ssh-keygen -A`
  before starting sshd.

Use an immutable digest, not the `cuda12` tag.

```bash
docker run --rm --gpus all -e SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)" \
  ghcr.io/artemko7v/gpu-images/higgs-audiocpp@sha256:<digest>
```

On hosts that replace the entrypoint (e.g. Vast.ai SSH mode), run
`python3 /opt/higgs/start.py` from the on-start script.

## Licenses

Built with Higgs TTS 3 licensed from Boson AI USA, Inc. — Boson Higgs TTS 3 Research and
Non-Commercial License. audio.cpp: Apache License 2.0. ggml: MIT.
Full texts are in `licenses/` and in the image under `/opt/higgs/licenses/`.
