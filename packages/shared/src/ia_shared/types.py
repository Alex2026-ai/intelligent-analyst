"""Type aliases for Intelligent Analyst domain identifiers.

All ID types are NewType wrappers around str for type safety while maintaining
Firestore compatibility (no Python UUID objects).
"""

from typing import NewType

# Entity identifiers — all stored as strings for Firestore compatibility
TenantId = NewType("TenantId", str)
UserId = NewType("UserId", str)
ResolutionId = NewType("ResolutionId", str)
DocumentId = NewType("DocumentId", str)
BatchId = NewType("BatchId", str)
EvidenceChainId = NewType("EvidenceChainId", str)
EvidenceNodeId = NewType("EvidenceNodeId", str)
CaseId = NewType("CaseId", str)
ExportId = NewType("ExportId", str)
EventId = NewType("EventId", str)
CorrelationId = NewType("CorrelationId", str)
IdempotencyKey = NewType("IdempotencyKey", str)

# Hash types
SHA256Hash = NewType("SHA256Hash", str)

# ISO 8601 timestamp strings
ISOTimestamp = NewType("ISOTimestamp", str)
