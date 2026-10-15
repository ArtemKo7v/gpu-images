"""Install the SSH public key for user worker and start the Chatterbox server on localhost."""

import json
import os
from pathlib import Path
import pwd
import sys

USER = "worker"
ROOT = Path("/opt/chatterbox")


def configure() -> None:
    """Write authorized_keys from WORKER_SSH_PUBLIC_KEY.

    The variable name is deliberately specific: hosts such as Vast.ai may set SSH_PUBLIC_KEY themselves.
    """
    home = Path("/home") / USER
    account = pwd.getpwnam(USER)
    public_key = os.environ.get("WORKER_SSH_PUBLIC_KEY", "").strip()
    if not public_key:
        return
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


# Image ENV repeated here: on-start scripts of some hosts do not inherit it.
ENVIRONMENT = {"PKUSEG_HOME": str(ROOT / "pkuseg"), "HF_HUB_OFFLINE": "1",
               "TRANSFORMERS_OFFLINE": "1", "TQDM_DISABLE": "1", "HOME": f"/home/{USER}",
               "XDG_CACHE_HOME": f"/home/{USER}/.cache",
               "NUMBA_CACHE_DIR": f"/home/{USER}/.cache/numba"}


if __name__ == "__main__":
    configure()
    os.environ.update(ENVIRONMENT)
    model = json.loads((ROOT / "model.json").read_text())
    command = [sys.executable, str(ROOT / "server.py"), "--host", "127.0.0.1", "--port", "8011",
               "--model-dir", str(ROOT / "models"), "--model-id", model["id"],
               "--t3-model", model["t3_model"], "--device", "cuda"]
    if os.geteuid() == 0:
        command = ["runuser", "-u", USER, "--", *command]
    os.execvp(command[0], command)
