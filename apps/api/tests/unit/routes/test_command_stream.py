"""Tests for SSE command stream endpoint."""

from apps.api.src.routes.command_stream import emit_stage, get_stages, _stage_store


class TestStageEmission:
    def setup_method(self):
        _stage_store.clear()

    def test_emit_and_get_stages(self):
        emit_stage("cmd_abc", "queued")
        emit_stage("cmd_abc", "pii_masking")
        stages = get_stages("cmd_abc")
        assert len(stages) == 2
        assert stages[0]["stage"] == "queued"
        assert stages[1]["stage"] == "pii_masking"

    def test_spec_anchor_on_pii(self):
        emit_stage("cmd_1", "pii_masking")
        stage = get_stages("cmd_1")[0]
        assert "spec_anchor" in stage
        assert stage["spec_anchor"]["spec_id"] == "INV-006"
        assert stage["spec_anchor"]["merkle_hash"]

    def test_spec_anchor_on_llm(self):
        emit_stage("cmd_2", "llm_resolve")
        stage = get_stages("cmd_2")[0]
        assert stage["spec_anchor"]["spec_id"] == "PHASE-8"

    def test_spec_anchor_on_evidence(self):
        emit_stage("cmd_3", "evidence_chain")
        stage = get_stages("cmd_3")[0]
        assert stage["spec_anchor"]["spec_id"] == "INV-002"

    def test_spec_anchor_on_tenant_scope(self):
        emit_stage("cmd_4", "tenant_scope")
        stage = get_stages("cmd_4")[0]
        assert stage["spec_anchor"]["spec_id"] == "INV-005"

    def test_no_anchor_on_queued(self):
        emit_stage("cmd_5", "queued")
        stage = get_stages("cmd_5")[0]
        assert "spec_anchor" not in stage

    def test_detail_passthrough(self):
        emit_stage("cmd_6", "pii_masking", {"tokens_masked": 3})
        stage = get_stages("cmd_6")[0]
        assert stage["detail"]["tokens_masked"] == 3

    def test_isolation_between_correlations(self):
        emit_stage("cmd_a", "queued")
        emit_stage("cmd_b", "pii_masking")
        assert len(get_stages("cmd_a")) == 1
        assert len(get_stages("cmd_b")) == 1
        assert get_stages("cmd_c") == []

    def test_merkle_hash_deterministic(self):
        emit_stage("cmd_7", "pii_masking")
        emit_stage("cmd_8", "pii_masking")
        h1 = get_stages("cmd_7")[0]["spec_anchor"]["merkle_hash"]
        h2 = get_stages("cmd_8")[0]["spec_anchor"]["merkle_hash"]
        assert h1 == h2  # Same spec → same hash
