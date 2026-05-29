import sys
import os
import re
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import clean_lines, num

with open(base_dir / "scratch/swapna_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

lines = clean_lines(text)
print(f"Total lines: {len(lines)}")

for i, line in enumerate(lines):
    line = line.strip()
    tokens = [t.strip() for t in line.split('|' if '|' in line else ' ') if t.strip()]
    if len(tokens) >= 6:
        # Find how many numeric tokens are at the end
        num_end = 0
        for k in range(len(tokens)-1, -1, -1):
            t = tokens[k]
            if re.match(r'^[\d.,%]+$', t):
                num_end += 1
            else:
                break
                
        if num_end >= 2:
            amt = num(tokens[-1])
            rate = num(tokens[-2])
            gst = 0
            
            date_idx = len(tokens) - num_end - 1
            if date_idx >= 0 and re.match(r'^\d{1,2}/\d{2,4}$', tokens[date_idx]):
                if num_end >= 4:
                    gst = num(tokens[-num_end])
                left_tokens = tokens[:date_idx]
            else:
                if num_end >= 3:
                    gst = num(tokens[-num_end])
                left_tokens = tokens[:len(tokens) - num_end]
                
            if amt > 0 and rate > 0 and amt < 1000000:
                print(f"\nLine {i+1}: {line}")
                print(f"tokens: {tokens}")
                print(f"num_end: {num_end}, date_idx: {date_idx if 'date_idx' in locals() else 'N/A'}")
                print(f"left_tokens: {left_tokens}")
                print(f"amt: {amt}, rate: {rate}, gst: {gst}")
                
                # Check expected qty
                taxable_amt = amt / (1 + gst / 100.0) if gst > 0 else amt
                expected_qty = round(taxable_amt / rate, 0)
                print(f"taxable_amt: {taxable_amt}, expected_qty: {expected_qty}")
                
                qty_idx = -1
                if expected_qty > 0:
                    for k in range(min(6, len(left_tokens))):
                        if num(left_tokens[k]) == expected_qty:
                            qty_idx = k
                            print(f"Found expected_qty at index {k}")
                            break
                            
                if qty_idx == -1:
                    for k in range(min(4, len(left_tokens))):
                        if re.match(r'^\d+$', left_tokens[k]):
                            qty_idx = k
                            print(f"Found digit token at index {k}: {left_tokens[k]}")
                            break
                            
                if qty_idx != -1:
                    qty = num(left_tokens[qty_idx])
                    print(f"Parsed qty: {qty}")
