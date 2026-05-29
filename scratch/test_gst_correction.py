import sys
import os
import re
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import num

def test_correction(text, current_gsts):
    active_slabs = []
    for line in text.split('\n'):
        m = re.search(r'\b(0|5|12|18|28)(?:\.00)?\s*%', line)
        if m:
            val = float(m.group(1))
            numbers = [num(t) for t in re.findall(r'[\d.,]+', line) if num(t) > 0]
            if len(numbers) > 1:
                active_slabs.append(val)
    active_slabs = sorted(list(set(active_slabs)))
    if not active_slabs:
        active_slabs = [18.0]
        
    print(f"Active GST slabs found: {active_slabs}")
    corrected = []
    for gst in current_gsts:
        corr = min(active_slabs, key=lambda x: abs(x - gst))
        corrected.append(corr)
    return corrected

# Test BCD
print("--- Testing BCD ---")
with open(base_dir / "scratch/bcd_ocr.txt", "r", encoding="utf-8") as f:
    bcd_text = f.read()
print(test_correction(bcd_text, [48.0, 18.0]))

# Test Florance
print("\n--- Testing Florance ---")
with open(base_dir / "scratch/florance_ocr.txt", "r", encoding="utf-8") as f:
    florance_text = f.read()
print(test_correction(florance_text, [8.0, 8.0]))
