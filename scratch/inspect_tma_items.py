import sys
import os
import re
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

import extractor

# Set stdout to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

with open(base_dir / "scratch/swapna_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

# Run parse_tma and print intermediate steps
lines = extractor.clean_lines(text)
header_words = {'MFGR', 'LOC', 'QTY', 'FREE', 'HSN', 'PACK', 'BATCH', 'EXP', 'GST', 'GST%', 'MRP', 'RATES', 'AMOUNT', 'PRODUCT', 'DESCRIPTION', 'PCODE', 'DL', 'REG', 'TSMC', 'FSSAI'}
last_product = ''

items = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    
    # 1. Aggressive Same-Line Recovery
    if len(line.split()) >= 6:
        toks = [t.strip() for t in re.split(r'[|!}\]\[\s]+', line) if t.strip()]
        if len(toks) >= 6:
            amt_r = extractor.num(toks[-1])
            if amt_r > 5:
                found_any = False
                for r_idx in range(-2, -7, -1):
                    if abs(r_idx) > len(toks): break
                    rate_r = extractor.num(toks[r_idx])
                    if rate_r > 50:
                        qty_r = round(amt_r / rate_r, 0)
                        if qty_r > 0 and qty_r < 5000 and (amt_r % rate_r < 2 or amt_r % rate_r > rate_r - 2):
                            product_r = " ".join([t for t in toks[1:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                            if not product_r:
                                product_r = " ".join([t for t in toks[0:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                            product_r = extractor.clean_product_name(product_r)
                            if extractor.is_valid_product(product_r):
                                print(f"Line {i+1}: Matched block 1 (Same-line recovery)")
                                items.append({"product": product_r, "qty": qty_r, "rate": rate_r, "gst_pct": 18.0, "amount": amt_r, "disc_pct": 0})
                                i += 1
                                found_any = True
                                break
                if found_any: continue

    # 2. Starts with short uppercase code
    mfgr_match = re.search(r'^([A-Z]{2,6})(?:\s+|$)', line)
    if mfgr_match and mfgr_match.group(1).upper() not in header_words:
        block = lines[i : i + 15]
        
        # SAME-LINE optimization in standard block
        line_tokens = [t.strip() for t in line.split('|' if '|' in line else ' ') if t.strip()]
        same_line_matched = False
        if len(line_tokens) >= 8:
            num_end = 0
            for t in reversed(line_tokens):
                if re.match(r'^[\d.,%\[\]{}!|]+$', t): num_end += 1
                else: break
            if num_end >= 4:
                amt_s = extractor.num(line_tokens[-1])
                rate_s = extractor.num(line_tokens[-2])
                mrp_s = extractor.num(line_tokens[-3])
                gst_s = extractor.num(line_tokens[-4])
                if amt_s > 0 and rate_s > 0:
                    qty_s = round(amt_s / rate_s, 0)
                    product_s = extractor.clean_product_name(" ".join(line_tokens[1 : len(line_tokens)-num_end]))
                    if extractor.is_valid_product(product_s):
                        print(f"Line {i+1}: Matched block 2 (Same-line optimization of block)")
                        disc_pct = round((1 - (amt_s / (qty_s * rate_s))) * 100, 2) if (qty_s * rate_s) > 0 else 0
                        items.append({
                            "product": product_s, "qty": qty_s, "rate": rate_s, 
                            "gst_pct": gst_s, "amount": amt_s, "disc_pct": disc_pct
                        })
                        same_line_matched = True
                        i += 1
                        continue
        if same_line_matched: continue

        # Standard block parsing (spread over multiple lines)
        best_k = -1
        best_score = -1
        for k in range(7, 13):
            if k+2 >= len(block): break
            gst_token = block[k-1]
            mrp_token = block[k]
            rate_token = block[k+1]
            amt_token = block[k+2]
            if any(x in (gst_token or '') for x in ['/', ':']): continue
            gst_v = extractor.num(gst_token)
            mrp_v = extractor.num(mrp_token)
            rate_v = extractor.num(rate_token)
            amt_v = extractor.num(amt_token)
            
            if amt_v > 0 and rate_v > 0 and mrp_v > 0 and amt_v < 1000000:
                score = 0
                if int(gst_v) in [0, 5, 12, 18, 28]: score += 10
                if amt_v >= rate_v and amt_v >= mrp_v: score += 5
                if rate_v <= mrp_v * 1.5: score += 5
                if score > best_score:
                    best_score = score
                    best_k = k
        if best_k > 0:
            k = best_k
            gst_v = extractor.num(block[k-1])
            mrp_v = extractor.num(block[k])
            rate_v = extractor.num(block[k+1])
            amt_v = extractor.num(block[k+2])
            paid_v = extractor.num(block[1])
            free_v = extractor.num(block[2])
            if free_v >= 1000: free_v = 0
            qty_v = paid_v + free_v
            disc_pct = round((1 - (amt_v / (qty_v * rate_v))) * 100, 2) if (qty_v * rate_v) > 0 else 0
            product_parts = block[5 : k-1]
            filtered = [p for p in product_parts if re.search(r'[A-Za-z]{3,}', p) and not re.search(r'^\d+YI|^\d+/\d+|^[A-Z0-9]{8,}|DL\s*NO|FSSAI', p, re.I)]
            if filtered: product = " ".join(filtered).strip()
            elif last_product: product = last_product
            else: product = " ".join(product_parts).strip()
            product = extractor.clean_product_name(product)
            if extractor.is_valid_product(product):
                print(f"Line {i+1}: Matched block 3 (Multi-line standard block) with best_k={k}")
                items.append({
                    "product": product, "qty": qty_v, "rate": rate_v, 
                    "gst_pct": gst_v, "amount": amt_v, "disc_pct": disc_pct
                })
                i += k + 2
                continue

    # 3. Smart Multi-Line Joining
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
            if re.match(r'^[\d.,%]+$', t): num_end += 1
            else: break
        if num_end >= 2:
            amt = extractor.num(tokens[-1])
            rate = extractor.num(tokens[-2])
            gst = 0
            date_idx = len(tokens) - num_end - 1
            if date_idx >= 0 and re.match(r'^\d{1,2}/\d{2,4}$', tokens[date_idx]):
                if num_end >= 4: gst = extractor.num(tokens[-num_end])
                left_tokens = tokens[:date_idx]
            else:
                if num_end >= 3: gst = extractor.num(tokens[-num_end])
                left_tokens = tokens[:len(tokens) - num_end]
                
            if amt > 0 and rate > 0 and amt < 1000000:
                qty_idx = -1
                taxable_amt = amt / (1 + gst / 100.0) if gst > 0 else amt
                expected_qty = round(taxable_amt / rate, 0)
                if expected_qty > 0:
                    for k in range(min(6, len(left_tokens))):
                        if extractor.num(left_tokens[k]) == expected_qty:
                            qty_idx = k; break
                if qty_idx == -1:
                    for k in range(min(4, len(left_tokens))):
                        if re.match(r'^\d+$', left_tokens[k]):
                            qty_idx = k; break
                if qty_idx != -1:
                    qty = extractor.num(left_tokens[qty_idx])
                    free_val = 0
                    if qty_idx + 1 < len(left_tokens):
                        free_tok = left_tokens[qty_idx + 1]
                        if re.match(r'^[\d.,%]+$', free_tok) and not free_tok.endswith('%'):
                            free_val = extractor.num(free_tok)
                    total_qty = qty + free_val
                    p_tokens = []
                    for p in left_tokens[qty_idx + 1:]:
                        if re.match(r'^[\d.,%]+$', p): continue
                        if re.match(r'^\d*(ML|GM|S|TABS|CAPS|PACK)\.?$', p, re.I): continue
                        p_tokens.append(p)
                    product = " ".join(p_tokens).strip()
                    product = extractor.clean_product_name(product)
                    if qty > 0 and extractor.is_valid_product(product):
                        print(f"Line {i+1}: Matched block 4 (Heuristic parsing)")
                        disc_pct = round((1 - (taxable_amt / (total_qty * rate))) * 100, 2) if (total_qty * rate) > 0 else 0
                        items.append({"product": product, "qty": total_qty, "rate": rate, "gst_pct": gst, "amount": amt, "disc_pct": disc_pct})
    i += 1
