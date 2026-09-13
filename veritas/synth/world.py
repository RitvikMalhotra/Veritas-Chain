"""Synthetic population: people, phones, bank accounts, vehicles, companies and the planted clusters."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from faker import Faker

from veritas import normalize
from veritas.models import NodeType, make_node_id
from veritas.synth import catalog
from veritas.synth.catalog import IST


@dataclass
class Account:
    ifsc: str
    number: str
    bank_name: str
    holder_id: str  # true_id of a person, or org_id of a company
    holder_name: str
    holder_type: str  # "person" | "organization"
    opened_on: datetime

    @property
    def node_id(self) -> str:
        return make_node_id(NodeType.BANK_ACCOUNT, f"{self.ifsc}:{self.number}")


@dataclass
class Vehicle:
    plate: str  # registry form, e.g. MH-12-AB-1234
    make_model: str
    color: str
    owner_id: str
    owner_name: str
    owner_type: str
    registered_on: datetime

    @property
    def node_id(self) -> str:
        return make_node_id(NodeType.VEHICLE, normalize.plate_key(self.plate))


@dataclass
class Place:
    name: str
    city: str

    @property
    def node_id(self) -> str:
        return make_node_id(NodeType.LOCATION, normalize.location_key(self.name, self.city))


@dataclass
class SynthPerson:
    true_id: str  # ground-truth identity; the pipeline never sees this
    name: str
    gender: str  # "M" | "F"
    city: str
    role: str  # leader | lieutenant | member | bridge | noise
    cluster: str | None = None
    bridges: list[str] | None = None
    tags: list[str] = field(default_factory=list)  # e.g. mule, merchant, isolated, second_sim
    reports_to: str | None = None
    phones: list[str] = field(default_factory=list)  # 10-digit numbers, primary first
    account: Account | None = None
    vehicles: list[Vehicle] = field(default_factory=list)

    @property
    def node_id(self) -> str:
        return make_node_id(NodeType.PERSON, normalize.person_key(self.name))


@dataclass
class SynthOrg:
    org_id: str
    name: str
    org_type: str
    city: str
    directors: list[str]  # true_ids
    appointed_on: datetime
    account: Account | None = None
    front_for: str | None = None  # cluster id when this is a front company

    @property
    def node_id(self) -> str:
        return make_node_id(NodeType.ORGANIZATION, normalize.organization_key(self.name))


@dataclass
class Cluster:
    cluster_id: str
    theme: str
    city: str
    leader: str
    lieutenants: list[str]
    members: list[str]
    meeting_places: list[Place]
    front_org: str | None = None

    @property
    def everyone(self) -> list[str]:
        return [self.leader, *self.lieutenants, *self.members]


@dataclass
class World:
    seed: int
    persons: dict[str, SynthPerson]
    orgs: dict[str, SynthOrg]
    clusters: dict[str, Cluster]
    bridge_ids: list[str]
    noise_places: dict[str, list[Place]]
    officers: dict[str, list[str]]
    unregistered_numbers: list[str]
    collision_ids: list[str]

    def noise(self, city: str | None = None, tag: str | None = None, with_account: bool | None = None) -> list[SynthPerson]:
        # Noise people filtered by city, tag and account ownership, in creation order.
        return [
            p for p in self.persons.values()
            if p.role == "noise"
            and (city is None or p.city == city)
            and (tag is None or tag in p.tags)
            and (with_account is None or (p.account is not None) == with_account)
        ]


class _Builder:
    def __init__(self, seed: int):
        self.rng = random.Random(f"{seed}:world")
        self.fake = Faker("en_IN")
        self.fake.seed_instance(seed)
        # Sets are only used for membership checks, never iterated, so output order stays deterministic.
        self.used_names = {normalize.person_key(catalog.COLLISION_NAME)}  # reserved for the planted pair
        self.used_numbers: set[str] = set()
        self.used_plates: set[str] = set()
        self.used_accounts: set[str] = set()
        self.used_orgs: set[str] = set()
        self.used_places: set[str] = set()
        self.persons: dict[str, SynthPerson] = {}
        self.orgs: dict[str, SynthOrg] = {}

    def date_between(self, start_year: int, end_year: int) -> datetime:
        start = datetime(start_year, 1, 1, tzinfo=IST)
        days = (datetime(end_year, 12, 31, tzinfo=IST) - start).days
        return start + timedelta(days=self.rng.randrange(days), hours=self.rng.randint(10, 17), minutes=self.rng.randrange(60))

    def name(self, gender: str) -> str:
        for _ in range(10_000):
            first = self.fake.first_name_male() if gender == "M" else self.fake.first_name_female()
            name = f"{first} {self.fake.last_name()}"
            key = normalize.person_key(name)
            if key not in self.used_names:  # no accidental collisions besides the planted one
                self.used_names.add(key)
                return name
        raise RuntimeError("Faker name pool exhausted")

    def phone(self) -> str:
        while True:
            number = f"{self.rng.choice('6789')}{self.rng.randrange(10**9):09d}"
            if number not in self.used_numbers:
                self.used_numbers.add(number)
                return number

    def person(self, role: str, city: str, gender: str | None = None, name: str | None = None, **extra) -> SynthPerson:
        gender = gender or self.rng.choice("MF")
        true_id = f"TP-{len(self.persons) + 1:04d}"
        person = SynthPerson(true_id, name or self.name(gender), gender, city, role, **extra)
        person.phones.append(self.phone())
        self.persons[true_id] = person
        return person

    def account(self, holder_id: str, holder_name: str, holder_type: str) -> Account:
        code, bank = self.rng.choice(catalog.BANKS)
        while True:
            ifsc = f"{code}0{self.rng.randrange(10**6):06d}"
            length = self.rng.choice((11, 12, 14, 16))
            number = str(self.rng.randrange(10 ** (length - 1), 10**length))
            if f"{ifsc}:{number}" not in self.used_accounts:
                self.used_accounts.add(f"{ifsc}:{number}")
                return Account(ifsc, number, bank, holder_id, holder_name, holder_type, self.date_between(2012, 2023))

    def give_account(self, person: SynthPerson) -> None:
        person.account = self.account(person.true_id, person.name, "person")

    def vehicle(self, owner_id: str, owner_name: str, owner_type: str, city: str, models: tuple[str, ...]) -> Vehicle:
        profile = catalog.CITIES[city]
        while True:
            series = "".join(self.rng.choice(catalog.PLATE_LETTERS) for _ in range(self.rng.choice((1, 2))))
            if profile.state_code == "DL":
                series = self.rng.choice("CS") + series  # Delhi plates carry a vehicle-class letter
            plate = f"{profile.state_code}-{self.rng.choice(profile.rto_codes)}-{series}-{self.rng.randrange(1, 10000):04d}"
            if normalize.plate_key(plate) not in self.used_plates:
                self.used_plates.add(normalize.plate_key(plate))
                break
        # Registered 2015-2023, so Telangana plates correctly use TS (TG only applies from 2024).
        return Vehicle(plate, self.rng.choice(models), self.rng.choice(catalog.COLORS), owner_id, owner_name,
                       owner_type, self.date_between(2015, 2023))

    def give_vehicle(self, person: SynthPerson, models: tuple[str, ...]) -> Vehicle:
        vehicle = self.vehicle(person.true_id, person.name, "person", person.city, models)
        person.vehicles.append(vehicle)
        return vehicle

    def place(self, city: str, template: str | None = None) -> Place:
        fixed = template
        while True:
            template = fixed or self.rng.choice(catalog.PLACE_TEMPLATES)
            name = template.format(last=self.fake.last_name(), street=self.fake.street_name())
            place = Place(name, city)
            if place.node_id not in self.used_places:
                self.used_places.add(place.node_id)
                return place

    def org(self, city: str, org_type: str, directors: list[SynthPerson], suffix: str | None = None,
            front_for: str | None = None) -> SynthOrg:
        while True:
            name = f"{self.fake.last_name()} {suffix or self.rng.choice(catalog.ORG_SUFFIXES)}"
            if normalize.organization_key(name) not in self.used_orgs:
                self.used_orgs.add(normalize.organization_key(name))
                break
        org_id = f"ORG-{len(self.orgs) + 1:03d}"
        org = SynthOrg(org_id, name, org_type, city, [d.true_id for d in directors], self.date_between(2016, 2023),
                       front_for=front_for)
        org.account = self.account(org_id, name, "organization")
        self.orgs[org_id] = org
        return org

    def cluster_gender(self) -> str:
        return "M" if self.rng.random() < 0.85 else "F"


def build_world(seed: int) -> World:
    b = _Builder(seed)
    clusters: dict[str, Cluster] = {}

    for cid, theme, city, site_template in catalog.CLUSTER_SPECS:
        size = b.rng.randint(6, 10)  # brief allows 5-10; 6 is the minimum the incident scripts need
        n_lieutenants = 2 if size >= 8 else 1
        leader = b.person("leader", city, gender="M", cluster=cid)
        lieutenants = [b.person("lieutenant", city, gender=b.cluster_gender(), cluster=cid, reports_to=leader.true_id)
                       for _ in range(n_lieutenants)]
        members = []
        for i in range(size - 1 - n_lieutenants):
            planted = cid == "A" and i == 0  # cluster A's first member is one half of the name collision
            members.append(b.person(
                "member", city, gender="M" if planted else b.cluster_gender(),
                name=catalog.COLLISION_NAME if planted else None,
                cluster=cid, reports_to=lieutenants[i % n_lieutenants].true_id,
            ))
        for p in (leader, *lieutenants):
            b.give_account(p)
        for m in members:
            if cid in ("C", "D") or b.rng.random() < 0.7:  # C members are all mules; D needs a mule
                b.give_account(m)
        b.give_vehicle(leader, catalog.CARS)
        clusters[cid] = Cluster(cid, theme, city, leader.true_id, [p.true_id for p in lieutenants],
                                [m.true_id for m in members], [b.place(city, site_template), b.place(city)])

    a, bb, c, d = (clusters[k] for k in "ABCD")
    b.persons[a.leader].phones.append(b.phone())  # A's leader keeps a second SIM for lieutenants only
    b.persons[a.leader].tags.append("second_sim")
    b.give_vehicle(b.persons[a.lieutenants[0]], catalog.CARS)
    for member_id in bb.members[:2]:
        b.give_vehicle(b.persons[member_id], catalog.BIKES)
    b.give_vehicle(b.persons[d.members[0]], catalog.BIKES)
    b.persons[d.members[0]].tags.append("mule")
    b.persons[c.members[0]].tags.append("mule")
    b.persons[c.members[1]].tags.extend(["mule", "director"])
    front = b.org("Hyderabad", "front company", [b.persons[c.leader], b.persons[c.members[1]]],
                  suffix="Trading Pvt Ltd", front_for="C")
    c.front_org = front.org_id

    bridge1 = b.person("bridge", "Pune", gender="M", bridges=["A", "B"], tags=["transporter"])
    b.give_account(bridge1)
    b.give_vehicle(bridge1, catalog.GOODS)
    b.org("Pune", "transport company", [bridge1], suffix="Logistics Pvt Ltd")
    bridge2 = b.person("bridge", "Hyderabad", gender="M", bridges=["B", "C"], tags=["money_handler"])
    b.give_account(bridge2)

    noise_places: dict[str, list[Place]] = {}
    officers: dict[str, list[str]] = {}
    for city, count in catalog.NOISE_PER_CITY.items():
        people = []
        for i in range(count):
            planted = city == "Delhi" and i == 0  # the other half of the name collision
            people.append(b.person("noise", city, gender="M" if planted else None,
                                   name=catalog.COLLISION_NAME if planted else None))
        for i, p in enumerate(people):
            if p.name == catalog.COLLISION_NAME:
                p.tags.append("individual")
            elif i % 4 == 3:
                p.tags.append("merchant")
            elif i % 11 == 10:
                p.tags.append("isolated")  # has a SIM but no calls, accounts or reports
            else:
                p.tags.append("individual")
        individuals = [p for p in people if "individual" in p.tags]
        for idx, p in enumerate(individuals):
            # The first few are fixed so every city always has account holders, car owners and bike owners.
            if idx < 4 or b.rng.random() < 0.6:
                b.give_account(p)
            if idx % 3 == 0:
                b.give_vehicle(p, catalog.CARS if idx % 6 == 0 else catalog.BIKES)
        for p in people:
            if "merchant" in p.tags:
                b.give_account(p)
                if b.rng.random() < 0.4:
                    b.give_vehicle(p, catalog.GOODS)
        for _ in range(2):
            directors = b.rng.sample(individuals, b.rng.choice((1, 2)))
            b.org(city, b.rng.choice(catalog.NOISE_ORG_TYPES), directors)
        noise_places[city] = [b.place(city) for _ in range(8)]
        officers[city] = [f"{b.rng.choice(catalog.OFFICER_RANKS)} {b.name(b.rng.choice('MF'))}" for _ in range(2)]

    collision_ids = [p.true_id for p in b.persons.values() if p.name == catalog.COLLISION_NAME]
    return World(
        seed=seed,
        persons=b.persons,
        orgs=b.orgs,
        clusters=clusters,
        bridge_ids=[bridge1.true_id, bridge2.true_id],
        noise_places=noise_places,
        officers=officers,
        unregistered_numbers=[b.phone() for _ in range(15)],
        collision_ids=collision_ids,
    )
