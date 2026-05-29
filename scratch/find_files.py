import os
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
for root, dirs, files in os.walk(base_dir):
    for f in files:
        if "BCD" in f.upper() or "LALRUATTL" in f.upper() or "00149" in f or "00151" in f:
            print(os.path.join(root, f))
