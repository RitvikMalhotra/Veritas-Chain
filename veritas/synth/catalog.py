"""Fixed lookup tables for the synthetic data generator. Bank names and IFSC prefixes are fictional."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
WINDOW_START = datetime(2025, 1, 1, tzinfo=IST)  # all calls, transfers and incidents fall in this 90-day window
WINDOW_DAYS = 90

COLLISION_NAME = "Rahul Sharma"  # the one planted same-name pair (decision 2)


@dataclass(frozen=True)
class CityProfile:
    name: str
    code: str  # used in FIR numbers
    state_code: str  # vehicle plate prefix
    rto_codes: tuple[str, ...]
    areas: tuple[str, ...]  # police station names


CITIES = {
    "Mumbai": CityProfile("Mumbai", "MUM", "MH", ("01", "02", "03", "47"), ("Kurla", "Andheri", "Govandi", "Malad", "Chembur")),
    "Pune": CityProfile("Pune", "PUN", "MH", ("12", "14"), ("Hadapsar", "Kothrud", "Pimpri", "Yerawada")),
    "Hyderabad": CityProfile("Hyderabad", "HYD", "TS", ("07", "08", "09", "10", "11", "13"), ("Madhapur", "Kukatpally", "Secunderabad", "LB Nagar")),
    "Delhi": CityProfile("Delhi", "DEL", "DL", ("1", "3", "4", "5", "7", "8", "9"), ("Karol Bagh", "Seelampur", "Rohini", "Lajpat Nagar")),
    "Bengaluru": CityProfile("Bengaluru", "BLR", "KA", ("01", "02", "03", "04", "05", "51"), ("Shivajinagar", "Yeshwanthpur", "Jayanagar", "Whitefield")),
}

# (cluster id, theme, home city, place template for its main operating site). Bridges: A<->B and B<->C; D has none.
CLUSTER_SPECS = (
    ("A", "drug distribution", "Mumbai", "{last} Warehouse"),
    ("B", "vehicle theft", "Pune", "{street} Garage"),
    ("C", "online fraud", "Hyderabad", "{street} Business Centre"),
    ("D", "extortion", "Delhi", "{last} Dhaba"),
)

NOISE_PER_CITY = {"Mumbai": 24, "Pune": 20, "Hyderabad": 20, "Delhi": 24, "Bengaluru": 14}

BANKS = (("ZARV", "Aravali Bank"), ("ZKVR", "Kaveri Bank"), ("ZNMD", "Narmada Bank"), ("ZGDV", "Godavari Bank"))

CARS = ("Maruti Suzuki Swift", "Hyundai Creta", "Maruti Suzuki Ertiga", "Toyota Innova Crysta", "Tata Nexon", "Mahindra Scorpio")
BIKES = ("Honda Activa", "Bajaj Pulsar 150", "Hero Splendor Plus", "TVS Apache RTR 160", "Royal Enfield Classic 350")
GOODS = ("Tata Ace", "Mahindra Bolero Pickup", "Ashok Leyland Dost")
COLORS = ("white", "black", "silver", "grey", "red", "blue", "maroon")  # no vowel-initial colours, templates say "a {color}"

PLATE_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"  # I and O are skipped, as on real plates

PLACE_TEMPLATES = (
    "{last} Dhaba", "{street} Garage", "{last} Warehouse", "Hotel {last} Residency",
    "{street} Bus Depot", "{last} Tea Stall", "{last} Auto Works", "{street} Market",
)
ORG_SUFFIXES = ("Trading Pvt Ltd", "Enterprises", "Traders", "Infra Pvt Ltd", "Services Pvt Ltd")
NOISE_ORG_TYPES = ("retail business", "construction firm", "IT services firm", "restaurant", "courier service")

OFFICER_RANKS = ("SI", "PSI", "Inspector")
