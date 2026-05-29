import sys
import os
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import parse_tma

with open(base_dir / "scratch/swapna_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

rows = parse_tma(text)
print("\nFinal rows:")
for r in rows:
    print(r)
