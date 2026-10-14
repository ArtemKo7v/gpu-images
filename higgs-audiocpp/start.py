"""Install the SSH public key for user worker and start audiocpp_server on localhost."""

import json
import os
from pathlib import Path
import pwd

USER = "worker"


def configure() -> Path:
    """Write authorized_keys from SSH_PUBLIC_KEY and the server config; return the config path."""
    home = Path("/home") / USER
    account = pwd.getpwnam(USER)
    public_key = os.environ.get("SSH_PUBLIC_KEY", "").strip()
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
    model = json.loads(Path("/opt/higgs/model.json").read_text())
    config = {
        "host": "127.0.0.1", "port": 8011, "backend": "cuda", "device": 0,
        "lazy_load": False, "max_loaded_models": 1, "busy_timeout_ms": 600000,
        "max_request_body_bytes": 1048576, "log_request_body": False,
        "models": [{"id": model["id"], "family": model["family"],
                    "path": model["path"], "task": "tts", "mode": "offline"}],
    }
    path = home / "higgs-server.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if os.geteuid() == 0:
        os.chown(path, account.pw_uid, account.pw_gid)
    return path


if __name__ == "__main__":
    config = configure()
    command = ["/opt/higgs/audiocpp_server", "--config", str(config)]
    if os.geteuid() == 0:
        command = ["runuser", "-u", USER, "--", *command]
    os.execvp(command[0], command)
