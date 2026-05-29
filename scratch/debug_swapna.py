import sys
import os
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import process_file, ocr_pdf_to_text, detect_supplier

pdf_path = base_dir / "debug_pdfs/Hyderabad_2026-05-23_145602_DR.SWAPNA PRIYA INV.151.pdf_1779965098.pdf"

# 1. OCR text
text = ocr_pdf_to_text(pdf_path)
with open(base_dir / "scratch/swapna_ocr.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("OCR text saved to scratch/swapna_ocr.txt")

# 2. Heuristic parsing
rows, source = process_file(pdf_path)
print(f"\nExtracted {len(rows)} rows via {source}:")
for row in rows:
    print(row)
