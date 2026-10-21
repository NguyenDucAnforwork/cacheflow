"""Token-aligned prefix fingerprints; raw prompts never enter scheduler logs."""

from __future__ import annotations

from hashlib import blake2b
from struct import pack
from typing import Sequence


def prefix_blocks(token_ids: Sequence[int], *, block_size: int = 256, namespace: str = "") -> tuple[str, ...]:
    """Return cumulative digests at complete block boundaries.

    Cumulative hashes encode both block content and order. A shared digest at
    position N proves identical token IDs for all N full blocks (barring a
    cryptographic collision). Incomplete suffixes are deliberately ignored.
    """
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    digest = blake2b(digest_size=16, person=b"CacheFlow-prefix")
    digest.update(namespace.encode("utf-8"))
    result: list[str] = []
    for i, token_id in enumerate(token_ids, start=1):
        if not 0 <= int(token_id) < 2**32:
            raise ValueError("token IDs must fit uint32")
        digest.update(pack("<I", int(token_id)))
        if i % block_size == 0:
            result.append(digest.hexdigest())
    return tuple(result)


def shared_prefix_tokens(a: Sequence[str], b: Sequence[str], *, block_size: int = 256) -> int:
    blocks = 0
    for x, y in zip(a, b):
        if x != y:
            break
        blocks += 1
    return blocks * block_size


def group_digest(blocks: Sequence[str], *, min_shared_tokens: int, block_size: int = 256) -> str | None:
    required = (min_shared_tokens + block_size - 1) // block_size
    if required == 0 or len(blocks) < required:
        return None
    return blocks[required - 1]
