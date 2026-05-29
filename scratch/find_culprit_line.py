import sys
import os
import re
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import clean_lines, num, is_valid_product, clean_product_name

with open(base_dir / "scratch/swapna_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

lines = clean_lines(text)

items = []
header_words = {'MFGR', 'LOC', 'QTY', 'FREE', 'HSN', 'PACK', 'BATCH', 'EXP', 'GST', 'GST%', 'MRP', 'RATES', 'AMOUNT', 'PRODUCT', 'DESCRIPTION', 'PCODE', 'DL', 'REG', 'TSMC', 'FSSAI'}
last_product = ''

i = 0
while i < len(lines):
    line = lines[i].strip()
    
    # Trace logic
    # Aggressive Same-Line Recovery
    if len(line.split()) >= 6:
        toks = [t.strip() for t in re.split(r'[|!}\]\[\s]+', line) if t.strip()]
        if len(toks) >= 6:
            amt_r = num(toks[-1])
            if amt_r > 5:
                found_any = False
                for r_idx in range(-2, -7, -1):
                    if abs(r_idx) > len(toks): break
                    rate_r = num(toks[r_idx])
                    if rate_r > 0:
                        qty_r = round(amt_r / rate_r, 0)
                        if qty_r > 0 and qty_r < 5000 and (amt_r % rate_r < 2 or amt_r % rate_r > rate_r - 2):
                            product_r = " ".join([t for t in toks[1:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                            if not product_r:
                                product_r = " ".join([t for t in toks[0:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                            
                            product_r = clean_product_name(product_r)
                            if is_valid_product(product_r):
                                print(f"Line {i+1} matched via Same-Line Recovery:")
                                print(f"  Line: {line}")
                                print(f"  product: {product_r}, qty: {qty_r}, rate: {rate_r}, amount: {amt_r}")
                                items.append({"product": product_r, "qty": qty_r, "rate": rate_r, "gst_pct": 18.0, "amount": amt_r, "disc_pct": 0})
                                i += 1
                                found_any = True
                                break
                if found_any: continue

    # Standard block checking
    mfgr_match = re.search(r'^([A-Z]{2,6})(?:\s+|$)', line)
    if mfgr_match and mfgr_match.group(1).upper() not in header_words:
        # standard block logic omitted for brevity, let's keep the main loop running
        pass
        
    current_line = line
    current_tokens = [t.strip() for t in current_line.split('|' if '|' in current_line else ' ') if t.strip()]
    if len(current_tokens) >= 4:
        has_qty = any(re.match(r'^\d+$', t) for t in current_tokens[1:4])
        has_prices = re.match(r'^[\d.,]+$', current_tokens[-1])
        if has_qty and not has_prices:
            peek_idx = i + 1
            while peek_idx < len(lines):
                next_l = lines[peek_idx]
                if re.match(r'^[A-Z]{2,6}(\s+|$)', next_l) and any(re.match(r'^\d+$', t) for t in next_l.split()[1:4]):
                    break
                current_line += " " + next_l
                current_tokens = [t.strip() for t in current_line.split('|' if '|' in current_line else ' ') if t.strip()]
                peek_idx += 1
                i += 1
                if re.match(r'^[\d.,]+$', current_tokens[-1]):
                    break
                    
    tokens = current_tokens
    if len(tokens) >= 6:
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
                if num_end >= 4: gst = num(tokens[-num_end])
                left_tokens = tokens[:date_idx]
            else:
                if num_end >= 3: gst = num(tokens[-num_end])
                left_tokens = tokens[:len(tokens) - num_end]
                
            if amt > 0 and rate > 0 and amt < 1000000:
                qty_idx = -1
                taxable_amt = amt / (1 + gst / 100.0) if gst > 0 else amt
                expected_qty = round(taxable_amt / rate, 0)
                if expected_qty > 0:
                    for k in range(min(6, len(left_tokens))):
                        if num(left_tokens[k]) == expected_qty:
                            qty_idx = k; break
                if qty_idx == -1:
                    for k in range(min(4, len(left_tokens))):
                        if re.match(r'^\d+$', left_tokens[k]):
                            qty_idx = k; break
                if qty_idx != -1:
                    qty = num(left_tokens[qty_idx])
                    free_val = 0
                    if qty_idx + 1 < len(left_tokens):
                        free_tok = left_tokens[qty_idx + 1]
                        if re.match(r'^[\d.,%]+$', free_tok) and not free_tok.endswith('%'):
                            free_val = num(free_tok)
                    total_qty = qty + free_val
                    p_tokens = []
                    for p in left_tokens[qty_idx + 1:]:
                        if re.match(r'^[\d.,%]+$', p): continue
                        if re.match(r'^\d*(ML|GM|S|TABS|CAPS|PACK)\.?$', p, re.I): continue
                        p_tokens.append(p)
                    product = " ".join(p_tokens).strip()
                    product = clean_product_name(product)
                    if qty > 0 and is_valid_product(product):
                        print(f"Line {i+1} matched via Heuristic parsing:")
                        print(f"  Line: {current_line}")
                        print(f"  product: {product}, qty: {total_qty}, rate: {rate}, amount: {amt}")
                        items.append({"product": product, "qty": total_qty, "rate": rate, "gst_pct": gst, "amount": amt, "disc_pct": 0})
    i += 1
