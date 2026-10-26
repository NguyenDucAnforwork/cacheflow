"""Verify segmented Qwen shards and adopt them into the pinned Hub snapshot."""
from __future__ import annotations

import argparse
import hashlib
import os
import signal
import time
from pathlib import Path

REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
FILES = {
    "model-00001-of-00002.safetensors": (3441185608, "169ad53ec313c3a34b06c0809216e4fc072cce444a5d4ff2b59690d064130ed5"),
    "model-00002-of-00002.safetensors": (622329984, "912becff8d60672aa8628ef08c05898d9adf17c2ad4ae3caf99b065622fdeff9"),
}
HOME = Path("/workspace/.hf_home")
REPO = HOME / "hub/models--Qwen--Qwen3-1.7B"
STAGE = HOME / "aria_probe"


def running(pid: int) -> bool:
    proc = Path(f"/proc/{pid}/stat")
    if not proc.exists():
        return False
    return proc.read_text().split()[2] != "Z"


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aria-pids", nargs=2, type=int, required=True)
    parser.add_argument("--old-downloader-pid", type=int, required=True)
    args = parser.parse_args()
    print(f"waiting for aria2 PIDs {args.aria_pids}", flush=True)
    deadline = time.monotonic() + 3 * 3600
    while any(running(pid) for pid in args.aria_pids):
        if time.monotonic() > deadline:
            raise SystemExit("segmented downloads did not finish within 3 hours")
        time.sleep(30)
    snapshot = REPO / "snapshots" / REVISION
    for name, (size, expected_sha) in FILES.items():
        source = STAGE / name
        if source.with_name(source.name + ".aria2").exists():
            raise SystemExit(f"aria2 control file remains: {name}")
        if not source.is_file() or source.stat().st_size != size:
            raise SystemExit(f"size mismatch: {name}")
        actual_sha = digest(source)
        if actual_sha != expected_sha:
            raise SystemExit(f"SHA256 mismatch: {name}: {actual_sha}")
        print(f"verified {name}: {size} bytes, SHA256 {actual_sha}", flush=True)
    for name, (_, sha) in FILES.items():
        blob = REPO / "blobs" / sha
        source = STAGE / name
        if blob.exists():
            if digest(blob) != sha:
                raise SystemExit(f"existing cache blob differs: {name}")
            source.unlink()
        else:
            os.replace(source, blob)
        target = snapshot / name
        if target.is_symlink() or target.exists():
            if target.resolve() != blob:
                raise SystemExit(f"snapshot target differs: {name}")
        else:
            target.symlink_to(os.path.relpath(blob, snapshot))
        print(f"adopted {name} into pinned snapshot", flush=True)
    if running(args.old_downloader_pid):
        os.kill(args.old_downloader_pid, signal.SIGTERM)
        print(f"stopped redundant HTTP downloader PID {args.old_downloader_pid}", flush=True)
    print("pinned model snapshot ready", flush=True)


if __name__ == "__main__":
    main()
