"""Tests for evidence exceptions."""

from apps.api.src.evidence.exceptions import (
    ChainClosedError,
    ChainNotFoundError,
    EvidenceIntegrityError,
)


class TestEvidenceIntegrityError:
    def test_fields(self):
        err = EvidenceIntegrityError(
            "Hash mismatch", chain_id="c1", node_id="n1",
            expected_hash="abc", actual_hash="xyz",
        )
        assert err.chain_id == "c1"
        assert err.node_id == "n1"
        assert err.expected_hash == "abc"
        assert err.actual_hash == "xyz"
        assert "Hash mismatch" in str(err)

    def test_defaults(self):
        err = EvidenceIntegrityError("msg", chain_id="c1")
        assert err.node_id is None
        assert err.expected_hash is None


class TestChainNotFoundError:
    def test_message(self):
        err = ChainNotFoundError("c-missing")
        assert err.chain_id == "c-missing"
        assert "c-missing" in str(err)


class TestChainClosedError:
    def test_message(self):
        err = ChainClosedError("c-closed")
        assert err.chain_id == "c-closed"
        assert "c-closed" in str(err)
