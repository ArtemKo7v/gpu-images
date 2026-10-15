"""Install the SSH public key for user worker and start audiocpp_server on localhost."""

import json
import os
from pathlib import Path
import pwd

USER = "worker"


def configure() -> Path:
    """Write authorized_keys from WORKER_SSH_PUBLIC_KEY and the server config; return the config path.

    Every model in model.json is loaded at start. The variable name is deliberately
    specific: hosts such as Vast.ai may set SSH_PUBLIC_KEY themselves.
    """
    home = Path("/home") / USER
    account = pwd.getpwnam(USER)
    public_key = os.environ.get("WORKER_SSH_PUBLIC_KEY", "").strip()
    if public_key:
        if "\n" in public_key or not public_key.startswith("ssh-ed25519 "):
            raise ValueError("Expected one ED25519 public key")
        ssh_dir = home / ".ssh"
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        authorized = ssh_dir / "authorized_keys"
        authorized.write_text(public_key + "\n", encoding="utf-8")
        ssh_dir.chmod(0o700)
        authorized.chmod(0o600)
        if os.geteuid() == 0:
            os.chown(ssh_dir, account.pw_uid, account.pw_gid)
            os.chown(authorized, account.pw_uid, account.pw_gid)
    models = json.loads(Path("/opt/qwen3-tts/model.json").read_text())["models"]
    config = {
        "host": "127.0.0.1", "port": 8011, "backend": "cuda", "device": 0,
        "lazy_load": False, "max_loaded_models": len(models), "busy_timeout_ms": 600000,
        "max_request_body_bytes": 1048576, "log_request_body": False,
        "models": [{"id": model["id"], "family": model["family"], "path": model["path"],
                    "task": "tts", "mode": "offline",
                    "default_request_options": model.get("default_request_options", {})}
                   for model in models],
    }
    path = home / "server.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if os.geteuid() == 0:
        os.chown(path, account.pw_uid, account.pw_gid)
    return path


if __name__ == "__main__":
    config = configure()
    command = ["/opt/qwen3-tts/audiocpp_server", "--config", str(config)]
    if os.geteuid() == 0:
        command = ["runuser", "-u", USER, "--", *command]
    os.execvp(command[0], command)
