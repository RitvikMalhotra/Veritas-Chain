"""CLI: python -m veritas.synth --seed 42 --out data"""

import argparse
from pathlib import Path

from veritas.synth.generate import generate

parser = argparse.ArgumentParser(description="Generate the synthetic criminal-network dataset.")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--out", type=Path, default=Path("data"))
args = parser.parse_args()

counts = generate(args.seed, args.out)
print(f"Wrote synthetic dataset to {args.out} (seed {args.seed})")
for name, value in counts.items():
    print(f"  {name:<14}{value}")
