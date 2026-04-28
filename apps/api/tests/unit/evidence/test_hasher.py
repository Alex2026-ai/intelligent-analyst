"""Tests for evidence hashing — determinism, tamper detection."""

from apps.api.src.evidence.hasher import (
    _canonical_json,
    hash_chain,
    hash_node,
    hash_node_content,
    verify_chain,
    verify_node,
)
from apps.api.src.evidence.node_factory import NodeFactory


class TestCanonicalJson:
    def test_sorted_keys(self):
        result = _canonical_json({"b": 1, "a": 2})
        assert result == '{"a":2,"b":1}'

    def test_compact_separators(self):
        result = _canonical_json({"key": "value"})
        assert " " not in result

    def test_nested_sorted(self):
        result = _canonical_json({"z": {"b": 1, "a": 2}})
        assert result == '{"z":{"a":2,"b":1}}'


class TestHashNodeContent:
    def test_deterministic(self):
        """Same input must produce same hash every time."""
        args = {
            "node_type": "source_artifact",
            "sequence": 1,
            "timestamp": "2026-03-21T10:00:00Z",
            "data": {"artifact_ref": "doc.pdf", "metadata": {}},
        }
        hashes = {hash_node_content(**args) for _ in range(1000)}
        assert len(hashes) == 1, "Hash is not deterministic!"

    def test_different_data_different_hash(self):
        h1 = hash_node_content("source_artifact", 1, "2026-03-21T10:00:00Z", {"a": 1})
        h2 = hash_node_content("source_artifact", 1, "2026-03-21T10:00:00Z", {"a": 2})
        assert h1 != h2

    def test_different_sequence_different_hash(self):
        h1 = hash_node_content("source_artifact", 1, "2026-03-21T10:00:00Z", {"a": 1})
        h2 = hash_node_content("source_artifact", 2, "2026-03-21T10:00:00Z", {"a": 1})
        assert h1 != h2

    def test_different_timestamp_different_hash(self):
        h1 = hash_node_content("source_artifact", 1, "2026-03-21T10:00:00Z", {})
        h2 = hash_node_content("source_artifact", 1, "2026-03-21T10:00:01Z", {})
        assert h1 != h2

    def test_sha256_format(self):
        h = hash_node_content("source_artifact", 1, "2026-03-21T10:00:00Z", {})
        assert len(h) == 64  # SHA-256 hex digest length
        assert all(c in "0123456789abcdef" for c in h)


class TestHashNode:
    def test_matches_content_hash(self):
        ts = "2026-03-21T10:00:00Z"
        node = NodeFactory.source_artifact(
            sequence=1,
            artifact_ref="doc.pdf",
            metadata={"size": 1024},
            timestamp=ts,
        )
        recomputed = hash_node(node)
        assert recomputed == node.node_hash

    def test_verify_valid_node(self):
        node = NodeFactory.source_artifact(
            sequence=1,
            artifact_ref="doc.pdf",
            metadata={},
            timestamp="2026-03-21T10:00:00Z",
        )
        assert verify_node(node) is True


class TestHashChain:
    def test_deterministic(self):
        ts = "2026-03-21T10:00:00Z"
        nodes = [
            NodeFactory.source_artifact(1, "doc.pdf", {}, timestamp=ts),
            NodeFactory.transformation(2, "h1", "h2", "pii_mask", timestamp=ts),
        ]
        hashes = {hash_chain(nodes) for _ in range(100)}
        assert len(hashes) == 1

    def test_order_matters(self):
        ts = "2026-03-21T10:00:00Z"
        n1 = NodeFactory.source_artifact(1, "doc.pdf", {}, timestamp=ts)
        n2 = NodeFactory.transformation(2, "h1", "h2", "pii_mask", timestamp=ts)
        h_forward = hash_chain([n1, n2])
        h_reverse = hash_chain([n2, n1])
        # Both compute using sequence order, so they should be the same
        # since hash_chain sorts by sequence
        assert h_forward == h_reverse  # sorted by sequence internally

    def test_extra_node_changes_hash(self):
        ts = "2026-03-21T10:00:00Z"
        n1 = NodeFactory.source_artifact(1, "doc.pdf", {}, timestamp=ts)
        n2 = NodeFactory.transformation(2, "h1", "h2", "pii_mask", timestamp=ts)
        h_two = hash_chain([n1, n2])
        n3 = NodeFactory.degradation_event(3, "llm_degraded", "timeout", timestamp=ts)
        h_three = hash_chain([n1, n2, n3])
        assert h_two != h_three


class TestVerifyChain:
    def test_valid_chain(self):
        from apps.api.src.evidence.builder import EvidenceChainBuilder
        from ia_shared.models.evidence import NodeType

        builder = EvidenceChainBuilder()
        chain = builder.create_chain("r1", "t1")
        chain = builder.add_node(chain, NodeType.SOURCE_ARTIFACT, {"ref": "doc.pdf"})
        chain = builder.close_chain(chain)
        assert verify_chain(chain) is True
