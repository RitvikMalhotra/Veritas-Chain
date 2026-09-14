"""Pattern-based relation extraction over FIR narratives, using already-extracted entity mentions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterator

from veritas import normalize
from veritas.config import get_confidence_settings
from veritas.models import (
    AssociatedWith, Called, EdgeType, ExtractionMethod, MemberOf, MetAt, NodeType, OwnsVehicle, PresentAtEvent,
    TransferredMoneyTo, UsesPhone, make_node_id,
)

EVENT = -1  # endpoint marker for "this document's incident"
_CODE = {NodeType.PERSON: "P", NodeType.PHONE: "T", NodeType.LOCATION: "L", NodeType.ORGANIZATION: "O", NodeType.VEHICLE: "V"}
_EDGE_CLASS = {cls.model_fields["type"].default: cls for cls in
               (Called, MetAt, TransferredMoneyTo, MemberOf, PresentAtEvent, OwnsVehicle, UsesPhone, AssociatedWith)}

# ---------- Cue patterns over masked sentences (entities replaced by tokens like ⟦P3⟧) ----------
# Cue words come from FIR phrasing ("who uses mobile number", "a director of") plus inflections of the same verbs.

_PL = r"(?:⟦P\d+⟧(?:\s*,\s*(?:and\s+)?|\s+and\s+))*⟦P\d+⟧"  # list of people: "A, B and C"
_PVL = r"(?:⟦[PV]\d+⟧(?:\s*,\s*(?:and\s+)?|\s+and\s+))*⟦[PV]\d+⟧"  # list of people and/or vehicles
_PHONE_CUE = r"(?:mobile|phone|cell)(?:\s+phone)?\s+(?:no\.?|number|bearing\s+number)"
_USE = r"(?:uses|used|using|use)"

_USES_PHONE = re.compile(
    rf"⟦P(?P<p>\d+)⟧(?:\s*\(\s*|\s*,\s*who\s+{_USE}\s+|\s+(?:is\s+|was\s+)?(?:known\s+to\s+)?{_USE}\s+"
    rf"|\s+can\s+be\s+contacted\s+on\s+|\s+was\s+carrying\s+an?\s+){_PHONE_CUE}\s+⟦T(?P<t>\d+)⟧")
_PHONE_BELONGING = re.compile(r"⟦T(?P<t>\d+)⟧\s+belonging\s+to\s+⟦P(?P<p>\d+)⟧")
_CALLED_FROM_NUMBER = re.compile(rf"⟦P(?P<p>\d+)⟧\s+called\s+⟦P(?P<callee>\d+)⟧\s+from\s+{_PHONE_CUE}\s+⟦T(?P<t>\d+)⟧")
_CALL_FROM_NUMBER = re.compile(r"\bcall(?:s|er|ed)?\b(?:[^⟦]|⟦[LOPV]\d+⟧)*?\b(?:from|using)\s+" + _PHONE_CUE + r"\s+⟦T(?P<t>\d+)⟧")
_PERSON_CALLED_PERSON = re.compile(r"⟦P(?P<a>\d+)⟧\s+(?:had\s+)?called\s+⟦P(?P<b>\d+)⟧")
_MEMBER_OF = re.compile(
    r"⟦P(?P<p>\d+)⟧(?:\s*\(\s*mobile\s+no\.?\s+⟦T\d+⟧\s*\))?\s*,?\s*"
    r"(?:who\s+(?:works|worked|is\s+working)\s+(?:at|for)|an?\s+(?:employee|director)\s+of)\s+⟦O(?P<o>\d+)⟧")
_REGISTERED_TO = re.compile(r"⟦V(?P<v>\d+)⟧(?:[^⟦]|⟦[LOT]\d+⟧)*?\b(?:is|was)\s+registered\s+to\s+⟦[PO](?P<o>\d+)⟧")
_POSSESSIVE_VEHICLE = re.compile(r"⟦P(?P<p>\d+)⟧['’]s\s+(?:[\w-]+\s+){0,5}?bearing\s+registration\s+number\s+⟦V(?P<v>\d+)⟧")
_MET_AT = re.compile(rf"(?P<subj>{_PL})(?:[^⟦]|⟦[LOTV]\d+⟧)*?\bmet\s+(?P<obj>{_PL})\s+at\s+⟦[LO](?P<place>\d+)⟧")
_PRESENT_PASSIVE = re.compile(
    rf"(?P<list>{_PVL})(?:\s*,(?:[^⟦,]|⟦[OT]\d+⟧)*,)?\s+(?:were|was)\s+(?:also\s+)?(?:apprehended|detained|found|present|recovered)\b")
_ARRIVED_ON = re.compile(rf"(?P<list>{_PL})\s+(?:arrived|came)\s+on\s+[^⟦]*?⟦V(?P<v>\d+)⟧")
_VEHICLE_WAITED = re.compile(r"⟦V(?P<v>\d+)⟧\s+waited\b")
_DRIVEN_BY = re.compile(r"⟦V(?P<v>\d+)⟧,\s+driven\s+by\s+⟦P(?P<p>\d+)⟧")
_WITNESSED = re.compile(r"⟦P(?P<p>\d+)⟧(?:\s*,(?:[^⟦,]|⟦O\d+⟧)*,)?\s+witnessed\b")
_CASH_TRANSFER = re.compile(r"⟦P(?P<a>\d+)⟧[^⟦.]*?\b(?:paid|handed\s+over)\s+₹\s?[\d,]+\s+in\s+cash\s+to\s+⟦P(?P<b>\d+)⟧")
_ACCOUNT_WORDS = re.compile(r"\b(?:account|UPI|NEFT|IMPS|RTGS|bank)\b", re.I)  # decision 3: no Person->Person money if a bank channel is named

# Place interpretation (decision 2): "X, City" gives X a city; a business in a place phrase is a Location.
_PLACE_WITH_CITY = re.compile(r"⟦L(?P<i>\d+)⟧,\s*⟦L(?P<city>\d+)⟧")
# City is required: without it, "who works at ⟦O⟧" would wrongly turn the employer into a place.
_BUSINESS_AS_PLACE = re.compile(r"\b(?:at|near|outside|around)\s+⟦O(?P<i>\d+)⟧,\s*⟦L(?P<city>\d+)⟧")
_MET_PLACE = re.compile(rf"\bmet\s+{_PL}\s+at\s+⟦O(?P<i>\d+)⟧")

# FIR conventions for references: "the complainant" and "the vehicle".
_COMPLAINANT_INTRO = re.compile(r"\bcomplainant\s+(?:(?:Shri|Smt|Sri|Mr|Mrs|Ms|Dr)\.?\s+)?$", re.I)
_COMPLAINANT_REF = re.compile(r"\bthe complainant\b", re.I)
_VEHICLE_REF = re.compile(r"\bthe vehicle\b", re.I)
_ABBREVIATIONS = {"no", "smt", "shri", "sri", "mr", "mrs", "ms", "dr", "st", "rs"}


@dataclass(frozen=True)
class Mention:
    idx: int
    node_type: NodeType
    text: str
    start: int
    end: int
    confidence: float

    @classmethod
    def from_record(cls, idx: int, record: dict[str, Any]) -> Mention:
        # Accepts Phase 2 output (start_char/end_char) or ground-truth annotations (start/end).
        start = record.get("start_char", record.get("start"))
        end = record.get("end_char", record.get("end"))
        node_type = NodeType(record["node_type"])
        confidence = record.get("confidence")
        if confidence is None:
            method = "regex" if node_type in (NodeType.PHONE, NodeType.VEHICLE) else "spacy_ner"
            confidence = get_confidence_settings().mention_default(method, node_type.value)
        return cls(idx, node_type, record["text"], start, end, confidence)


@dataclass(frozen=True)
class ResolvedEntity:
    mention: Mention
    node_type: NodeType  # can differ from the mention's type: a business in a place phrase becomes a Location
    node_id: str | None  # None when the text has no usable key (e.g. only a title)
    name: str
    city: str | None = None
    is_city_of_place: bool = False  # consumed as another place's city, so not a node of its own


@dataclass(frozen=True)
class TextRelation:
    edge_type: EdgeType
    source_id: str
    target_id: str
    method: ExtractionMethod
    rule: str
    confidence: float
    sentence: str


@dataclass(frozen=True)
class DocumentInterpretation:
    document_id: str
    entities: list[ResolvedEntity]
    relations: list[TextRelation]


def split_sentences(text: str, mentions: list[Mention]) -> list[tuple[int, int]]:
    """Sentence spans. A period after a known abbreviation or inside an entity does not end a sentence."""
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?=\s+[A-Z(\"'])", text):
        i = m.start()
        word = re.search(r"(\w+)$", text[:i])
        if word and word.group(1).lower() in _ABBREVIATIONS:
            continue
        if any(x.start <= i < x.end - 1 for x in mentions):
            continue
        spans.append((start, i + 1))
        start = i + 1 + (len(text[i + 1:]) - len(text[i + 1:].lstrip()))
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _find_complainant(text: str, mentions: list[Mention]) -> Mention | None:
    # The person introduced as "The complainant [Shri/Smt.] <name>".
    people = [m for m in mentions if m.node_type == NodeType.PERSON]
    return next((m for m in people if _COMPLAINANT_INTRO.search(text[max(0, m.start - 30):m.start])), None)


def _alias_spans(text: str, mentions: list[Mention], complainant: Mention | None) -> list[tuple[int, int, str]]:
    """Spans of "the complainant" / "the vehicle" with the token of the entity they refer to."""
    aliases = []
    if complainant:
        aliases += [(r.start(), r.end(), f"⟦P{complainant.idx}⟧") for r in _COMPLAINANT_REF.finditer(text)
                    if r.start() >= complainant.end]
    vehicles = [m for m in mentions if m.node_type == NodeType.VEHICLE]
    for r in _VEHICLE_REF.finditer(text):
        earlier = [v for v in vehicles if v.end <= r.start()]
        if earlier:
            aliases.append((r.start(), r.end(), f"⟦V{earlier[-1].idx}⟧"))
    taken = [(m.start, m.end) for m in mentions]
    return [a for a in aliases if not any(a[0] < e and s < a[1] for s, e in taken)]


def _mask(text: str, span: tuple[int, int], mentions: list[Mention], aliases: list[tuple[int, int, str]]) -> str:
    lo, hi = span
    pieces = sorted([(m.start, m.end, f"⟦{_CODE[m.node_type]}{m.idx}⟧") for m in mentions if lo <= m.start and m.end <= hi]
                    + [a for a in aliases if lo <= a[0] and a[1] <= hi])
    out, pos = [], lo
    for s, e, token in pieces:
        out.append(text[pos:s])
        out.append(token)
        pos = e
    out.append(text[pos:hi])
    return "".join(out)


def _resolve_entities(mentions: list[Mention], masked: list[str]) -> dict[int, ResolvedEntity]:
    city_of: dict[int, int] = {}
    as_place: set[int] = set()
    for sentence in masked:
        for m in _PLACE_WITH_CITY.finditer(sentence):
            city_of[int(m["i"])] = int(m["city"])
        for m in _BUSINESS_AS_PLACE.finditer(sentence):
            as_place.add(int(m["i"]))
            if m["city"]:
                city_of[int(m["i"])] = int(m["city"])
        as_place.update(int(m["i"]) for m in _MET_PLACE.finditer(sentence))
    by_idx = {m.idx: m for m in mentions}
    consumed = set(city_of.values())
    resolved = {}
    for m in mentions:
        node_type = NodeType.LOCATION if m.idx in as_place else m.node_type
        city = by_idx[city_of[m.idx]].text if m.idx in city_of else None
        try:
            if node_type == NodeType.PERSON:
                key = normalize.person_key(m.text)
            elif node_type == NodeType.ORGANIZATION:
                key = normalize.organization_key(m.text)
            elif node_type == NodeType.LOCATION:
                key = normalize.location_key(m.text, city)
            elif node_type == NodeType.PHONE:
                key = normalize.phone_key(m.text)
            else:
                key = normalize.plate_key(m.text)
            node_id = make_node_id(node_type, key)
        except ValueError:
            node_id = None
        resolved[m.idx] = ResolvedEntity(m, node_type, node_id, m.text, city, m.idx in consumed)
    return resolved


def _pattern_hits(sentence: str, phone_of: dict[int, int], complainant: int | None) -> Iterator[tuple[EdgeType, int, int, str]]:
    for m in _CALLED_FROM_NUMBER.finditer(sentence):
        callee_phone = phone_of.get(int(m["callee"]))
        if callee_phone is not None:
            yield EdgeType.CALLED, int(m["t"]), callee_phone, "called_from_number"
    if complainant is not None and complainant in phone_of:
        for m in _CALL_FROM_NUMBER.finditer(sentence):
            yield EdgeType.CALLED, int(m["t"]), phone_of[complainant], "call_to_complainant"  # complainant reports calls received
    if "⟦T" not in sentence:  # decision 3: Person->Person only when no number is given
        for m in _PERSON_CALLED_PERSON.finditer(sentence):
            yield EdgeType.CALLED, int(m["a"]), int(m["b"]), "person_called_person"
    for m in _MEMBER_OF.finditer(sentence):
        yield EdgeType.MEMBER_OF, int(m["p"]), int(m["o"]), "member_of"
    for m in _REGISTERED_TO.finditer(sentence):
        yield EdgeType.OWNS_VEHICLE, int(m["o"]), int(m["v"]), "registered_to"
    for m in _POSSESSIVE_VEHICLE.finditer(sentence):
        yield EdgeType.OWNS_VEHICLE, int(m["p"]), int(m["v"]), "possessive_vehicle"
    for m in _MET_AT.finditer(sentence):
        for p in re.findall(r"⟦P(\d+)⟧", m["subj"] + m["obj"]):
            yield EdgeType.MET_AT, int(p), int(m["place"]), "met_at"
    for m in _PRESENT_PASSIVE.finditer(sentence):
        for i in re.findall(r"⟦[PV](\d+)⟧", m["list"]):
            yield EdgeType.PRESENT_AT_EVENT, int(i), EVENT, "present_passive"
    for m in _ARRIVED_ON.finditer(sentence):
        for i in [*re.findall(r"⟦P(\d+)⟧", m["list"]), m["v"]]:
            yield EdgeType.PRESENT_AT_EVENT, int(i), EVENT, "arrived_on"
    for m in _VEHICLE_WAITED.finditer(sentence):
        yield EdgeType.PRESENT_AT_EVENT, int(m["v"]), EVENT, "vehicle_waited"
    for m in _DRIVEN_BY.finditer(sentence):
        yield EdgeType.PRESENT_AT_EVENT, int(m["v"]), EVENT, "driven_by"
        yield EdgeType.PRESENT_AT_EVENT, int(m["p"]), EVENT, "driven_by"
    for m in _WITNESSED.finditer(sentence):
        yield EdgeType.PRESENT_AT_EVENT, int(m["p"]), EVENT, "witnessed"
    if not _ACCOUNT_WORDS.search(sentence):
        for m in _CASH_TRANSFER.finditer(sentence):
            yield EdgeType.TRANSFERRED_MONEY_TO, int(m["a"]), int(m["b"]), "cash_transfer"


def interpret_document(document_id: str, narrative: str, records: list[dict[str, Any]], event_id: str) -> DocumentInterpretation:
    mentions = sorted((Mention.from_record(i, r) for i, r in enumerate(records)), key=lambda m: m.start)
    by_idx = {m.idx: m for m in mentions}
    complainant_mention = _find_complainant(narrative, mentions)
    complainant = complainant_mention.idx if complainant_mention else None
    aliases = _alias_spans(narrative, mentions, complainant_mention)
    spans = split_sentences(narrative, mentions)
    masked = [_mask(narrative, span, mentions, aliases) for span in spans]
    entities = _resolve_entities(mentions, masked)
    settings = get_confidence_settings()

    # Pass 1: who uses which phone (needed to direct CALLED edges in pass 2).
    uses: list[tuple[EdgeType, int, int, str, int]] = []
    phone_of: dict[int, int] = {}
    for n, sentence in enumerate(masked):
        hits = [(int(m["p"]), int(m["t"]), "uses_phone") for m in _USES_PHONE.finditer(sentence)]
        hits += [(int(m["p"]), int(m["t"]), "phone_belonging_to") for m in _PHONE_BELONGING.finditer(sentence)]
        hits += [(int(m["p"]), int(m["t"]), "called_from_number") for m in _CALLED_FROM_NUMBER.finditer(sentence)]
        for p, t, rule in hits:
            phone_of.setdefault(p, t)
            uses.append((EdgeType.USES_PHONE, p, t, rule, n))
    hits = uses + [(*h, n) for n, s in enumerate(masked) for h in _pattern_hits(s, phone_of, complainant)]

    def endpoint(i: int) -> str | None:
        return event_id if i == EVENT else entities[i].node_id

    def node_type(i: int) -> NodeType:
        return NodeType.EVENT if i == EVENT else entities[i].node_type

    relations: dict[tuple, TextRelation] = {}
    linked: set[frozenset] = set()

    def add(edge_type, src, dst, rule, n, method, confidence):
        source, target = endpoint(src), endpoint(dst)
        if source is None or target is None or source == target:
            return
        if (node_type(src), node_type(dst)) not in _EDGE_CLASS[edge_type].ALLOWED_ENDPOINTS:
            return  # e.g. a Person tagged as ORG where the rule expects a person
        key = (edge_type, source, target)
        if key not in relations:
            relations[key] = TextRelation(edge_type, source, target, method, rule, confidence,
                                          narrative[spans[n][0]:spans[n][1]])
            linked.add(frozenset((source, target)))

    for edge_type, src, dst, rule, n in hits:
        confs = [settings.edge_default(ExtractionMethod.TEXT_PATTERN.value)]
        confs += [by_idx[i].confidence for i in (src, dst) if i != EVENT]
        add(edge_type, src, dst, rule, n, ExtractionMethod.TEXT_PATTERN, min(confs))

    # Same-sentence people with no pattern relation between them get a weak ASSOCIATED_WITH edge.
    for n, sentence in enumerate(masked):
        people: dict[str, int] = {}
        for i in re.findall(r"⟦P(\d+)⟧", sentence):
            node_id = entities[int(i)].node_id
            if node_id and entities[int(i)].node_type == NodeType.PERSON:
                people.setdefault(node_id, int(i))
        for (a, ia), (b, ib) in combinations(people.items(), 2):
            if frozenset((a, b)) not in linked:
                confidence = min(settings.edge_default(ExtractionMethod.TEXT_COOCCURRENCE.value),
                                 by_idx[ia].confidence, by_idx[ib].confidence)
                add(EdgeType.ASSOCIATED_WITH, ia, ib, "same_sentence", n, ExtractionMethod.TEXT_COOCCURRENCE, confidence)

    return DocumentInterpretation(document_id, [entities[m.idx] for m in mentions], list(relations.values()))
