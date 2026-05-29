import sys
import os
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import ocr_pdf_to_text

pdf_path = base_dir / "debug_pdfs/Guwahati_2026-05-25_110936_BCD HAIR CLINIC.pdf_1779962737.pdf"
text = ocr_pdf_to_text(pdf_path)

with open(base_dir / "scratch/bcd_ocr.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("OCR completed. Saved to scratch/bcd_ocr.txt")
