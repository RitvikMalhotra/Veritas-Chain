"""Call records (with planted spikes) and bank transactions (with a planted cycle and a decoy)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import combinations

from veritas.synth.catalog import WINDOW_DAYS, WINDOW_START
from veritas.synth.scenarios import SPIKE_FACTOR, Scenario
from veritas.synth.world import SynthPerson, World

WINDOW_END = WINDOW_START + timedelta(days=WINDOW_DAYS)
BLOCK = timedelta(hours=6)
# Share of a contact's daily calls in each 6-hour block (00-06, 06-12, 12-18, 18-24).
BLOCK_WEIGHTS = {"cluster": (0.15, 0.2, 0.25, 0.4), "social": (0.03, 0.3, 0.32, 0.35), "service": (0.0, 0.45, 0.45, 0.1)}


@dataclass
class Contact:
    a: str  # true_id, or "UNREG" for numbers with no subscriber record
    b: str
    a_phone: str
    b_phone: str
    rate: float  # expected calls per day
    a_share: float  # fraction of calls placed by a
    profile: str


@dataclass
class Call:
    at: datetime
    caller: str  # 10-digit
    callee: str
    seconds: int
    kind: str  # voice | sms


@dataclass
class Txn:
    at: datetime
    from_account: str  # account node id
    to_account: str
    amount: Decimal
    mode: str
    tag: str  # generator-internal label, only surfaces in ground truth


def _poisson(rng: random.Random, lam: float) -> int:
    # Knuth's method; fine for the small rates used here.
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


# ---------- Calls ----------


def build_contacts(world: World, rng: random.Random) -> list[Contact]:
    P = world.persons
    contacts: dict[tuple[str, str], Contact] = {}  # keyed by sorted pair, insertion-ordered

    def add(a: SynthPerson, b: SynthPerson, rate: float, profile: str, a_share: float = 0.5,
            a_phone: str | None = None, b_phone: str | None = None) -> None:
        key = tuple(sorted((a.true_id, b.true_id)))
        if key in contacts and contacts[key].rate >= rate:
            return
        contacts[key] = Contact(a.true_id, b.true_id, a_phone or a.phones[0], b_phone or b.phones[0], rate, a_share, profile)

    def noise_contacts(p: SynthPerson, k_lo: int, k_hi: int) -> None:
        pool = [n for n in world.noise(p.city) if "isolated" not in n.tags]
        for n in rng.sample(pool, rng.randint(k_lo, k_hi)):  # family, shops, friends in the same city
            add(p, n, rng.uniform(0.05, 0.25), "social")

    for cluster in world.clusters.values():
        leader = P[cluster.leader]
        lieutenants = [P[i] for i in cluster.lieutenants]
        members = [P[i] for i in cluster.members]
        for lt in lieutenants:
            # A's leader uses the second SIM only with lieutenants.
            leader_phone = leader.phones[1] if "second_sim" in leader.tags else leader.phones[0]
            add(leader, lt, 0.6, "cluster", 0.55, a_phone=leader_phone)
        for x, y in combinations(lieutenants, 2):
            add(x, y, 0.3, "cluster")
        for m in members:
            add(m, P[m.reports_to], 0.4, "cluster", 0.7)  # members mostly call their lieutenant
            if rng.random() < 0.4:
                add(leader, m, 0.15, "cluster", 0.3)
        for x, y in combinations(members, 2):
            if x.reports_to == y.reports_to and rng.random() < 0.5:
                add(x, y, 0.15, "cluster")
        for p in (leader, *lieutenants, *members):
            noise_contacts(p, 2, 4)

    A, B, C = (world.clusters[k] for k in "ABC")
    bridge1, bridge2 = (P[i] for i in world.bridge_ids)
    add(bridge1, P[A.lieutenants[0]], 0.3, "cluster")
    add(bridge1, P[B.leader], 0.3, "cluster")
    add(bridge1, P[rng.choice(A.members[1:])], 0.08, "cluster")  # skip A.members[0], the collision person
    add(bridge1, P[rng.choice(B.members)], 0.08, "cluster")
    add(bridge2, P[B.lieutenants[0]], 0.3, "cluster")
    add(bridge2, P[C.leader], 0.3, "cluster")
    add(bridge2, P[C.members[1]], 0.1, "cluster")
    for bridge in (bridge1, bridge2):
        noise_contacts(bridge, 2, 2)

    all_noise = [p for p in world.noise() if "isolated" not in p.tags]
    for city in world.noise_places:
        people = [p for p in all_noise if p.city == city]
        rng.shuffle(people)
        i = 0
        while i < len(people):  # split into social circles of 3-7 people
            circle = people[i:i + rng.randint(3, 7)]
            i += len(circle)
            for x, y in combinations(circle, 2):
                if rng.random() < 0.7:
                    add(x, y, rng.uniform(0.08, 0.45), "social")
        for p in people:
            add(p, rng.choice([q for q in people if q is not p]), rng.uniform(0.02, 0.08), "social")
    for _ in range(10):
        x, y = rng.sample(all_noise, 2)
        if x.city != y.city:
            add(x, y, rng.uniform(0.02, 0.06), "social")

    callers = [p for p in P.values() if "isolated" not in p.tags]
    for number in world.unregistered_numbers:  # delivery, bank, cab numbers with no subscriber record
        for p in rng.sample(callers, rng.randint(4, 8)):
            key = (p.true_id, f"UNREG:{number}")
            contacts[key] = Contact(p.true_id, "UNREG", p.phones[0], number, rng.uniform(0.02, 0.06), 1.0, "service")
    return list(contacts.values())


def generate_calls(world: World, scenarios: list[Scenario]) -> list[Call]:
    rng = random.Random(f"{world.seed}:calls")
    contacts = build_contacts(world, rng)
    spikes = [(set(s.spike_ids), *s.spike_window) for s in scenarios if s.spike_ids]
    calls: list[Call] = []
    for c in contacts:
        windows = [(lo, hi) for ids, lo, hi in spikes if c.a in ids and c.b in ids]
        weights = BLOCK_WEIGHTS[c.profile]
        start = WINDOW_START
        while start < WINDOW_END:
            factor = SPIKE_FACTOR if any(start < hi and start + BLOCK > lo for lo, hi in windows) else 1.0
            block_index = start.hour // 6
            for _ in range(_poisson(rng, c.rate * weights[block_index] * factor)):
                at = start + timedelta(seconds=rng.randrange(int(BLOCK.total_seconds())))
                a_calls = rng.random() < c.a_share
                caller, callee = (c.a_phone, c.b_phone) if a_calls else (c.b_phone, c.a_phone)
                if rng.random() < 0.15:
                    calls.append(Call(at, caller, callee, 0, "sms"))
                else:
                    seconds = int(min(1800, max(5, rng.lognormvariate(math.log(60), 0.9))))
                    calls.append(Call(at, caller, callee, seconds, "voice"))
            start += BLOCK
    for s in scenarios:
        calls.extend(Call(at, frm, to, secs, "voice") for frm, to, at, secs in s.scripted_calls)
    calls.sort(key=lambda call: (call.at, call.caller, call.callee))
    return calls


# ---------- Transactions ----------


def _mode(rng: random.Random, amount: Decimal) -> str:
    # Mirrors Indian rails: UPI up to 1 lakh, RTGS for 2 lakh and above.
    if amount >= 200_000:
        return rng.choice(("RTGS", "NEFT"))
    if amount > 100_000:
        return rng.choice(("IMPS", "NEFT"))
    return rng.choice(("UPI", "UPI", "IMPS"))


def _rupees(value: float, step: int = 1) -> Decimal:
    return Decimal(max(step, int(round(value / step)) * step))


def generate_transactions(world: World, scenarios: list[Scenario]) -> list[Txn]:
    rng = random.Random(f"{world.seed}:transactions")
    P = world.persons
    txns: list[Txn] = []

    def pay(frm, to, amount: Decimal, at: datetime, tag: str, mode: str | None = None) -> None:
        if WINDOW_START <= at < WINDOW_END:
            txns.append(Txn(at, frm.node_id, to.node_id, amount, mode or _mode(rng, amount), tag))

    def day(d: float, hour_lo: int = 8, hour_hi: int = 22) -> datetime:
        return WINDOW_START + timedelta(days=int(d), hours=rng.randint(hour_lo, hour_hi), minutes=rng.randrange(60))

    merchants = {city: world.noise(city, "merchant") for city in world.noise_places}
    # The shopkeepers named in D's reports pay extortion over UPI. They never receive cluster spending,
    # otherwise shop -> collector -> leader -> shop would be an unplanted cycle.
    D = world.clusters["D"]
    extortion_shops = list({s.slots["complainant"].true_id: s.slots["complainant"] for s in scenarios if s.cluster == "D"}.values())
    extortion_payer_ids = {p.true_id for p in extortion_shops}
    clean_merchants = {city: [m for m in ms if m.true_id not in extortion_payer_ids] for city, ms in merchants.items()}

    # Decoy: a 3-cycle among Bengaluru friends whose dates run backwards around the loop and whose amounts differ widely.
    x, y, z = world.noise("Bengaluru", "individual", with_account=True)[:3]
    decoy = [(x, y, _rupees(rng.uniform(2000, 3000), 50), day(61)), (y, z, _rupees(rng.uniform(15000, 20000), 500), day(33)),
             (z, x, _rupees(rng.uniform(500, 900), 10), day(9))]
    for frm, to, amt, at in decoy:
        pay(frm.account, to.account, amt, at, "decoy_cycle")
    reserved = {x.true_id, y.true_id, z.true_id}
    free_individuals = [p for p in world.noise(tag="individual", with_account=True) if p.true_id not in reserved]

    # Background: individuals pay merchants, companies pay salaries, friends repay loans (2-cycles only).
    for p in free_individuals:
        for month in range(3):
            for _ in range(rng.randint(2, 4)):
                pay(p.account, rng.choice(merchants[p.city]).account, _rupees(rng.lognormvariate(math.log(1500), 0.8), 10),
                    day(month * 30 + rng.randrange(30)), "retail")
    free_ids = {p.true_id for p in free_individuals}
    for org in world.orgs.values():
        # Salaries go to the employees named in reports ("who works at ..."), so text and bank data agree.
        for p in (P[i] for i in org.employees if i in free_ids):
            salary = _rupees(rng.uniform(18000, 65000), 500)
            for month in range(3):
                pay(org.account, p.account, salary, day(month * 30 + rng.randrange(3), 9, 12), "salary", "NEFT")
    for city in world.noise_places:
        pool = [p for p in free_individuals if p.city == city]
        people = rng.sample(pool, min(6, len(pool) // 2 * 2))
        for lender, borrower in zip(people[0::2], people[1::2]):  # disjoint pairs, so loans never chain into a longer cycle
            amount, lent_on = _rupees(rng.uniform(1000, 20000), 100), rng.randrange(0, 60)
            pay(lender.account, borrower.account, amount, day(lent_on), "loan")
            pay(borrower.account, lender.account, amount, day(lent_on + rng.randint(5, 25)), "loan_repayment")

    # Cluster members and bridges also spend normally, which hides their money flows among ordinary ones.
    active = [P[i] for c in world.clusters.values() for i in c.everyone] + [P[i] for i in world.bridge_ids]
    for p in active:
        if p.account:
            for _ in range(rng.randint(3, 6)):
                pay(p.account, rng.choice(clean_merchants[p.city]).account, _rupees(rng.uniform(2000, 25000), 100),
                    day(rng.randrange(WINDOW_DAYS)), "spending")

    # A (drugs): buyers -> street members -> lieutenant -> leader. Fan-in, no cycle.
    A = world.clusters["A"]
    a_sellers = [P[m] for m in A.members if P[m].account] or [P[A.lieutenants[0]]]
    buyers = [p for p in free_individuals if p.city == "Mumbai"][:6]
    for buyer in buyers:
        for _ in range(rng.randint(3, 6)):
            pay(buyer.account, rng.choice(a_sellers).account, _rupees(rng.uniform(1500, 6000), 100),
                day(rng.randrange(WINDOW_DAYS), 18, 23), "A_sale")
    for seller in a_sellers:
        lt = P[seller.reports_to] if seller.reports_to in A.lieutenants else P[A.lieutenants[0]]
        for d in range(rng.randint(3, 9), WINDOW_DAYS, rng.randint(8, 12)):
            if seller is not lt:
                pay(seller.account, lt.account, _rupees(rng.uniform(15000, 40000), 500), day(d), "A_upstream")
    for lt in (P[i] for i in A.lieutenants):
        for d in range(rng.randint(10, 16), WINDOW_DAYS, 14):
            pay(lt.account, P[A.leader].account, _rupees(rng.uniform(50000, 120000), 1000), day(d), "A_upstream")

    # B -> bridge2 -> C's front company: theft proceeds laundered through the fraud cluster. Linear, no cycle.
    B, C = world.clusters["B"], world.clusters["C"]
    bridge2 = P[world.bridge_ids[1]]
    front = world.orgs[C.front_org]
    for d in (rng.randint(8, 20), rng.randint(35, 50), rng.randint(62, 75)):
        amount = _rupees(rng.uniform(200000, 400000), 5000)
        pay(P[B.leader].account, bridge2.account, amount, day(d), "B_to_bridge2")
        pay(bridge2.account, front.account, _rupees(float(amount) * rng.uniform(0.88, 0.92), 1000),
            day(d + rng.randint(1, 3)), "bridge2_to_C_front")

    # C (fraud): victim money moves mule1 -> mule2 -> front company, the same direction as the planted cycle.
    mule1, mule2 = P[C.members[0]], P[C.members[1]]
    fraud_payments = [pm for s in scenarios if s.cluster == "C" for pm in s.payments]
    extra_victims = [p for p in free_individuals if p.city in ("Hyderabad", "Bengaluru", "Pune")][:5]
    for victim in extra_victims:
        at = day(rng.randrange(WINDOW_DAYS - 3), 10, 18)
        amount = _rupees(rng.uniform(20000, 150000), 500)
        pay(victim.account, mule1.account, amount, at, "C_victim")
    for pm in fraud_payments:
        txns.append(Txn(pm.at, pm.from_account, pm.to_account, pm.amount, pm.mode, "C_victim_reported"))
    victim_inflows = [t for t in txns if t.tag in ("C_victim", "C_victim_reported")]
    for t in victim_inflows:
        hop1 = t.at + timedelta(hours=rng.randint(3, 20))
        a1 = _rupees(float(t.amount) * rng.uniform(0.96, 0.98), 100)
        pay(mule1.account, mule2.account, a1, hop1, "C_layering")
        pay(mule2.account, front.account, _rupees(float(a1) * rng.uniform(0.96, 0.98), 100),
            hop1 + timedelta(hours=rng.randint(3, 20)), "C_layering")

    # Planted cycle, two rounds: C leader -> mule1 -> mule2 -> front company -> C leader, each hop later and slightly smaller.
    chain = [P[C.leader].account, mule1.account, mule2.account, front.account, P[C.leader].account]
    for round_no, start_day in enumerate((rng.uniform(15, 30), rng.uniform(55, 70)), start=1):
        at = WINDOW_START + timedelta(days=start_day, hours=rng.randint(10, 16))
        amount = _rupees(rng.uniform(400000, 650000), 5000)
        for hop in range(4):
            pay(chain[hop], chain[hop + 1], amount, at, f"planted_cycle:{round_no}:{hop + 1}")
            at += timedelta(hours=rng.randint(14, 44))
            amount = _rupees(float(amount) * rng.uniform(0.96, 0.98), 100)

    # D (extortion): shopkeepers pay the collector over UPI; the collector passes money to the leader. No cycle.
    collector = P[D.members[0]]
    for pm in (pm for s in scenarios if s.cluster == "D" for pm in s.payments):
        txns.append(Txn(pm.at, pm.from_account, pm.to_account, pm.amount, pm.mode, "D_extortion_reported"))
    for shop in extortion_shops:
        for _ in range(rng.randint(1, 2)):
            pay(shop.account, collector.account, _rupees(rng.uniform(10000, 50000), 1000),
                day(rng.randrange(WINDOW_DAYS)), "D_extortion")
    for d in range(rng.randint(5, 12), WINDOW_DAYS, rng.randint(10, 15)):
        pay(collector.account, P[D.leader].account, _rupees(rng.uniform(30000, 80000), 1000), day(d), "D_upstream")

    txns.sort(key=lambda t: (t.at, t.from_account, t.to_account))
    return txns
