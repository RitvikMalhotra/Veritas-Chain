"""Incident scenarios: who was where and when. Each scenario becomes one incident-register row and one FIR."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from veritas.synth import catalog
from veritas.synth.catalog import WINDOW_START
from veritas.synth.world import Place, SynthPerson, World

SPIKE_BEFORE = timedelta(hours=48)  # planted call spike starts this long before the incident
SPIKE_AFTER = timedelta(hours=12)
SPIKE_FACTOR = 5.0  # call rate multiplier inside the spike window


@dataclass(frozen=True)
class PhoneRef:
    number: str  # 10-digit


@dataclass(frozen=True)
class CityRef:
    city: str


@dataclass
class Payment:
    from_account: str  # account node id
    to_account: str
    amount: Decimal
    at: datetime
    mode: str


@dataclass
class Scenario:
    key: str  # e.g. "A1", "N07"
    template: str
    city: str
    cluster: str | None
    event_type: str
    sections: str
    occurred_at: datetime
    place: Place
    slots: dict[str, Any]  # template slot -> SynthPerson | Vehicle | Place | SynthOrg | PhoneRef | CityRef | str
    spike_ids: list[str] = field(default_factory=list)  # empty means no planted spike
    scripted_calls: list[tuple[str, str, datetime, int]] = field(default_factory=list)  # (from, to, time, seconds)
    payments: list[Payment] = field(default_factory=list)  # matching bank records
    reported_at: datetime | None = None
    police_station: str = ""
    officer: str = ""
    fir_id: str = ""

    @property
    def spike_window(self) -> tuple[datetime, datetime] | None:
        return (self.occurred_at - SPIKE_BEFORE, self.occurred_at + SPIKE_AFTER) if self.spike_ids else None


def inr(amount) -> str:
    """Indian digit grouping: 120000 -> '1,20,000'."""
    digits = str(int(amount))
    head, groups = digits[:-3], [digits[-3:]]
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(groups)


def _at(rng: random.Random, day_lo: int, day_hi: int, hour_lo: int, hour_hi: int) -> datetime:
    return WINDOW_START + timedelta(days=rng.randint(day_lo, day_hi), hours=rng.randint(hour_lo, hour_hi),
                                    minutes=rng.randrange(60))


def _vehicle_slots(prefix: str, vehicle) -> dict[str, Any]:
    return {prefix: vehicle, f"{prefix}_model": vehicle.make_model, f"{prefix}_color": vehicle.color}


class _Picker:
    """Hands out noise people for complainant roles without reusing anyone."""

    def __init__(self, world: World, rng: random.Random):
        self.world, self.rng, self.used = world, rng, set()

    def take(self, city: str, need=lambda p: True, forced: SynthPerson | None = None) -> SynthPerson:
        if forced is not None:
            self.used.add(forced.true_id)
            return forced
        pool = [p for p in self.world.noise(city) if "isolated" not in p.tags and p.true_id not in self.used
                and p.name != catalog.COLLISION_NAME and need(p)]
        if not pool:
            raise RuntimeError(f"no noise person left in {city} for this role")
        chosen = self.rng.choice(pool)
        self.used.add(chosen.true_id)
        return chosen


def build_scenarios(world: World) -> list[Scenario]:
    rng = random.Random(f"{world.seed}:scenarios")
    pick = _Picker(world, rng)
    P = world.persons
    A, B, C, D = (world.clusters[k] for k in "ABCD")
    bridge1, bridge2 = (P[i] for i in world.bridge_ids)
    out: list[Scenario] = []

    def noise_place(city: str) -> Place:
        return rng.choice(world.noise_places[city])

    # ---- Cluster A: drug distribution, Mumbai ----
    a_leader, a_lt = P[A.leader], P[A.lieutenants[0]]
    a_others = [P[m] for m in A.members if P[m].name != catalog.COLLISION_NAME]
    a_collision = next(P[m] for m in A.members if P[m].name == catalog.COLLISION_NAME)
    acc1, acc2 = a_others[0], a_others[1]
    t = _at(rng, 12, 38, 21, 23)
    out.append(Scenario(
        "A1", "A_RAID", "Mumbai", "A", "drug seizure", "NDPS Act 1985 s.8(c), 21, 29", t, A.meeting_places[0],
        {"acc1": acc1, "acc2": acc2, "leader": a_leader, "lt": a_lt, "leader_phone": PhoneRef(a_leader.phones[0]),
         "owner": bridge1, "place": A.meeting_places[0], "city": CityRef("Mumbai"),
         "meet_place": A.meeting_places[1], "meet_city": CityRef("Mumbai"), **_vehicle_slots("veh", bridge1.vehicles[0])},
        spike_ids=[acc1.true_id, acc2.true_id, a_leader.true_id, *A.lieutenants, bridge1.true_id],
    ))
    a2_partner = a_others[2]
    t = _at(rng, 50, 80, 18, 22)
    a2_place = noise_place("Mumbai")
    out.append(Scenario(
        "A2", "A_PATROL", "Mumbai", "A", "drug seizure", "NDPS Act 1985 s.8(c), 22", t, a2_place,
        {"acc1": a_collision, "acc2": a2_partner, "acc2_phone": PhoneRef(a2_partner.phones[0]),
         "lt": P[A.lieutenants[-1]], "leader": a_leader, "place": a2_place, "city": CityRef("Mumbai")},
        spike_ids=[a_collision.true_id, a2_partner.true_id, A.lieutenants[-1], a_leader.true_id],
    ))

    # ---- Cluster B: vehicle theft, Pune ----
    b_leader, b_lt = P[B.leader], P[B.lieutenants[0]]
    b1, b2, b3 = (P[m] for m in B.members[:3])
    victim = pick.take("Pune", lambda p: any(v.make_model in catalog.CARS for v in p.vehicles))
    stolen_car = next(v for v in victim.vehicles if v.make_model in catalog.CARS)
    t = _at(rng, 12, 38, 1, 4)
    b1_place = noise_place("Pune")
    out.append(Scenario(
        "B1", "B_THEFT", "Pune", "B", "vehicle theft", "BNS 2023 s.303(2), 3(5)", t, b1_place,
        {"complainant": victim, "c_title": "Shri " if victim.gender == "M" else "Smt. ",
         "c_phone": PhoneRef(victim.phones[0]), **_vehicle_slots("cveh", stolen_car),
         "b1": b1, "b2": b2, "leader": b_leader, "place": b1_place, "city": CityRef("Pune"),
         **_vehicle_slots("veh", bridge1.vehicles[0])},
        spike_ids=[b1.true_id, b2.true_id, b_leader.true_id, *B.lieutenants, bridge1.true_id],
    ))
    bike_owner = pick.take("Pune", lambda p: any(v.make_model in catalog.BIKES for v in p.vehicles))
    stolen_bike = next(v for v in bike_owner.vehicles if v.make_model in catalog.BIKES)
    t = _at(rng, 50, 80, 11, 16)
    out.append(Scenario(
        "B2", "B_GARAGE", "Pune", "B", "stolen vehicle recovery", "BNS 2023 s.303(2), 317(2), 3(5)", t,
        B.meeting_places[0],
        {"b1": b1, "b2": b2, "b3": b3, "leader": b_leader, "lt": b_lt, "lt_phone": PhoneRef(b_lt.phones[0]),
         "bridge2": bridge2, "bridge2_city": CityRef(bridge2.city), "stolen": stolen_bike,
         "place": B.meeting_places[0], "city": CityRef("Pune")},
        spike_ids=[b1.true_id, b2.true_id, b3.true_id, b_leader.true_id, *B.lieutenants],
    ))

    # ---- Cluster C: online fraud, Hyderabad ----
    c_leader = P[C.leader]
    mule1, mule2 = P[C.members[0]], P[C.members[1]]
    front = world.orgs[C.front_org]
    callers = [P[m] for m in C.members[2:]] + [P[i] for i in C.lieutenants]
    for key, city, caller in (("C1", "Hyderabad", callers[0]), ("C2", "Mumbai", callers[-1])):
        # Individuals only: a merchant victim also receives cluster spending, which closes unplanted money cycles.
        victim = pick.take(city, lambda p: p.account is not None and "individual" in p.tags)
        t = _at(rng, 5, 80, 10, 18)
        n_txn = rng.randint(1, 3)
        amounts = [Decimal(rng.randrange(15000, 70000, 500)) for _ in range(n_txn)]
        payments = [Payment(victim.account.node_id, mule1.account.node_id, amt,
                            t + timedelta(minutes=12 + 9 * i + rng.randrange(5)), "IMPS")
                    for i, amt in enumerate(amounts)]
        home = noise_place(city)
        out.append(Scenario(
            key, "C_COMPLAINT", city, "C", "online fraud", "BNS 2023 s.318(4), 319(2); IT Act 2000 s.66D", t, home,
            {"complainant": victim, "c_title": "Shri " if victim.gender == "M" else "Smt. ",
             "c_phone": PhoneRef(victim.phones[0]), "fraud_phone": PhoneRef(caller.phones[0]),
             "amount": inr(sum(amounts)), "n_txn": "a single transaction" if n_txn == 1 else f"{n_txn} transactions", "place": home, "city": CityRef(city)},
            scripted_calls=[(caller.phones[0], victim.phones[0], t, rng.randint(420, 900))],
            payments=payments,
        ))
    raided = [p for p in callers + [mule1] if p is not mule2][:3]
    t = _at(rng, 20, 75, 11, 15)
    out.append(Scenario(
        "C3", "C_RAID", "Hyderabad", "C", "fraud call centre raid", "BNS 2023 s.318(4), 319(2), 61(2); IT Act 2000 s.66D",
        t, C.meeting_places[0],
        {"c1": raided[0], "c2": raided[1], "c3": raided[2], "mule2": mule2, "front": front, "leader": c_leader,
         "leader_phone": PhoneRef(c_leader.phones[0]), "place": C.meeting_places[0], "city": CityRef("Hyderabad")},
        spike_ids=[*(p.true_id for p in raided), mule2.true_id, c_leader.true_id, *C.lieutenants],
    ))

    # ---- Cluster D: extortion, Delhi ----
    d_leader, d_lt = P[D.leader], P[D.lieutenants[0]]
    collector = P[D.members[0]]
    bike = collector.vehicles[0]
    d_male = [P[i] for i in [*D.members[1:], *D.lieutenants] if P[i].gender == "M"] or [d_leader]
    caller = d_male[0]
    shop1 = pick.take("Delhi", lambda p: "merchant" in p.tags)
    t = _at(rng, 5, 30, 17, 20)
    shop1_place = noise_place("Delhi")
    threat_calls = [(caller.phones[0], shop1.phones[0], t - timedelta(hours=h, minutes=rng.randrange(60)),
                     rng.randint(40, 150)) for h in (44, 26, 5)]
    out.append(Scenario(
        "D1", "D_COMPLAINT", "Delhi", "D", "extortion", "BNS 2023 s.308(2), 351(2)", t, shop1_place,
        {"complainant": shop1, "c_title": "Shri " if shop1.gender == "M" else "Smt. ",
         "c_phone": PhoneRef(shop1.phones[0]), "ext_phone": PhoneRef(caller.phones[0]), "caller": caller,
         "collector": collector, **_vehicle_slots("veh", bike), "place": shop1_place, "city": CityRef("Delhi")},
        scripted_calls=threat_calls,
    ))
    d2_partner = P[D.members[1]]
    shop2 = pick.take("Delhi", lambda p: "merchant" in p.tags)
    t = _at(rng, 40, 60, 12, 16)
    shop2_place = noise_place("Delhi")
    out.append(Scenario(
        "D2", "D_VANDALISM", "Delhi", "D", "extortion and mischief", "BNS 2023 s.308(2), 324(4), 351(3), 3(5)", t,
        shop2_place,
        {"d1": collector, "d2": d2_partner, **_vehicle_slots("veh", bike), "complainant": shop2,
         "c_title": "Shri " if shop2.gender == "M" else "Smt. ", "leader": d_leader, "lt": d_lt,
         "leader_phone": PhoneRef(d_leader.phones[0]), "meet_place": D.meeting_places[0],
         "meet_city": CityRef("Delhi"), "place": shop2_place, "city": CityRef("Delhi")},
        spike_ids=[collector.true_id, d2_partner.true_id, d_leader.true_id, *D.lieutenants],
    ))
    shop3 = pick.take("Delhi", lambda p: "merchant" in p.tags and p.account is not None)
    d3_lt = P[D.lieutenants[-1]]
    t = _at(rng, 66, 84, 11, 19)
    market = noise_place("Delhi")
    out.append(Scenario(
        "D3", "D_DEMAND", "Delhi", "D", "extortion", "BNS 2023 s.308(2)", t, market,
        {"complainant": shop3, "c_title": "Shri " if shop3.gender == "M" else "Smt. ",
         "c_phone": PhoneRef(shop3.phones[0]), "lt": d3_lt, "lt_phone": PhoneRef(d3_lt.phones[0]),
         "leader": d_leader, "place": market, "city": CityRef("Delhi")},
        scripted_calls=[(d3_lt.phones[0], shop3.phones[0], t, rng.randint(60, 200))],
        payments=[Payment(shop3.account.node_id, collector.account.node_id, Decimal(25000),
                          t + timedelta(hours=rng.randint(2, 6)), "UPI")],
    ))

    # ---- Background incidents unrelated to any cluster ----
    delhi_rahul = next(P[i] for i in world.collision_ids if P[i].role == "noise")
    background = (
        ("SNATCH", "Mumbai", None), ("PHONE_THEFT", "Delhi", delhi_rahul), ("ACCIDENT", "Pune", None),
        ("ONLINE_CHEAT", "Bengaluru", None), ("DISPUTE", "Hyderabad", None), ("BURGLARY", "Delhi", None),
        ("PHONE_THEFT", "Hyderabad", None), ("SNATCH", "Bengaluru", None), ("DISPUTE", "Mumbai", None),
        ("ACCIDENT", "Delhi", None), ("ONLINE_CHEAT", "Pune", None), ("BURGLARY", "Bengaluru", None),
        ("DISPUTE", "Pune", None), ("PHONE_THEFT", "Mumbai", None),
    )
    sections = {
        "SNATCH": ("chain snatching", "BNS 2023 s.304(2)"),
        "PHONE_THEFT": ("mobile phone theft", "BNS 2023 s.303(2)"),
        "ACCIDENT": ("road accident", "BNS 2023 s.281, 125(a)"),
        "ONLINE_CHEAT": ("online job fraud", "BNS 2023 s.318(4); IT Act 2000 s.66D"),
        "DISPUTE": ("assault", "BNS 2023 s.115(2), 352"),
        "BURGLARY": ("house burglary", "BNS 2023 s.331(4), 305(a)"),
    }
    for n, (template, city, forced) in enumerate(background, start=1):
        t = _at(rng, 2, 87, 7, 21)
        place = noise_place(city)
        complainant = pick.take(city, (lambda p: p.gender == "F") if template == "SNATCH" else (lambda p: True), forced)
        slots: dict[str, Any] = {"complainant": complainant, "c_title": "Shri " if complainant.gender == "M" else "Smt. ",
                                 "c_phone": PhoneRef(complainant.phones[0]), "place": place, "city": CityRef(city)}
        calls: list[tuple[str, str, datetime, int]] = []
        if template == "ACCIDENT":
            pick.used.discard(complainant.true_id)  # accident FIRs name the drivers, not a separate complainant
            driver1 = pick.take(city, lambda p: bool(p.vehicles))
            driver2 = pick.take(city, lambda p: bool(p.vehicles))
            slots = {"driver1": driver1, "d1_phone": PhoneRef(driver1.phones[0]), "driver2": driver2,
                     **_vehicle_slots("veh1", driver1.vehicles[0]), **_vehicle_slots("veh2", driver2.vehicles[0]),
                     "place": place, "city": CityRef(city)}
        elif template == "ONLINE_CHEAT":
            scam_number = world.unregistered_numbers[n % len(world.unregistered_numbers)]
            slots |= {"scam_phone": PhoneRef(scam_number), "amount": inr(rng.randrange(1500, 9000, 100))}
            calls.append((scam_number, complainant.phones[0], t, rng.randint(200, 500)))
        elif template == "DISPUTE":
            slots |= {"accused": pick.take(city), "witness": pick.take(city)}
        elif template == "BURGLARY":
            org = next(o for o in world.orgs.values() if o.city == city and o.front_for is None
                       and o.org_type != "transport company")
            slots |= {"suspect": pick.take(city), "org": org}
        event_type, sec = sections[template]
        out.append(Scenario(f"N{n:02d}", template, city, None, event_type, sec, t, place, slots, scripted_calls=calls))

    # Report times, stations, officers, then FIR numbers in report order per city.
    for s in out:
        delay = timedelta(hours=rng.randint(1, 4)) if s.spike_ids else timedelta(hours=rng.randint(1, 30))
        s.reported_at = s.occurred_at + delay
        s.police_station = f"{rng.choice(catalog.CITIES[s.city].areas)} Police Station"
        s.officer = rng.choice(world.officers[s.city])
    for city, profile in catalog.CITIES.items():
        in_city = sorted((s for s in out if s.city == city), key=lambda s: s.reported_at)
        for seq, s in enumerate(in_city, start=1):
            s.fir_id = f"FIR-{profile.code}-2025-{seq:04d}"
    return sorted(out, key=lambda s: s.fir_id)
