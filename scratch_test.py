import sys
import os
from pathlib import Path

sys.path.append(os.path.abspath(r"c:\Users\User\Downloads\billgen"))
from extractor import process_file

pdf_path = Path(r"C:\Users\User\Downloads\billgen\invoices\TMA - Guwahati & Kolkata\Kol & Guw Invoice_Jan_25\INV.A000442.pdf")

print("\n--- EXTRACTION (KOLKATA 442) ---")
rows, source = process_file(pdf_path, original_filename="INV.A000442.pdf")
print(f"Source: {source}")
print(f"Rows found: {len(rows)}")
for r in rows:
    print(r)
