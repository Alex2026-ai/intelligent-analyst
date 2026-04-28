"""Golden record tests — run all golden records through L1/L2 resolution.

Each golden record defines an input document and expected outcome.
These serve as regression tests for the deterministic resolution core.
"""

import json
import os

import pytest

from apps.api.src.resolver.base import ResolverConfig
from apps.api.src.resolver.engine import resolve
from apps.api.tests.unit.resolver.conftest import SAMPLE_PRECEDENTS, SAMPLE_RULE_SET

GOLDEN_RECORDS_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..", "..",
    "test", "golden_records",
)


def load_golden_record(directory: str) -> dict:
    """Load a golden record's input and expected result files."""
    base = os.path.join(GOLDEN_RECORDS_DIR, directory)
    with open(os.path.join(base, "input.json")) as f:
        input_data = json.load(f)

    # Try both expected file names
    expected = None
    for name in ["expected_l1_result.json", "expected_l2_result.json"]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            with open(path) as f:
                expected = json.load(f)
            break

    evidence_path = os.path.join(base, "expected_evidence.json")
    with open(evidence_path) as f:
        expected_evidence = json.load(f)

    return {
        "input": input_data,
        "expected": expected,
        "expected_evidence": expected_evidence,
    }


def load_manifest() -> list[dict]:
    """Load the golden records manifest."""
    manifest_path = os.path.join(GOLDEN_RECORDS_DIR, "manifest.json")
    with open(manifest_path) as f:
        return json.load(f)["records"]


# Build test parameters from manifest
MANIFEST = load_manifest()
GOLDEN_RECORD_IDS = [(r["id"], r["directory"]) for r in MANIFEST]


@pytest.mark.parametrize("record_id,directory", GOLDEN_RECORD_IDS)
def test_golden_record(record_id: str, directory: str):
    """Run a golden record through the resolution engine and verify outcome."""
    gr = load_golden_record(directory)
    inp = gr["input"]
    expected = gr["expected"]
    expected_evidence = gr["expected_evidence"]

    config = ResolverConfig(
        review_threshold=0.85,
        l2_match_threshold=0.6,
    )

    result = resolve(
        content=inp["content"],
        document_type=inp["document_type"],
        metadata=inp.get("metadata", {}),
        config=config,
        rule_set=SAMPLE_RULE_SET,
        precedents=SAMPLE_PRECEDENTS,
    )

    # Verify status
    assert result.status == expected["status"], (
        f"{record_id}: expected status={expected['status']}, got {result.status}"
    )

    # Verify layer
    assert result.layer_used == expected["layer_used"], (
        f"{record_id}: expected layer={expected['layer_used']}, got {result.layer_used}"
    )

    # Verify confidence
    if "confidence" in expected:
        assert result.confidence == expected["confidence"], (
            f"{record_id}: expected confidence={expected['confidence']}, got {result.confidence}"
        )
    if "confidence_min" in expected:
        assert result.confidence >= expected["confidence_min"], (
            f"{record_id}: expected confidence>={expected['confidence_min']}, got {result.confidence}"
        )

    # Verify resolution text
    if expected.get("resolution") is not None:
        assert result.resolution == expected["resolution"], (
            f"{record_id}: resolution mismatch"
        )
    elif expected.get("resolution") is None and expected["status"] == "routed_to_review":
        # Resolution may or may not be None when routed to review
        pass

    # Verify review reason
    if expected.get("review_reason") is not None:
        assert result.review_reason == expected["review_reason"], (
            f"{record_id}: expected review_reason={expected['review_reason']}, got {result.review_reason}"
        )

    # Verify evidence
    assert len(result.evidence) >= expected_evidence["min_evidence_count"], (
        f"{record_id}: expected >={expected_evidence['min_evidence_count']} evidence records, "
        f"got {len(result.evidence)}"
    )

    evidence_types = {e.node_type for e in result.evidence}
    for required_type in expected_evidence["required_node_types"]:
        assert required_type in evidence_types, (
            f"{record_id}: missing required evidence node type: {required_type}"
        )


class TestGR001SimpleRegulatory:
    """GR-001: L1 resolves with confidence 1.0."""

    def test_resolves_at_l1(self):
        gr = load_golden_record("GR-001-simple-regulatory")
        config = ResolverConfig()
        result = resolve(
            content=gr["input"]["content"],
            document_type=gr["input"]["document_type"],
            metadata=gr["input"]["metadata"],
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.layer_used == 1
        assert result.confidence == 1.0
        assert result.status == "resolved"


class TestGR003ExactMatch:
    """GR-003: L2 exact match with confidence > 0.9."""

    def test_resolves_at_l2_with_high_confidence(self):
        gr = load_golden_record("GR-003-exact-match")
        config = ResolverConfig()
        result = resolve(
            content=gr["input"]["content"],
            document_type=gr["input"]["document_type"],
            metadata=gr["input"]["metadata"],
            config=config,
            rule_set=SAMPLE_RULE_SET,
            precedents=SAMPLE_PRECEDENTS,
        )
        assert result.layer_used == 2
        assert result.confidence > 0.9
        assert result.status == "resolved"
