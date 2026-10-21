from cacheflow.prefix import group_digest, prefix_blocks, shared_prefix_tokens


def test_block_aligned_shared_prefix_ignores_incomplete_tail():
    a = prefix_blocks(list(range(20)), block_size=4)
    b = prefix_blocks(list(range(12)) + [99, 98, 97, 96], block_size=4)
    assert shared_prefix_tokens(a, b, block_size=4) == 12
    assert group_digest(a, min_shared_tokens=8, block_size=4) == group_digest(b, min_shared_tokens=8, block_size=4)


def test_namespace_and_order_change_digest():
    ids = list(range(8))
    assert prefix_blocks(ids, block_size=4) != prefix_blocks(ids[::-1], block_size=4)
    assert prefix_blocks(ids, block_size=4, namespace="a") != prefix_blocks(ids, block_size=4, namespace="b")
