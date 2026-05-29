from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
path = base_dir / "extractor.py"
with open(path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if "% rate" in line or "amt_r / rate" in line or "rate_r > 0" in line:
            print(f"Line {idx+1}: {line.strip()}")
