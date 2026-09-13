"""Renders FIR-style reports and records the exact span of every planted entity mention."""

from __future__ import annotations

import random
from dataclasses import dataclass
from string import Formatter
from typing import Any

from veritas import normalize
from veritas.models import EntityMention, MentionMethod, NodeType, make_node_id
from veritas.synth.scenarios import CityRef, PhoneRef, Scenario
from veritas.synth.world import Place, SynthOrg, SynthPerson, Vehicle

SYNTHETIC_BANNER = "[SYNTHETIC RECORD - generated test data, not a real case]"
NARRATIVE_MARKER = "NARRATIVE"

# template -> (narrative text, relations stated in it). "EVENT" means this FIR's own incident.
TEMPLATES: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    "A_RAID": (
        "Acting on specific information, a police team conducted a raid at {place}, {city} on {when}. "
        "{acc1} and {acc2} were apprehended at the spot and 240 grams of a white crystalline substance suspected to be "
        "mephedrone was recovered from their possession. A {veh_color} {veh_model} bearing registration number {veh} "
        "was found parked at the spot and was seized. As per registration records, the vehicle is registered to {owner}. "
        "During questioning, {acc1} disclosed that the contraband was supplied by {leader}, who uses mobile number "
        "{leader_phone}. {acc2} further disclosed having met {leader} and {lt} at {meet_place}, {meet_city} two days "
        "before the raid to collect the consignment. Further investigation is in progress.",
        [("PRESENT_AT_EVENT", "acc1", "EVENT"), ("PRESENT_AT_EVENT", "acc2", "EVENT"), ("PRESENT_AT_EVENT", "veh", "EVENT"),
         ("OWNS_VEHICLE", "owner", "veh"), ("USES_PHONE", "leader", "leader_phone"),
         ("MET_AT", "acc2", "meet_place"), ("MET_AT", "leader", "meet_place"), ("MET_AT", "lt", "meet_place")],
    ),
    "A_PATROL": (
        "On {when}, a patrolling team noticed {acc1} and {acc2} standing near {place}, {city} and acting suspiciously. "
        "On search, 35 grams of suspected mephedrone packed in small pouches was recovered from {acc1}. {acc2} was "
        "carrying a mobile phone bearing number {acc2_phone}. During questioning, {acc1} stated that the pouches had "
        "been handed over by {lt}, who works for {leader}. Call detail records of the seized mobile phone have been requested.",
        [("PRESENT_AT_EVENT", "acc1", "EVENT"), ("PRESENT_AT_EVENT", "acc2", "EVENT"), ("USES_PHONE", "acc2", "acc2_phone")],
    ),
    "B_THEFT": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}) reported that the complainant's {cveh_color} "
        "{cveh_model} bearing registration number {cveh}, parked outside {place}, {city}, was stolen on {when}. CCTV "
        "footage from a nearby shop shows two persons breaking into the car while a {veh_color} {veh_model} bearing "
        "registration number {veh} waited nearby. A local resident identified the two persons as {b1} and {b2}, who are "
        "known associates of {leader}. The footage has been preserved.",
        [("USES_PHONE", "complainant", "c_phone"), ("OWNS_VEHICLE", "complainant", "cveh"),
         ("PRESENT_AT_EVENT", "veh", "EVENT"), ("PRESENT_AT_EVENT", "b1", "EVENT"), ("PRESENT_AT_EVENT", "b2", "EVENT")],
    ),
    "B_GARAGE": (
        "On {when}, a raid was conducted at {place}, {city} on information that stolen vehicles were being dismantled "
        "there. {b1}, {b2} and {b3} were found removing parts from motorcycles and were detained. A motorcycle bearing "
        "registration number {stolen}, whose owner is being traced, was recovered from the premises. During questioning, "
        "{b1} disclosed that the gang is run by {leader} and {lt}, and that {leader} handed over ₹3,50,000 in cash to "
        "{bridge2} of {bridge2_city} last month for disposing of stolen vehicles. {lt} can be contacted on mobile number {lt_phone}.",
        [("PRESENT_AT_EVENT", "b1", "EVENT"), ("PRESENT_AT_EVENT", "b2", "EVENT"), ("PRESENT_AT_EVENT", "b3", "EVENT"),
         ("PRESENT_AT_EVENT", "stolen", "EVENT"), ("TRANSFERRED_MONEY_TO", "leader", "bridge2"),
         ("USES_PHONE", "lt", "lt_phone")],
    ),
    "C_COMPLAINT": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}), who lives near {place}, {city}, reported that on "
        "{when}, a caller using mobile number {fraud_phone} claimed to be a bank official and said that the complainant's "
        "KYC had expired. On the caller's instructions, the complainant installed a screen-sharing application, after "
        "which ₹{amount} was debited from the complainant's account in {n_txn}. The complainant has submitted the bank "
        "statement. A request has been sent to the telecom service provider for subscriber details of mobile number {fraud_phone}.",
        [("USES_PHONE", "complainant", "c_phone"), ("CALLED", "fraud_phone", "c_phone")],
    ),
    "C_RAID": (
        "On {when}, a raid was conducted at the office of {front} at {place}, {city} on information that fraudulent calls "
        "were being made from the premises. {c1}, {c2} and {c3} were found calling members of the public using scripts "
        "about bank KYC updates and were detained. Fourteen mobile phones and six laptops were seized. {mule2}, a director "
        "of {front}, was also present at the office. Initial questioning revealed that the operation is run by {leader}, "
        "who uses mobile number {leader_phone} and is absconding.",
        [("PRESENT_AT_EVENT", "c1", "EVENT"), ("PRESENT_AT_EVENT", "c2", "EVENT"), ("PRESENT_AT_EVENT", "c3", "EVENT"),
         ("PRESENT_AT_EVENT", "mule2", "EVENT"), ("MEMBER_OF", "mule2", "front"), ("USES_PHONE", "leader", "leader_phone")],
    ),
    "D_COMPLAINT": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}), who runs a shop near {place}, {city}, reported "
        "receiving threatening calls over the past two days from mobile number {ext_phone}. The caller, who gave his name "
        "as {caller}, demanded ₹50,000 as protection money. On {when}, out of fear, the complainant paid ₹20,000 in cash "
        "to {collector} near the shop. {collector} came on a {veh_color} {veh_model} bearing registration number {veh}.",
        [("USES_PHONE", "complainant", "c_phone"), ("CALLED", "ext_phone", "c_phone"), ("USES_PHONE", "caller", "ext_phone"),
         ("TRANSFERRED_MONEY_TO", "complainant", "collector"), ("PRESENT_AT_EVENT", "complainant", "EVENT"),
         ("PRESENT_AT_EVENT", "collector", "EVENT"), ("PRESENT_AT_EVENT", "veh", "EVENT")],
    ),
    "D_VANDALISM": (
        "On {when}, {d1} and {d2} arrived on a {veh_color} {veh_model} bearing registration number {veh} at the shop of "
        "{c_title}{complainant} near {place}, {city}, damaged the shop counter and threatened {complainant} for not paying "
        "protection money. The incident was recorded on the shop's CCTV camera. As per information from local sources, "
        "{d1} had met {leader} and {lt} at {meet_place}, {meet_city} on the previous evening. {leader} is known to use "
        "mobile number {leader_phone}.",
        [("PRESENT_AT_EVENT", "d1", "EVENT"), ("PRESENT_AT_EVENT", "d2", "EVENT"), ("PRESENT_AT_EVENT", "veh", "EVENT"),
         ("PRESENT_AT_EVENT", "complainant", "EVENT"), ("MET_AT", "d1", "meet_place"), ("MET_AT", "leader", "meet_place"),
         ("MET_AT", "lt", "meet_place"), ("USES_PHONE", "leader", "leader_phone")],
    ),
    "D_DEMAND": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}) reported that {lt}, an associate of {leader}, has "
        "been demanding money from shopkeepers around {place}, {city}. On {when}, {lt} called the complainant from mobile "
        "number {lt_phone} and demanded ₹1,00,000. The complainant paid ₹25,000 through UPI out of fear and has now "
        "approached the police.",
        [("USES_PHONE", "complainant", "c_phone"), ("USES_PHONE", "lt", "lt_phone"), ("CALLED", "lt_phone", "c_phone")],
    ),
    "SNATCH": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}) reported that on {when}, while walking near "
        "{place}, {city}, two unidentified persons on a motorcycle snatched a gold chain weighing about 20 grams from the "
        "complainant's neck and fled. The registration number of the motorcycle could not be noted.",
        [("USES_PHONE", "complainant", "c_phone"), ("PRESENT_AT_EVENT", "complainant", "EVENT")],
    ),
    "PHONE_THEFT": (
        "The complainant {c_title}{complainant} reported that on {when}, a mobile phone bearing number {c_phone} belonging "
        "to the complainant was stolen from the complainant's bag in a crowd near {place}, {city}. The IMEI details have "
        "been submitted.",
        [("USES_PHONE", "complainant", "c_phone"), ("PRESENT_AT_EVENT", "complainant", "EVENT")],
    ),
    "ACCIDENT": (
        "On {when}, a {veh1_color} {veh1_model} bearing registration number {veh1}, driven by {driver1}, collided with a "
        "{veh2_color} {veh2_model} bearing registration number {veh2}, driven by {driver2}, near {place}, {city}. "
        "{driver2} sustained minor injuries and was taken to a nearby hospital. {driver1} (mobile no. {d1_phone}) "
        "remained at the spot and cooperated with the police.",
        [("PRESENT_AT_EVENT", "driver1", "EVENT"), ("PRESENT_AT_EVENT", "driver2", "EVENT"),
         ("PRESENT_AT_EVENT", "veh1", "EVENT"), ("PRESENT_AT_EVENT", "veh2", "EVENT"), ("USES_PHONE", "driver1", "d1_phone")],
    ),
    "ONLINE_CHEAT": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}), who lives near {place}, {city}, reported that on "
        "{when}, a caller using mobile number {scam_phone} offered a part-time online job and asked for a registration "
        "fee. The complainant paid ₹{amount} online, after which the caller stopped responding.",
        [("USES_PHONE", "complainant", "c_phone"), ("CALLED", "scam_phone", "c_phone")],
    ),
    "DISPUTE": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}) reported that on {when}, {accused}, a neighbour, "
        "quarrelled with the complainant over parking near {place}, {city} and slapped the complainant. {witness} "
        "witnessed the incident.",
        [("USES_PHONE", "complainant", "c_phone"), ("PRESENT_AT_EVENT", "complainant", "EVENT"),
         ("PRESENT_AT_EVENT", "accused", "EVENT"), ("PRESENT_AT_EVENT", "witness", "EVENT")],
    ),
    "BURGLARY": (
        "The complainant {c_title}{complainant} (mobile no. {c_phone}) reported that on {when}, the lock of the "
        "complainant's house near {place}, {city} was found broken and cash and jewellery were missing. The complainant "
        "suspects {suspect}, an employee of {org}, who had visited the house a week earlier for repair work.",
        [("USES_PHONE", "complainant", "c_phone"), ("MEMBER_OF", "suspect", "org")],
    ),
}


@dataclass
class RenderedReport:
    fir_id: str
    file_text: str
    narrative: str
    mentions: list[dict[str, Any]]
    relations: list[dict[str, str]]


def _phone_surface(rng: random.Random, number: str) -> str:
    # Varied formats on purpose, so Phase 2 regex + normalization gets exercised.
    return rng.choice((number, f"{number[:5]} {number[5:]}", f"+91-{number}", f"0{number}", f"+91 {number[:5]} {number[5:]}"))


def _plate_surface(rng: random.Random, plate: str) -> str:
    parts = plate.split("-")
    return rng.choice(("-".join(parts), " ".join(parts), "".join(parts)))


def _entity(rng: random.Random, value: Any) -> tuple[str, NodeType, str, str | None] | None:
    """Return (surface text, node type, expected node id, true_id) for entity slots, None for plain text."""
    if isinstance(value, SynthPerson):
        return value.name, NodeType.PERSON, value.node_id, value.true_id
    if isinstance(value, PhoneRef):
        return _phone_surface(rng, value.number), NodeType.PHONE, make_node_id(NodeType.PHONE, "+91" + value.number), None
    if isinstance(value, Vehicle):
        return _plate_surface(rng, value.plate), NodeType.VEHICLE, value.node_id, None
    if isinstance(value, Place):
        return value.name, NodeType.LOCATION, value.node_id, None
    if isinstance(value, CityRef):
        return value.city, NodeType.LOCATION, make_node_id(NodeType.LOCATION, normalize.location_key(value.city, None)), None
    if isinstance(value, SynthOrg):
        return value.name, NodeType.ORGANIZATION, value.node_id, None
    return None


def _when(s: Scenario) -> str:
    t = s.occurred_at
    return f"{t.day} {t:%B %Y} at about {t:%H:%M} hours"


def render_report(scenario: Scenario, seed: int) -> RenderedReport:
    rng = random.Random(f"{seed}:report:{scenario.key}")
    template, relation_specs = TEMPLATES[scenario.template]
    slots = {**scenario.slots, "when": _when(scenario)}
    surfaces: dict[str, tuple[str, NodeType, str, str | None] | None] = {}  # one surface form per slot per report
    parts: list[str] = []
    mentions: list[dict[str, Any]] = []
    pos = 0
    for literal, field_name, _, _ in Formatter().parse(template):
        parts.append(literal)
        pos += len(literal)
        if field_name is None:
            continue
        if field_name not in surfaces:
            surfaces[field_name] = _entity(rng, slots[field_name])
        entity = surfaces[field_name]
        text = entity[0] if entity else str(slots[field_name])
        if entity:
            node_type = entity[1]
            method = MentionMethod.REGEX if node_type in (NodeType.PHONE, NodeType.VEHICLE) else MentionMethod.SPACY_NER
            # Validate against the Phase 0 contract so annotations can't drift from the schema.
            EntityMention(document_id=scenario.fir_id, node_type=node_type, text=text, start_char=pos,
                          end_char=pos + len(text), method=method)
            mentions.append({"text": text, "node_type": str(node_type), "start": pos, "end": pos + len(text),
                             "expected_method": str(method), "expected_node_id": entity[2], "true_id": entity[3]})
        parts.append(text)
        pos += len(text)
    narrative = "".join(parts)

    event_id = make_node_id(NodeType.EVENT, normalize.text_key(scenario.fir_id))
    relations = [
        {"type": edge_type, "source": surfaces[src][2], "target": event_id if dst == "EVENT" else surfaces[dst][2]}
        for edge_type, src, dst in relation_specs
    ]
    header = [
        SYNTHETIC_BANNER,
        f"FIR No: {scenario.fir_id}",
        f"Police Station: {scenario.police_station}, {scenario.city}",
        f"Date and Time of Report: {scenario.reported_at.isoformat()}",
        f"Date and Time of Occurrence: {scenario.occurred_at.isoformat()}",
        f"Acts and Sections: {scenario.sections}",
        f"Investigating Officer: {scenario.officer}",
    ]
    file_text = "\n".join([*header, "", NARRATIVE_MARKER, narrative, ""])
    return RenderedReport(scenario.fir_id, file_text, narrative, mentions, relations)


def parse_narrative(file_text: str) -> str:
    """The single line after the NARRATIVE marker. Mention offsets are relative to this string."""
    lines = file_text.splitlines()
    return lines[lines.index(NARRATIVE_MARKER) + 1]
