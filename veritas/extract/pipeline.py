"""Entity extraction for one FIR: regex for phones and plates, spaCy NER for people, places and organisations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from veritas import normalize
from veritas.extract.documents import FirDocument
from veritas.extract.patterns import find_phones, find_plates
from veritas.models import EntityMention, MentionMethod, NodeType

# md over sm: measured on seeds 42 and 7, md finds people better (+5-10 F1) at the cost of more ORG false positives.
DEFAULT_MODEL = "en_core_web_md"

# spaCy labels kept, mapped to schema node types. DATE, MONEY, CARDINAL, PRODUCT, NORP etc. are not graph entities.
LABEL_MAP = {
    "PERSON": NodeType.PERSON,
    "ORG": NodeType.ORGANIZATION,
    "GPE": NodeType.LOCATION,
    "LOC": NodeType.LOCATION,
    "FAC": NodeType.LOCATION,
}

_KEY_FUNCTIONS = {
    NodeType.PERSON: normalize.person_key,
    NodeType.ORGANIZATION: normalize.organization_key,
    NodeType.LOCATION: lambda text: normalize.location_key(text, None),  # city attachment is a Phase 3 job
    NodeType.PHONE: normalize.phone_key,
    NodeType.VEHICLE: normalize.plate_key,
}


@dataclass(frozen=True)
class NerCandidate:
    text: str
    label: str  # raw spaCy label
    start_char: int
    end_char: int


def canonical_key(node_type: NodeType, text: str) -> str | None:
    try:
        return _KEY_FUNCTIONS[node_type](text)
    except ValueError:
        return None  # e.g. a PERSON span that is only a title


def merge(document_id: str, regex_mentions: list[EntityMention], candidates: list[NerCandidate]) -> list[dict[str, Any]]:
    """Combine both extractors. A spaCy span overlapping a regex match is dropped, since the regex match is format-validated."""
    records = [(m, "REGEX") for m in regex_mentions]
    taken = [(m.start_char, m.end_char) for m in regex_mentions]
    for c in candidates:
        node_type = LABEL_MAP.get(c.label)
        if node_type is None or any(c.start_char < end and start < c.end_char for start, end in taken):
            continue
        mention = EntityMention(document_id=document_id, node_type=node_type, text=c.text, start_char=c.start_char,
                                end_char=c.end_char, method=MentionMethod.SPACY_NER)
        records.append((mention, c.label))
    records.sort(key=lambda r: (r[0].start_char, r[0].end_char))
    return [{**m.model_dump(mode="json"), "raw_label": label, "canonical_key": canonical_key(m.node_type, m.text)}
            for m, label in records]


class Extractor:
    def __init__(self, model: str = DEFAULT_MODEL):
        import spacy  # imported here so regex-only code and tests don't need spaCy loaded

        self.model = model
        self.nlp = spacy.load(model)
        self.spacy_version = spacy.__version__
        self.model_version = self.nlp.meta["version"]

    def extract(self, doc: FirDocument) -> list[dict[str, Any]]:
        regex_mentions = find_phones(doc.fir_id, doc.narrative) + find_plates(doc.fir_id, doc.narrative)
        candidates = [NerCandidate(e.text, e.label_, e.start_char, e.end_char) for e in self.nlp(doc.narrative).ents]
        return merge(doc.fir_id, regex_mentions, candidates)
