import re
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
path = base_dir / "scratch/swapna_text.txt"
with open(path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if "523" in line:
            print(f"Line {idx+1}: {line.strip()}")
