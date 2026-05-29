import os
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
for root, dirs, files in os.walk(base_dir):
    for f in files:
        if "FLORANCE" in f.upper() or "00148" in f:
            print(os.path.join(root, f))
