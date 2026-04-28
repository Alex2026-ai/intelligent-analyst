"""Tests for export preconditions — INV-004 enforcement."""

from apps.api.src.export.preconditions import check_export_preconditions


class TestExportPreconditions:
    def test_complete_chain_allowed(self):
        result = check_export_preconditions("complete", [], is_high_impact=False)
        assert result.allowed is True

    def test_incomplete_chain_blocked(self):
        result = check_export_preconditions("building", [], is_high_impact=False)
        assert result.allowed is False
        assert "not complete" in result.reason

    def test_high_impact_without_approval_blocked(self):
        nodes = [
            {"node_type": "source_artifact", "data": {}},
            {"node_type": "transformation", "data": {}},
        ]
        result = check_export_preconditions("complete", nodes, is_high_impact=True)
        assert result.allowed is False
        assert "INV-004" in result.reason

    def test_high_impact_with_approval_allowed(self):
        nodes = [
            {"node_type": "source_artifact", "data": {}},
            {"node_type": "human_decision", "data": {"decision": "approve"}},
        ]
        result = check_export_preconditions("complete", nodes, is_high_impact=True)
        assert result.allowed is True

    def test_high_impact_with_reject_blocked(self):
        nodes = [
            {"node_type": "human_decision", "data": {"decision": "reject"}},
        ]
        result = check_export_preconditions("complete", nodes, is_high_impact=True)
        assert result.allowed is False

    def test_non_high_impact_no_approval_needed(self):
        result = check_export_preconditions("complete", [], is_high_impact=False)
        assert result.allowed is True
