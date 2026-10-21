"""Populate the pinned Qwen3-1.7B snapshot expected by serving scripts."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("HF_HOME", "/workspace/.hf_home")

from huggingface_hub import snapshot_download  # noqa: E402

MODEL = "Qwen/Qwen3-1.7B"
REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"

path = Path(snapshot_download(repo_id=MODEL, revision=REVISION))
if path.name != REVISION:
    raise RuntimeError(f"unexpected model revision path: {path}")
print(path)
