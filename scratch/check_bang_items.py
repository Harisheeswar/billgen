import os
import re
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
for f in ["debug_484_bangalore.txt", "debug_871_bang_ocr.txt", "debug_484_ocr.txt"]:
    path = base_dir / f
    if path.exists():
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            content = file.read()
            matches = re.findall(r'Total\s*Item[s]?(?:\s*[:-]+)?\s*\d+', content, re.I)
            print(f"{f}: {matches}")
