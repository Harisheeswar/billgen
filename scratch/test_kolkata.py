import sys
import re

with open("scratch/lalruattl_ocr.txt", "r", encoding="utf-8") as f:
    text = f.read()

from extractor import clean_lines, extract_invoice_no, extract_date, extract_customer, num, round_val
lines = clean_lines(text)
invoice_no = extract_invoice_no(text)
date_str = extract_date(text)
customer = extract_customer(lines)

def clean_product_name(product):
    if not product: return ""
    # Strip any leading/trailing garbage symbols (like brackets, curly braces)
    product = re.sub(r'^[^a-zA-Z0-9(]+|[^a-zA-Z0-9)]+$', '', product).strip()
    # Strip common pack sizes at the end of the product name (e.g. GLASS, S50ML, 2.5ML, etc.)
    product = re.sub(r'\s+(GLASS|[a-zA-Z]?\d+(\.\d+)?(ML|GM|CAPS|TABS|CAP|TAB|S))\s*$', '', product, flags=re.I).strip()
    # Final cleanup of symbols
    product = re.sub(r'^[^a-zA-Z0-9(]+|[^a-zA-Z0-9)]+$', '', product).strip()
    return product

summary_keywords = ['GRAND TOTAL', 'SGST', 'CGST', 'TOTAL ITEM', 'TOTAL QTY', 'ROUND OFF', 'DISCOUNT', 'CN/DN', 'Goods Once Sold', 'CUSTOMER CARE']

# Modified Variant 1
items1 = []
for line in lines:
    u_line = line.upper()
    if any(k in u_line for k in summary_keywords):
        continue
        
    tokens = [t.strip() for t in line.replace('|', ' ').split() if t.strip()]
    if len(tokens) >= 10 and re.match(r'^\d+$', tokens[0]):
        date_idx = -1
        for k in range(len(tokens)-1, 3, -1):
            clean_t = re.sub(r'^[^0-9]+|[^0-9]+$', '', tokens[k])
            if re.match(r'^\d{1,2}/\d{2,4}$', clean_t):
                date_idx = k
                break
        if date_idx != -1 and date_idx < len(tokens) - 3:
            qty = num(tokens[2])
            taxable = num(tokens[-1])
            gst_pct = num(tokens[-2])
            rate = num(tokens[-5])
            
            p_tokens = tokens[4 : date_idx - 1]
            product = " ".join(p_tokens).strip()
            product = clean_product_name(product)
            
            if product:
                disc_pct = round((1 - (taxable / (qty * rate))) * 100, 2) if (qty * rate) > 0 else 0
                items1.append({"product": product, "qty": qty, "rate": rate, "gst_pct": gst_pct, "amount": taxable, "disc_pct": disc_pct})

# Deduplicate items
unique_items = []
seen = set()
for r in items1:
    norm_prod = re.sub(r'[^A-Z0-9]', '', r['product'].upper())[:15]
    key = (norm_prod, int(r['qty']))
    
    if key not in seen:
        seen.add(key)
        unique_items.append(r)
    else:
        idx = -1
        for i, item in enumerate(unique_items):
            item_norm = re.sub(r'[^A-Z0-9]', '', item['product'].upper())[:15]
            if item_norm == norm_prod and int(item['qty']) == int(r['qty']):
                idx = i; break
        if idx != -1:
            curr_item = unique_items[idx]
            curr_diff = abs(curr_item['rate'] * curr_item['qty'] - curr_item['amount'])
            new_diff = abs(r['rate'] * r['qty'] - r['amount'])
            if new_diff < curr_diff:
                unique_items[idx] = r

print("Deduplicated items:")
for it in unique_items:
    print(" ", it)
