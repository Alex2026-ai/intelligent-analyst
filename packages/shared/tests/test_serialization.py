"""Round-trip JSON serialization tests for all models.

Every model must survive: model -> JSON -> model with identical field values.
"""

from ia_shared.models.resolution import (
    BatchResolutionRequest,
    BatchResolutionResponse,
    BatchResultItem,
    BatchItemStatus,
    DocumentMetadata,
    DocumentType,
    Priority,
    ResolutionRequest,
    ResolutionResponse,
    ResolutionStatus,
    ReviewReason,
    BatchConfig,
)
from ia_shared.models.evidence import (
    ChainStatus,
    EvidenceChain,
    EvidenceNode,
    NodeType,
)
from ia_shared.models.review import (
    CasePriority,
    CaseStatus,
    Decision,
    QueueStats,
    ReviewCase,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueResponse,
    ReviewReason as ReviewReviewReason,
)
from ia_shared.models.export import (
    ExportFormat,
    ExportRequest,
    ExportResponse,
    ExportStatus,
)
from ia_shared.models.events import (
    EventType,
    ExportRequestedData,
    ExportRequestedEvent,
    ResolutionCompletedData,
    ResolutionCompletedEvent,
    ReviewDecisionMadeData,
    ReviewDecisionMadeEvent,
)
from ia_shared.models.errors import (
    ErrorDetail,
    ErrorResponse,
    VALIDATION_ERROR,
)
from ia_shared.models.health import (
    CheckStatus,
    CircuitBreakerState,
    CircuitBreakers,
    HealthStatus,
    LiveHealthResponse,
    ReadyHealthResponse,
    StartupChecks,
    StartupHealthResponse,
)
from ia_shared.models.tenant import (
    Role,
    TenantConfig,
    UserRecord,
)


def roundtrip(model_instance):
    """Serialize to JSON and deserialize back, asserting equality."""
    json_str = model_instance.model_dump_json()
    reconstructed = type(model_instance).model_validate_json(json_str)
    assert reconstructed.model_dump() == model_instance.model_dump()
    return reconstructed


class TestResolutionRoundTrip:
    def test_resolution_request(self):
        roundtrip(
            ResolutionRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000",
                document_type=DocumentType.REGULATORY,
                content="Test content",
                metadata=DocumentMetadata(
                    source="test", priority=Priority.HIGH, force_review=True
                ),
            )
        )

    def test_resolution_response(self):
        roundtrip(
            ResolutionResponse(
                resolution_id="r1",
                status=ResolutionStatus.RESOLVED,
                layer_used=2,
                confidence=0.92,
                resolution="Matched",
                evidence_chain_id="ec1",
                created_at="2026-03-21T10:00:00Z",
            )
        )

    def test_resolution_response_routed(self):
        roundtrip(
            ResolutionResponse(
                resolution_id="r1",
                status=ResolutionStatus.ROUTED_TO_REVIEW,
                layer_used=4,
                confidence=0.3,
                resolution=None,
                review_reason=ReviewReason.LOW_CONFIDENCE,
                evidence_chain_id="ec1",
                created_at="2026-03-21T10:00:00Z",
            )
        )

    def test_batch_request(self):
        roundtrip(
            BatchResolutionRequest(
                documents=[
                    ResolutionRequest(
                        document_id="550e8400-e29b-41d4-a716-446655440000",
                        document_type=DocumentType.FINANCIAL,
                        content="test",
                    )
                ],
                batch_config=BatchConfig(max_parallel=3, stop_on_error=True),
            )
        )

    def test_batch_response(self):
        roundtrip(
            BatchResolutionResponse(
                batch_id="b1",
                total=1,
                resolved=1,
                routed_to_review=0,
                failed=0,
                results=[
                    BatchResultItem(
                        document_id="d1",
                        resolution_id="r1",
                        status=BatchItemStatus.RESOLVED,
                        layer_used=1,
                        confidence=1.0,
                    )
                ],
                created_at="2026-03-21T10:00:00Z",
            )
        )


class TestEvidenceRoundTrip:
    def test_evidence_chain(self):
        roundtrip(
            EvidenceChain(
                chain_id="c1",
                resolution_id="r1",
                tenant_id="t1",
                status=ChainStatus.COMPLETE,
                chain_hash="hashvalue",
                nodes=[
                    EvidenceNode(
                        node_id="n1",
                        node_type=NodeType.SOURCE_ARTIFACT,
                        sequence=1,
                        timestamp="2026-03-21T10:00:00Z",
                        node_hash="h1",
                        data={"key": "value"},
                    )
                ],
                created_at="2026-03-21T10:00:00Z",
                updated_at="2026-03-21T10:00:01Z",
            )
        )


class TestReviewRoundTrip:
    def test_review_decision_request(self):
        roundtrip(
            ReviewDecisionRequest(
                decision=Decision.APPROVE,
                notes="Confirmed match after full evidence review.",
                evidence_reviewed=["n1", "n2"],
            )
        )

    def test_review_case(self):
        roundtrip(
            ReviewCase(
                case_id="c1",
                resolution_id="r1",
                evidence_chain_id="ec1",
                status=CaseStatus.PENDING,
                priority=CasePriority.HIGH,
                review_reason=ReviewReviewReason.HIGH_IMPACT,
                sla_deadline="2026-03-22T10:00:00Z",
                created_at="2026-03-21T10:00:00Z",
            )
        )

    def test_review_queue_response(self):
        roundtrip(
            ReviewQueueResponse(
                cases=[],
                queue_stats=QueueStats(
                    total_pending=0,
                    total_assigned=0,
                    oldest_case_age_hours=0.0,
                    sla_breaches=0,
                ),
            )
        )

    def test_review_decision_response(self):
        roundtrip(
            ReviewDecisionResponse(
                case_id="c1",
                decision=Decision.REJECT,
                decided_by="user-1",
                decided_at="2026-03-21T10:00:00Z",
                evidence_chain_updated=True,
            )
        )


class TestExportRoundTrip:
    def test_export_request(self):
        roundtrip(
            ExportRequest(
                resolution_id="r1",
                format=ExportFormat.PDF,
                include_evidence=True,
                include_source_document=False,
            )
        )

    def test_export_response_queued(self):
        roundtrip(
            ExportResponse(
                export_id="e1",
                status=ExportStatus.QUEUED,
                format=ExportFormat.PDF,
                estimated_completion_seconds=30,
                created_at="2026-03-21T10:00:00Z",
            )
        )

    def test_export_response_complete(self):
        roundtrip(
            ExportResponse(
                export_id="e1",
                status=ExportStatus.COMPLETE,
                format=ExportFormat.CSV,
                download_url="https://storage.googleapis.com/bucket/file",
                created_at="2026-03-21T10:00:00Z",
                completed_at="2026-03-21T10:01:00Z",
            )
        )


class TestEventRoundTrip:
    def test_resolution_completed_event(self):
        roundtrip(
            ResolutionCompletedEvent(
                event_id="e1",
                timestamp="2026-03-21T10:00:00Z",
                tenant_id="t1",
                correlation_id="c1",
                data=ResolutionCompletedData(
                    resolution_id="r1",
                    document_id="d1",
                    status="resolved",
                    layer_used=2,
                    confidence=0.95,
                    evidence_chain_id="ec1",
                ),
            )
        )

    def test_review_decision_made_event(self):
        roundtrip(
            ReviewDecisionMadeEvent(
                event_id="e2",
                timestamp="2026-03-21T10:00:00Z",
                tenant_id="t1",
                correlation_id="c2",
                data=ReviewDecisionMadeData(
                    case_id="c1",
                    resolution_id="r1",
                    decision="approve",
                    decided_by="user-1",
                    evidence_chain_id="ec1",
                ),
            )
        )

    def test_export_requested_event(self):
        roundtrip(
            ExportRequestedEvent(
                event_id="e3",
                timestamp="2026-03-21T10:00:00Z",
                tenant_id="t1",
                correlation_id="c3",
                data=ExportRequestedData(
                    export_id="ex1",
                    resolution_id="r1",
                    evidence_chain_id="ec1",
                    format="pdf",
                    include_evidence=True,
                    include_source_document=False,
                    requested_by="user-1",
                ),
            )
        )


class TestErrorRoundTrip:
    def test_error_response(self):
        roundtrip(
            ErrorResponse(
                error=ErrorDetail(
                    code=VALIDATION_ERROR,
                    message="Invalid input",
                    correlation_id="trace-1",
                    retry=False,
                )
            )
        )


class TestHealthRoundTrip:
    def test_startup_health(self):
        roundtrip(
            StartupHealthResponse(
                status=HealthStatus.HEALTHY,
                checks=StartupChecks(
                    config=CheckStatus.OK,
                    secrets=CheckStatus.OK,
                    firestore=CheckStatus.OK,
                    schema_version=CheckStatus.OK,
                ),
                version="1.0.0",
                started_at="2026-03-21T10:00:00Z",
            )
        )

    def test_ready_health(self):
        roundtrip(
            ReadyHealthResponse(
                status=HealthStatus.READY,
                circuit_breakers=CircuitBreakers(
                    llm_provider_a=CircuitBreakerState.CLOSED,
                    llm_provider_b=CircuitBreakerState.CLOSED,
                    firestore_reads=CircuitBreakerState.CLOSED,
                    firestore_writes=CircuitBreakerState.CLOSED,
                    gcs=CircuitBreakerState.CLOSED,
                ),
            )
        )

    def test_live_health(self):
        roundtrip(
            LiveHealthResponse(
                status=HealthStatus.ALIVE,
                timestamp="2026-03-21T10:00:00Z",
            )
        )


class TestTenantRoundTrip:
    def test_user_record(self):
        roundtrip(
            UserRecord(
                user_id="u1",
                tenant_id="t1",
                role=Role.ANALYST,
                email="analyst@example.com",
                display_name="Test Analyst",
                active=True,
                created_at="2026-03-21T10:00:00Z",
                updated_at="2026-03-21T10:00:00Z",
            )
        )

    def test_tenant_config(self):
        roundtrip(
            TenantConfig(
                tenant_id="t1",
                tenant_name="Acme Corp",
                region="us-central1",
                confidence_threshold=0.85,
                high_impact_threshold=0.95,
                rate_limit_per_minute=100,
                review_sla_hours=24,
                l3_max_cost_usd=10.0,
                created_at="2026-03-21T10:00:00Z",
                updated_at="2026-03-21T10:00:00Z",
            )
        )
