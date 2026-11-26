"""Connector SDK (plan §10, Phase 3, T3.1): canonical models, protocol, mapping, registry."""

from connectors.sdk.canonical import (
    CanonicalActivity,
    CanonicalCertification,
    CanonicalDocument,
    CanonicalMeeting,
    CanonicalMessage,
    CanonicalMilestone,
    CanonicalPerson,
    CanonicalProject,
    CanonicalWorkOrder,
)
from connectors.sdk.mapping import FieldMap, MappingEngine, RecordMapping
from connectors.sdk.protocol import (
    Connector,
    ConnectorCapabilities,
    ConnectorHealth,
    NotSupportedError,
    RawRecord,
)
from connectors.sdk.registry import (
    BUILTIN_CONNECTORS,
    BaseConnector,
    get_connector,
    mode_for,
    register,
)

__all__ = [
    "BUILTIN_CONNECTORS",
    "BaseConnector",
    "CanonicalActivity",
    "CanonicalCertification",
    "CanonicalDocument",
    "CanonicalMeeting",
    "CanonicalMessage",
    "CanonicalMilestone",
    "CanonicalPerson",
    "CanonicalProject",
    "CanonicalWorkOrder",
    "Connector",
    "ConnectorCapabilities",
    "ConnectorHealth",
    "FieldMap",
    "MappingEngine",
    "NotSupportedError",
    "RawRecord",
    "RecordMapping",
    "get_connector",
    "mode_for",
    "register",
]
