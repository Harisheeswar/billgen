import sys
import os
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import process_file

files = [
    ("DR.LALRUATTLUAGA SAILO", base_dir / "debug_pdfs/Guwahati_2026-05-23_164114_DR.LALRUATTLUAGA SAILO.pdf_1779962751.pdf"),
    ("BCD HAIR CLINIC", base_dir / "debug_pdfs/Guwahati_2026-05-25_110936_BCD HAIR CLINIC.pdf_1779962737.pdf"),
    ("DR.SWAPNA PRIYA", base_dir / "debug_pdfs/Hyderabad_2026-05-23_145602_DR.SWAPNA PRIYA INV.151.pdf_1779965098.pdf")
]

for name, pdf_path in files:
    print(f"\n--- Processing {name} ---")
    rows, source = process_file(pdf_path)
    print(f"Extracted {len(rows)} rows via {source}:")
    for row in rows:
        print(row)
