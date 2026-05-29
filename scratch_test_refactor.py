import os
from extractor import process_file

# Sample files to test
test_files = [
    r"c:\Users\User\Downloads\billgen\invoices\TMA - Bangalore\INV.466 - Copy.pdf",
    r"c:\Users\User\Downloads\billgen\invoices\TMA - Guwahati & Kolkata\INV.347.pdf"
]

for f in test_files:
    if os.path.exists(f):
        print(f"Testing: {f}")
        rows, source = process_file(f)
        print(f"  Source: {source}")
        print(f"  Rows found: {len(rows)}")
        if rows:
            print(f"  First row: {rows[0]}")
    else:
        print(f"File not found: {f}")
