"""Tests for evidence chain and node models."""

import pytest
from pydantic import ValidationError

from ia_shared.models.evidence import (
    ChainStatus,
    EvidenceChain,
    EvidenceNode,
    EvidenceQueryParams,
    NodeType,
)
from ia_shared.constants import MAX_PAGE_SIZE


class TestNodeType:
    def test_all_values(self):
        expected = {
            "source_artifact",
            "retrieval_result",
            "transformation",
            "model_call",
            "human_decision",
            "export_artifact",
            "degradation_event",
        }
        assert {nt.value for nt in NodeType} == expected

    def test_exhaustive(self):
        """No catch-all 'other' value exists."""
        assert len(NodeType) == 7


class TestChainStatus:
    def test_all_values(self):
        assert set(ChainStatus) == {
            ChainStatus.BUILDING,
            ChainStatus.COMPLETE,
            ChainStatus.INTEGRITY_WARNING,
        }


class TestEvidenceNode:
    def test_valid(self):
        node = EvidenceNode(
            node_id="550e8400-e29b-41d4-a716-446655440000",
            node_type=NodeType.SOURCE_ARTIFACT,
            sequence=1,
            timestamp="2026-03-21T10:00:00Z",
            node_hash="abc123def456",
            data={"filename": "document.pdf", "size_bytes": 1024},
        )
        assert node.node_type == NodeType.SOURCE_ARTIFACT
        assert node.data["filename"] == "document.pdf"

    def test_sequence_must_be_positive(self):
        with pytest.raises(ValidationError):
            EvidenceNode(
                node_id="550e8400-e29b-41d4-a716-446655440000",
                node_type=NodeType.SOURCE_ARTIFACT,
                sequence=0,
                timestamp="2026-03-21T10:00:00Z",
                node_hash="abc123",
            )

    def test_empty_data_allowed(self):
        node = EvidenceNode(
            node_id="550e8400-e29b-41d4-a716-446655440000",
            node_type=NodeType.DEGRADATION_EVENT,
            sequence=1,
            timestamp="2026-03-21T10:00:00Z",
            node_hash="abc123",
        )
        assert node.data == {}


class TestEvidenceChain:
    def test_valid_complete_chain(self):
        chain = EvidenceChain(
            chain_id="550e8400-e29b-41d4-a716-446655440000",
            resolution_id="660e8400-e29b-41d4-a716-446655440000",
            tenant_id="tenant-001",
            status=ChainStatus.COMPLETE,
            chain_hash="sha256hashvalue",
            nodes=[
                EvidenceNode(
                    node_id="n1",
                    node_type=NodeType.SOURCE_ARTIFACT,
                    sequence=1,
                    timestamp="2026-03-21T10:00:00Z",
                    node_hash="h1",
                ),
                EvidenceNode(
                    node_id="n2",
                    node_type=NodeType.MODEL_CALL,
                    sequence=2,
                    timestamp="2026-03-21T10:00:01Z",
                    node_hash="h2",
                ),
            ],
            created_at="2026-03-21T10:00:00Z",
            updated_at="2026-03-21T10:00:01Z",
        )
        assert len(chain.nodes) == 2
        assert chain.status == ChainStatus.COMPLETE
        assert chain.next_cursor is None

    def test_with_pagination(self):
        chain = EvidenceChain(
            chain_id="c1",
            resolution_id="r1",
            tenant_id="t1",
            status=ChainStatus.BUILDING,
            chain_hash="hash",
            nodes=[],
            next_cursor="page2token",
            created_at="2026-03-21T10:00:00Z",
            updated_at="2026-03-21T10:00:00Z",
        )
        assert chain.next_cursor == "page2token"

    def test_has_tenant_id(self):
        """Evidence chains are storage models — tenant_id required (INV-005)."""
        assert "tenant_id" in EvidenceChain.model_fields


class TestEvidenceQueryParams:
    def test_defaults(self):
        params = EvidenceQueryParams()
        assert params.cursor is None
        assert params.page_size == 50

    def test_page_size_bounds(self):
        with pytest.raises(ValidationError):
            EvidenceQueryParams(page_size=0)
        with pytest.raises(ValidationError):
            EvidenceQueryParams(page_size=MAX_PAGE_SIZE + 1)
