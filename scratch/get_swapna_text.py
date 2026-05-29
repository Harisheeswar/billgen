import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

sys_path = str(base_dir) + os.pathsep + os.environ.get("PATH", "")
env = os.environ.copy()
env["PATH"] = sys_path

from extractor import PDFTOTEXT_EXE

pdf_path = base_dir / "debug_pdfs/Hyderabad_2026-05-23_145602_DR.SWAPNA PRIYA INV.151.pdf_1779965098.pdf"
res = subprocess.run([str(PDFTOTEXT_EXE), '-layout', str(pdf_path), '-'], 
                     capture_output=True, text=True, encoding='utf-8', errors='ignore', env=env)
text = res.stdout

with open(base_dir / "scratch/swapna_text.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("Text layer saved to scratch/swapna_text.txt")
