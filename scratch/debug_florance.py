import sys
import os
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import process_file, ocr_pdf_to_text

pdf_path = base_dir / "debug_pdfs/Guwahati_2026-05-23_162752_DR. FLORANCE.pdf_1779964794.pdf"

# 1. OCR text
text = ocr_pdf_to_text(pdf_path)
with open(base_dir / "scratch/florance_ocr.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("OCR text saved to scratch/florance_ocr.txt")

# 2. Heuristic parsing
rows, source = process_file(pdf_path)
print(f"\nExtracted {len(rows)} rows via {source}:")
for row in rows:
    print(row)
