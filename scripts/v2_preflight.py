"""Fail before touching serving processes if the pinned V2 stack is incomplete."""
from __future__ import annotations

import json
import hashlib
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
REQUIRED = {
    "vllm": "0.22.0",
    "lmcache": "0.5.3",
    "transformers": "5.6.2",
    "torch": "2.11.0+cu128",
}
RUNTIME = ("httpx", "psutil", "fastapi", "uvicorn", "PyYAML")


def check(model: Path, expected_revision: str = REVISION) -> list[str]:
    errors = []
    for package, expected in REQUIRED.items():
        try:
            actual = version(package)
        except PackageNotFoundError:
            actual = None
        if actual != expected:
            errors.append(f"{package}: expected {expected}, found {actual or 'missing'}")
    for package in RUNTIME:
        try:
            version(package)
        except PackageNotFoundError:
            errors.append(f"{package}: missing")
    if model.name != expected_revision:
        errors.append(f"model revision mismatch: {model.name}")
    for name in ("config.json", "tokenizer.json", "model.safetensors.index.json"):
        if not (model / name).is_file():
            errors.append(f"model file missing: {name}")
    index = model / "model.safetensors.index.json"
    if index.is_file():
        try:
            shards = set(json.loads(index.read_text())["weight_map"].values())
            if not shards:
                errors.append("model index has no weight shards")
            for shard in sorted(shards):
                path = model / shard
                if not path.is_file() or path.stat().st_size == 0:
                    errors.append(f"model shard missing or empty: {shard}")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid model weight index: {type(exc).__name__}")
    return errors


def main() -> int:
    home = Path(os.environ.get("HF_HOME", "/workspace/.hf_home"))
    model = Path(os.environ.get("CACHEFLOW_MODEL_PATH", str(
        home / "hub/models--Qwen--Qwen3-1.7B/snapshots" / REVISION
    )))
    expected_revision = REVISION
    marker = Path(__file__).resolve().parents[1] / '.cacheflow-v3-runtime.json'
    spec = None
    if marker.exists():
        from v3_model import get_model
        spec = get_model(json.loads(marker.read_text()).get('model_key', 'qwen3-1.7b'))
        model = Path(spec['path']); expected_revision = spec['revision']
    errors = check(model, expected_revision)
    if spec and spec['adoption']:
        adoption = marker.parent / spec['adoption']
        if not adoption.is_file():
            errors.append('model adoption record missing; weights must finish SHA verification first')
        else:
            audit = json.loads(adoption.read_text())
            if audit['revision'] != expected_revision or audit['repo'] != spec['repo']:
                errors.append('model adoption identity mismatch')
            index_path = model / 'model.safetensors.index.json'
            if index_path.exists():
                indexed = set(json.loads(index_path.read_text())['weight_map'].values())
                if indexed != {item['file'] for item in audit['weights']}:
                    errors.append('model adoption does not cover exactly the indexed shards')
            for shard in audit['weights']:
                path = model / shard['file']
                if not path.is_file() or path.stat().st_size != shard['size']:
                    errors.append('model shard size mismatch: '+shard['file'])
                elif hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != shard['sha256']:
                    errors.append('model shard SHA mismatch: '+shard['file'])
    if errors:
        print("V2 preflight failed:\n" + "\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"V2 preflight passed: {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
