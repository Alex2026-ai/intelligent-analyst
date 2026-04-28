"""
Transparency Log Spine — Binary Merkle tree.

Append-only binary Merkle tree with:
- SHA-256 hash function
- Proof depth cap: 64
- RFC 6962 domain separation (0x00 for leaf, 0x01 for node)
"""

from __future__ import annotations

import hashlib
import threading
from typing import Dict, List, Optional, Tuple


MAX_PROOF_DEPTH = 64


def _hash_leaf(data: bytes) -> bytes:
    """Hash a leaf with domain separation prefix 0x00."""
    return hashlib.sha256(b"\x00" + data).digest()


def _hash_node(left: bytes, right: bytes) -> bytes:
    """Hash an interior node with domain separation prefix 0x01."""
    return hashlib.sha256(b"\x01" + left + right).digest()


class MerkleTree:
    """
    Append-only binary Merkle tree.

    Thread-safe. Supports:
    - append(leaf_hash_hex) -> leaf_index
    - root() -> root_hash_hex
    - inclusion_proof(leaf_index) -> list of (hash, direction) pairs
    - tree_size -> int

    Proof depth is capped at MAX_PROOF_DEPTH (64).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._leaves: List[bytes] = []
        # Cache of computed node hashes for efficiency
        self._levels: List[List[bytes]] = [[]]

    @property
    def tree_size(self) -> int:
        with self._lock:
            return len(self._leaves)

    def append(self, leaf_hash_hex: str) -> int:
        """
        Append a leaf to the tree.

        Args:
            leaf_hash_hex: The leaf hash as a lowercase hex string (64 chars).

        Returns:
            The leaf index (0-based).

        Raises:
            ValueError: If tree would exceed proof depth cap.
        """
        leaf_bytes = bytes.fromhex(leaf_hash_hex)
        hashed = _hash_leaf(leaf_bytes)

        with self._lock:
            if len(self._leaves) >= (2 ** MAX_PROOF_DEPTH):
                raise ValueError(f"Tree size would exceed proof depth cap of {MAX_PROOF_DEPTH}")

            index = len(self._leaves)
            self._leaves.append(hashed)
            self._rebuild_levels()
            return index

    def root(self) -> str:
        """Return the current root hash as a lowercase hex string."""
        with self._lock:
            if not self._leaves:
                return hashlib.sha256(b"").hexdigest()
            return self._compute_root().hex()

    def inclusion_proof(self, leaf_index: int) -> List[Dict[str, str]]:
        """
        Generate an inclusion proof for a leaf.

        Returns:
            List of {"hash": hex, "direction": "left"|"right"} dicts.

        Raises:
            IndexError: If leaf_index is out of range.
        """
        with self._lock:
            n = len(self._leaves)
            if leaf_index < 0 or leaf_index >= n:
                raise IndexError(f"leaf_index {leaf_index} out of range [0, {n})")
            return self._build_proof(leaf_index)

    def _rebuild_levels(self) -> None:
        """Rebuild the level cache after an append."""
        self._levels = [list(self._leaves)]
        current = list(self._leaves)
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    next_level.append(_hash_node(current[i], current[i + 1]))
                else:
                    next_level.append(current[i])
            self._levels.append(next_level)
            current = next_level

    def _compute_root(self) -> bytes:
        """Compute the root from the level cache."""
        if not self._levels:
            return hashlib.sha256(b"").digest()
        return self._levels[-1][0]

    def _build_proof(self, leaf_index: int) -> List[Dict[str, str]]:
        """Build inclusion proof path from leaf to root."""
        proof = []
        idx = leaf_index
        for level in self._levels[:-1]:
            if idx % 2 == 0:
                # We are the left child; sibling is right
                if idx + 1 < len(level):
                    proof.append({
                        "hash": level[idx + 1].hex(),
                        "direction": "right",
                    })
                # else: odd leaf out, no sibling needed
            else:
                # We are the right child; sibling is left
                proof.append({
                    "hash": level[idx - 1].hex(),
                    "direction": "left",
                })
            idx //= 2
        return proof


def verify_inclusion_proof(
    leaf_hash_hex: str,
    leaf_index: int,
    proof: List[Dict[str, str]],
    expected_root_hex: str,
) -> bool:
    """
    Verify an inclusion proof offline.

    Args:
        leaf_hash_hex: The leaf hash (hex).
        leaf_index: The leaf's index in the tree.
        proof: List of {"hash": hex, "direction": "left"|"right"}.
        expected_root_hex: The expected root hash (hex).

    Returns:
        True if the proof validates against the expected root.
    """
    current = _hash_leaf(bytes.fromhex(leaf_hash_hex))

    for step in proof:
        sibling = bytes.fromhex(step["hash"])
        if step["direction"] == "right":
            current = _hash_node(current, sibling)
        else:
            current = _hash_node(sibling, current)

    return current.hex() == expected_root_hex
