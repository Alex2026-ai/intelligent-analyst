"""Tests for evidence node factory — all node types, required fields."""

from apps.api.src.evidence.hasher import verify_node
from apps.api.src.evidence.node_factory import NodeFactory
from ia_shared.models.evidence import NodeType


TS = "2026-03-21T10:00:00Z"


class TestSourceArtifact:
    def test_creates_valid_node(self):
        node = NodeFactory.source_artifact(1, "doc.pdf", {"size": 1024}, timestamp=TS)
        assert node.node_type == NodeType.SOURCE_ARTIFACT
        assert node.sequence == 1
        assert node.data["artifact_ref"] == "doc.pdf"
        assert verify_node(node) is True


class TestRetrievalResult:
    def test_creates_valid_node(self):
        node = NodeFactory.retrieval_result(
            2, "search query", [{"id": "p1", "score": 0.9}], 0.9, timestamp=TS
        )
        assert node.node_type == NodeType.RETRIEVAL_RESULT
        assert node.data["match_score"] == 0.9
        assert verify_node(node) is True


class TestTransformation:
    def test_creates_valid_node(self):
        node = NodeFactory.transformation(3, "hash_in", "hash_out", "pii_mask", timestamp=TS)
        assert node.node_type == NodeType.TRANSFORMATION
        assert node.data["transform_type"] == "pii_mask"
        assert verify_node(node) is True


class TestModelCall:
    def test_creates_valid_node(self):
        node = NodeFactory.model_call(
            4, "v1.0", "anthropic", "claude-haiku", 0.85, 250, "Summary text", timestamp=TS
        )
        assert node.node_type == NodeType.MODEL_CALL
        assert node.data["provider"] == "anthropic"
        assert node.data["latency_ms"] == 250
        assert verify_node(node) is True


class TestHumanDecision:
    def test_creates_valid_node(self):
        node = NodeFactory.human_decision(
            5, "approve", "user-42", "Looks correct.", ["n1", "n2"], timestamp=TS
        )
        assert node.node_type == NodeType.HUMAN_DECISION
        assert node.data["decision"] == "approve"
        assert node.data["reviewer_id"] == "user-42"
        assert verify_node(node) is True


class TestExportArtifact:
    def test_creates_valid_node(self):
        node = NodeFactory.export_artifact(6, "gs://bucket/file.pdf", "pdf", "abc123", timestamp=TS)
        assert node.node_type == NodeType.EXPORT_ARTIFACT
        assert node.data["format"] == "pdf"
        assert verify_node(node) is True


class TestDegradationEvent:
    def test_creates_valid_node(self):
        node = NodeFactory.degradation_event(7, "llm_degraded", "Provider A timeout", timestamp=TS)
        assert node.node_type == NodeType.DEGRADATION_EVENT
        assert node.data["reason"] == "Provider A timeout"
        assert verify_node(node) is True


class TestAllNodeTypes:
    def test_every_node_type_has_factory(self):
        """Every NodeType in the registry must have a factory method."""
        factory_methods = {
            NodeType.SOURCE_ARTIFACT: NodeFactory.source_artifact,
            NodeType.RETRIEVAL_RESULT: NodeFactory.retrieval_result,
            NodeType.TRANSFORMATION: NodeFactory.transformation,
            NodeType.MODEL_CALL: NodeFactory.model_call,
            NodeType.HUMAN_DECISION: NodeFactory.human_decision,
            NodeType.EXPORT_ARTIFACT: NodeFactory.export_artifact,
            NodeType.DEGRADATION_EVENT: NodeFactory.degradation_event,
        }
        assert set(factory_methods.keys()) == set(NodeType)

    def test_all_nodes_have_valid_hashes(self):
        nodes = [
            NodeFactory.source_artifact(1, "ref", {}, timestamp=TS),
            NodeFactory.retrieval_result(2, "q", [], 0.5, timestamp=TS),
            NodeFactory.transformation(3, "h1", "h2", "t", timestamp=TS),
            NodeFactory.model_call(4, "v1", "p", "m", 0.8, 100, "s", timestamp=TS),
            NodeFactory.human_decision(5, "approve", "u", "n", [], timestamp=TS),
            NodeFactory.export_artifact(6, "ref", "pdf", "h", timestamp=TS),
            NodeFactory.degradation_event(7, "mode", "reason", timestamp=TS),
        ]
        for node in nodes:
            assert verify_node(node) is True, f"Hash invalid for {node.node_type}"

    def test_auto_timestamp_all_types(self):
        """All factory methods work without explicit timestamp."""
        nodes = [
            NodeFactory.source_artifact(1, "ref", {}),
            NodeFactory.retrieval_result(2, "q", [], 0.5),
            NodeFactory.transformation(3, "h1", "h2", "t"),
            NodeFactory.model_call(4, "v1", "p", "m", 0.8, 100, "s"),
            NodeFactory.human_decision(5, "approve", "u", "n", []),
            NodeFactory.export_artifact(6, "ref", "pdf", "h"),
            NodeFactory.degradation_event(7, "mode", "reason"),
        ]
        for node in nodes:
            assert verify_node(node) is True
            assert node.timestamp  # Has auto-generated timestamp
