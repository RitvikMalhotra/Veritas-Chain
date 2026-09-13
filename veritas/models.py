"""Pydantic models for every node, edge and entity mention. schema.md explains each rule."""

from __future__ import annotations

import hashlib
from datetime import timezone
from decimal import Decimal
from enum import StrEnum
from itertools import product
from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    computed_field,
    field_validator,
    model_validator,
)

from veritas import normalize
from veritas.config import get_confidence_settings


class NodeType(StrEnum):
    PERSON = "Person"
    PHONE = "Phone"
    LOCATION = "Location"
    ORGANIZATION = "Organization"
    VEHICLE = "Vehicle"
    EVENT = "Event"
    BANK_ACCOUNT = "BankAccount"


class EdgeType(StrEnum):
    CALLED = "CALLED"
    MET_AT = "MET_AT"
    TRANSFERRED_MONEY_TO = "TRANSFERRED_MONEY_TO"
    MEMBER_OF = "MEMBER_OF"
    PRESENT_AT_EVENT = "PRESENT_AT_EVENT"
    OWNS_VEHICLE = "OWNS_VEHICLE"
    USES_PHONE = "USES_PHONE"  # added beyond the brief, approved (schema.md section 6)
    HOLDS_ACCOUNT = "HOLDS_ACCOUNT"  # added beyond the brief, approved (schema.md section 6)
    ASSOCIATED_WITH = "ASSOCIATED_WITH"


class ExtractionMethod(StrEnum):
    STRUCTURED = "structured"  # row from a CDR / bank / registry file
    TEXT_PATTERN = "text_pattern"  # explicit phrase in a report, e.g. "X called Y"
    TEXT_COOCCURRENCE = "text_cooccurrence"  # two entities in one sentence, no relation phrase


class MentionMethod(StrEnum):
    REGEX = "regex"
    SPACY_NER = "spacy_ner"


def make_node_id(node_type: NodeType, key: str) -> str:
    return f"{node_type}:{key}"


def node_type_of(node_id: str) -> NodeType:
    """Read the type prefix of a node id, e.g. 'Phone:+919876543210' -> NodeType.PHONE."""
    prefix, sep, key = node_id.partition(":")
    if not sep or not key:
        raise ValueError(f"malformed node id {node_id!r}")
    return NodeType(prefix)


def _drop_supplied_id(data: Any) -> Any:
    # IDs are always recomputed from content; an id in the input is never trusted.
    if isinstance(data, dict) and "id" in data:
        data = {k: v for k, v in data.items() if k != "id"}
    return data


# ---------- Nodes ----------


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: NodeType
    source_document_ids: tuple[str, ...] = Field(min_length=1)  # every document that mentioned this entity

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: Any) -> Any:
        return _drop_supplied_id(data)

    def canonical_key(self) -> str:
        raise NotImplementedError

    @computed_field
    @property
    def id(self) -> str:
        return make_node_id(self.type, self.canonical_key())


class Person(_Node):
    type: Literal[NodeType.PERSON] = NodeType.PERSON
    name: str  # display form, as first seen

    @field_validator("name")
    @classmethod
    def _name_has_key(cls, v: str) -> str:
        normalize.person_key(v)  # rejects names that are only titles or punctuation
        return v

    def canonical_key(self) -> str:
        return normalize.person_key(self.name)


class Phone(_Node):
    type: Literal[NodeType.PHONE] = NodeType.PHONE
    number: str  # stored as E.164, e.g. +919876543210

    @field_validator("number")
    @classmethod
    def _to_e164(cls, v: str) -> str:
        return normalize.phone_key(v)

    def canonical_key(self) -> str:
        return self.number


class Location(_Node):
    type: Literal[NodeType.LOCATION] = NodeType.LOCATION
    name: str
    city: str | None = None  # part of the key when known

    @model_validator(mode="after")
    def _has_key(self) -> Location:
        self.canonical_key()
        return self

    def canonical_key(self) -> str:
        return normalize.location_key(self.name, self.city)


class Organization(_Node):
    type: Literal[NodeType.ORGANIZATION] = NodeType.ORGANIZATION
    name: str
    org_type: str | None = None  # free text, e.g. "shell company", "transport business"

    @field_validator("name")
    @classmethod
    def _name_has_key(cls, v: str) -> str:
        normalize.organization_key(v)
        return v

    def canonical_key(self) -> str:
        return normalize.organization_key(self.name)


class Vehicle(_Node):
    type: Literal[NodeType.VEHICLE] = NodeType.VEHICLE
    registration_number: str  # stored normalized, e.g. MH12AB1234
    make_model: str | None = None
    color: str | None = None

    @field_validator("registration_number")
    @classmethod
    def _normalize_plate(cls, v: str) -> str:
        return normalize.plate_key(v)

    def canonical_key(self) -> str:
        return self.registration_number


class Event(_Node):
    type: Literal[NodeType.EVENT] = NodeType.EVENT
    event_ref: str  # source-assigned reference; events are never merged by description
    event_type: str  # free text, e.g. "robbery", "drug seizure"
    occurred_at: AwareDatetime
    description: str | None = None

    @field_validator("event_ref")
    @classmethod
    def _ref_has_key(cls, v: str) -> str:
        normalize.text_key(v)
        return v

    def canonical_key(self) -> str:
        return normalize.text_key(self.event_ref)


class BankAccount(_Node):
    type: Literal[NodeType.BANK_ACCOUNT] = NodeType.BANK_ACCOUNT
    ifsc: str
    account_number: str
    bank_name: str | None = None

    @field_validator("ifsc")
    @classmethod
    def _normalize_ifsc(cls, v: str) -> str:
        return normalize.ifsc_key(v)

    @field_validator("account_number")
    @classmethod
    def _normalize_account(cls, v: str) -> str:
        return normalize.account_number_key(v)

    def canonical_key(self) -> str:
        # Account numbers are only unique within a bank branch, so IFSC is part of the key.
        return f"{self.ifsc}:{self.account_number}"


# ---------- Edges ----------

_P, _PH, _L, _O, _V, _E, _B = (
    NodeType.PERSON,
    NodeType.PHONE,
    NodeType.LOCATION,
    NodeType.ORGANIZATION,
    NodeType.VEHICLE,
    NodeType.EVENT,
    NodeType.BANK_ACCOUNT,
)


class _Edge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    ALLOWED_ENDPOINTS: ClassVar[frozenset[tuple[NodeType, NodeType]]]
    TEXT_ONLY_ENDPOINTS: ClassVar[frozenset[tuple[NodeType, NodeType]]] = frozenset()  # pairs structured data may not use

    type: EdgeType
    source_id: str
    target_id: str
    timestamp: AwareDatetime  # timezone required; naive datetimes are rejected
    source_document_id: str = Field(min_length=1)
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0.0, le=1.0)  # filled from config by extraction_method if omitted

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: Any) -> Any:
        data = _drop_supplied_id(data)
        if isinstance(data, dict) and data.get("confidence") is None and "extraction_method" in data:
            method = ExtractionMethod(data["extraction_method"])
            data = {**data, "confidence": get_confidence_settings().edge_default(method.value)}
        return data

    @model_validator(mode="after")
    def _check_endpoints(self) -> _Edge:
        pair = (node_type_of(self.source_id), node_type_of(self.target_id))
        if pair not in self.ALLOWED_ENDPOINTS:
            allowed = ", ".join(sorted(f"{s}->{t}" for s, t in self.ALLOWED_ENDPOINTS))
            raise ValueError(f"{self.type} cannot connect {pair[0]}->{pair[1]}; allowed: {allowed}")
        if pair in self.TEXT_ONLY_ENDPOINTS and self.extraction_method == ExtractionMethod.STRUCTURED:
            raise ValueError(f"structured {self.type} must go through instrument nodes, not {pair[0]}->{pair[1]}")
        if self.source_id == self.target_id:
            raise ValueError("self-loops are not allowed")
        return self

    @computed_field
    @property
    def id(self) -> str:
        # Deterministic: re-ingesting the same record gives the same id, so duplicates collapse.
        utc = self.timestamp.astimezone(timezone.utc).isoformat()
        raw = "|".join([self.type, self.source_id, self.target_id, utc, self.source_document_id])
        return "edge:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


class Called(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_PH, _PH), (_P, _P)})
    TEXT_ONLY_ENDPOINTS = frozenset({(_P, _P)})  # Person->Person: report text only, when no number is given
    type: Literal[EdgeType.CALLED] = EdgeType.CALLED
    duration_seconds: int | None = Field(default=None, ge=0)
    call_type: Literal["voice", "sms"] = "voice"


class MetAt(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_P, _L)})
    type: Literal[EdgeType.MET_AT] = EdgeType.MET_AT


class TransferredMoneyTo(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_B, _B), (_P, _P)})
    TEXT_ONLY_ENDPOINTS = frozenset({(_P, _P)})  # Person->Person: report text only, when no account is given
    type: Literal[EdgeType.TRANSFERRED_MONEY_TO] = EdgeType.TRANSFERRED_MONEY_TO
    amount_inr: Decimal | None = Field(default=None, gt=0)
    transaction_ref: str | None = None
    mode: Literal["NEFT", "IMPS", "RTGS", "UPI", "CASH"] | None = None


class MemberOf(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_P, _O)})
    type: Literal[EdgeType.MEMBER_OF] = EdgeType.MEMBER_OF
    role: str | None = None


class PresentAtEvent(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_P, _E), (_V, _E)})
    type: Literal[EdgeType.PRESENT_AT_EVENT] = EdgeType.PRESENT_AT_EVENT


class OwnsVehicle(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_P, _V), (_O, _V)})
    type: Literal[EdgeType.OWNS_VEHICLE] = EdgeType.OWNS_VEHICLE


class UsesPhone(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_P, _PH)})
    type: Literal[EdgeType.USES_PHONE] = EdgeType.USES_PHONE


class HoldsAccount(_Edge):
    ALLOWED_ENDPOINTS = frozenset({(_P, _B), (_O, _B)})
    type: Literal[EdgeType.HOLDS_ACCOUNT] = EdgeType.HOLDS_ACCOUNT


class AssociatedWith(_Edge):
    ALLOWED_ENDPOINTS = frozenset(product(NodeType, NodeType))
    type: Literal[EdgeType.ASSOCIATED_WITH] = EdgeType.ASSOCIATED_WITH
    context: str = Field(min_length=1)  # why this link exists; the fallback edge must explain itself


Node = Annotated[
    Union[Person, Phone, Location, Organization, Vehicle, Event, BankAccount],
    Field(discriminator="type"),
]
Edge = Annotated[
    Union[
        Called, MetAt, TransferredMoneyTo, MemberOf, PresentAtEvent,
        OwnsVehicle, UsesPhone, HoldsAccount, AssociatedWith,
    ],
    Field(discriminator="type"),
]

NODE_ADAPTER: TypeAdapter[Node] = TypeAdapter(Node)
EDGE_ADAPTER: TypeAdapter[Edge] = TypeAdapter(Edge)


# ---------- Mentions (contract between Phase 2 extraction and Phase 3 graph building) ----------


class EntityMention(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Which node types each extractor is allowed to produce.
    METHOD_NODE_TYPES: ClassVar[dict[MentionMethod, frozenset[NodeType]]] = {
        MentionMethod.REGEX: frozenset({_PH, _V}),
        MentionMethod.SPACY_NER: frozenset({_P, _L, _O}),
    }

    document_id: str = Field(min_length=1)
    node_type: NodeType
    text: str = Field(min_length=1)  # surface form exactly as it appears in the document
    start_char: int = Field(ge=0)
    end_char: int
    method: MentionMethod
    confidence: float = Field(ge=0.0, le=1.0)  # filled from config by method and node type if omitted

    @model_validator(mode="before")
    @classmethod
    def _fill_confidence(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("confidence") is None and "method" in data and "node_type" in data:
            method, node_type = MentionMethod(data["method"]), NodeType(data["node_type"])
            if node_type not in cls.METHOD_NODE_TYPES[method]:  # reject before looking up a per-label default that can't exist
                raise ValueError(f"{method} is not allowed to produce {node_type} mentions")
            data = {**data, "confidence": get_confidence_settings().mention_default(method.value, node_type.value)}
        return data

    @model_validator(mode="after")
    def _check(self) -> EntityMention:
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        if self.end_char - self.start_char != len(self.text):
            raise ValueError("span length does not match text length")
        if self.node_type not in self.METHOD_NODE_TYPES[self.method]:
            raise ValueError(f"{self.method} is not allowed to produce {self.node_type} mentions")
        return self
