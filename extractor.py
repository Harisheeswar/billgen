import os
import re
import csv
import json
import subprocess
import tempfile
import shutil
import time
import math
from pathlib import Path

# --- Configuration & Paths ---
BASE_DIR = Path(__file__).parent.absolute()
INVOICE_FOLDER = BASE_DIR / "invoices"
TESSERACT_EXE = BASE_DIR / "tesseract.exe"
# Try common poppler path from the JS code
POPPLER_DIR = BASE_DIR / "poppler-26.02.0"
PDFTOTEXT_EXE = POPPLER_DIR / "Library" / "bin" / "pdftotext.exe"
PDFTOPPM_EXE = POPPLER_DIR / "Library" / "bin" / "pdftoppm.exe"

# If local binaries not found, fallback to PATH
if not PDFTOTEXT_EXE.exists():
    PDFTOTEXT_EXE = "pdftotext"
if not PDFTOPPM_EXE.exists():
    PDFTOPPM_EXE = "pdftoppm"
if not TESSERACT_EXE.exists():
    TESSERACT_EXE = "tesseract"

def num(s):
    if s is None:
        return 0.0
    try:
        # Remove commas, symbols, and whitespace
        clean = re.sub(r'[,%\s]', '', str(s))
        # Keep only digits, dots, and minus signs
        clean = re.sub(r'[^\d.-]', '', clean)
        if not clean or clean == '.':
            return 0.0
        return float(clean)
    except ValueError:
        return 0.0

def round_val(x, n=2):
    return round(x, n)

def clean_product_name(product):
    if not product:
        return ""
    
    # Remove leading/trailing non-alphanumeric garbage
    product = re.sub(r'^[^a-zA-Z0-9(]+|[^a-zA-Z0-9)]+$', '', product).strip()
    
    # Strip expiry dates (e.g., 02/26, 10/27, 8/27, ]1/26, {10/27, 03/26)
    product = re.sub(r'\b[\[\]{}|!\s]*\d{1,2}[-\/]\d{2,4}\b', ' ', product)
    
    # Strip batch codes and other alphanumeric codes
    # Batch codes in TMA are typically alphanumeric with dashes, e.g. 12YC05-6-5G, 11YC03-3-58, 10YI10-1-18, 11YI06-6-7G
    product = re.sub(r'\b\d+[A-Z]+\d+[-A-Z0-9]*\b', ' ', product, flags=re.I)
    
    # Strip leading/trailing non-alphanumeric garbage again
    product = re.sub(r'^[^a-zA-Z0-9(]+|[^a-zA-Z0-9)]+$', '', product).strip()
    
    # Check tokens and strip HSN, pack size, batch codes, and MFG name (e.g. CHOS)
    tokens = product.split()
    cleaned_tokens = []
    for t in tokens:
        # Check if it looks like a batch code (has letters and numbers, length >= 5, not a pack size)
        is_batch = False
        if '-' in t and re.search(r'\d', t) and re.search(r'[A-Za-z]', t):
            # Exclude tokens starting with a real word (e.g. SERUM-100ML)
            if not re.match(r'^[A-Za-z]{3,}', t):
                is_batch = True
        elif len(t) >= 5 and re.search(r'\d', t) and re.search(r'[A-Z]', t, re.I):
            if not re.match(r'^[A-Za-z]{3,}', t) and not re.match(r'^\d+(\.\d+)?(ML|GM|MG|CAP|TAB|S)$', t, re.I):
                is_batch = True
                
        # Also check if it is HSN (4 to 8 digits)
        is_hsn = False
        if re.match(r'^\d{4,8}$', t):
            is_hsn = True
            
        # Also check if it is a packing size token (e.g. 10GM, 40ML, 50ML, 100ML, 2.5ML, S50ML, GLASS)
        is_pack = False
        if re.match(r'^[a-zA-Z]?\d+(\.\d+)?(ML|GM|MG|CAPS|TABS|CAP|TAB|S|G)$', t, re.I) or t.upper() in ['GLASS', 'GLASS}', 'ML', 'GM', 'MG', 'CAPS', 'TABS', 'CAP', 'TAB']:
            is_pack = True
            
        # Also check if it is a common manufacturer code (e.g. CHOS) at the start
        is_mfg = False
        if not cleaned_tokens and t.upper() in ['CHOS', 'MFG', 'MFGR', 'LOC', 'IZO', '1ZO']:
            is_mfg = True
            
        # Also check if it is a number or percentage (e.g. 62.5%, 66.67%, 18%)
        is_num_or_pct = False
        if re.match(r'^[\d.,%+-]+$', t):
            is_num_or_pct = True
            
        if not (is_batch or is_hsn or is_pack or is_mfg or is_num_or_pct):
            cleaned_tokens.append(t)
            
    product = " ".join(cleaned_tokens).strip()
    
    # Strip any trailing pack sizes at the end of the product name that might have been joined
    product = re.sub(r'\s+(GLASS|[a-zA-Z]?\d+(\.\d+)?(ML|GM|CAPS|TABS|CAP|TAB|S))\s*$', '', product, flags=re.I).strip()
    
    # Strip leading/trailing non-alphanumeric garbage
    product = re.sub(r'^[^a-zA-Z0-9(]+|[^a-zA-Z0-9)]+$', '', product).strip()
    return product

def is_valid_product(product_name):
    if not product_name:
        return False
    # Must contain at least one word with 4 or more alphabetic characters
    # (to filter out OCR noise like 'V92.94', '18.00%', '13215.00 V92.9', '693', 'Fay')
    if not re.search(r'[A-Za-z]{4,}', product_name):
        return False
        
    u = product_name.upper()
    # Comprehensive blacklist of words that should never appear in a product name
    bad_words = [
        'TOTAL', 'GRAND', 'CGST', 'SGST', 'TAXABLE', 'SCHEME', 'SCHM', 'ROUND', 
        'DISCOUNT', 'CN/DN', 'CUSTOMER', 'PERSON', 'SIGNATURE', 'AUTHORISED', 
        'SIGNATORY', 'COMPETENT', 'COPY', 'ORIGINAL', 'DUPLICATE', 'BILL', 
        'INVOICE', 'DATE', 'DUE', 'PARTY', 'CODE', 'TELEPHONE', 'PHONE', 
        'MOBILE', 'FSSAI', 'GSTIN', 'PAN', 'EMAIL', 'MAIL', 'WEBSITE', 'WEB', 
        'COM', 'NET', 'ORG', 'MEDICAL', 'AGENCY', 'THANE', 'SHRADHA', 'GOA', 
        'ZELIG', 'HILLS', 'ROAD', 'STREET', 'PLOT', 'BUILDING', 'FLOOR', 
        'LAKE', 'GARDEN', 'GARDENS', 'KOLKATA', 'BANGALORE', 'HYDERABAD', 
        'GUWAHATI', 'AIZWAL', 'MUMBAI', 'DELHI', 'STATE', 'TEL', 'FAX', 'DL NO'
    ]
    if any(w in u for w in bad_words):
        return False
    return True

def clean_lines(text):
    if not text:
        return []
    lines = [l.strip() for l in text.split('\n')]
    # Deduplicate repeated lines (common in some PDF extractions)
    kept = []
    for i, line in enumerate(lines):
        if i == 0 or line != lines[i-1]:
            if line:
                kept.append(line)
    return kept

def detect_supplier(text, pdf_path=None, original_filename=''):
    u = text.upper()
    path_u = (str(pdf_path).upper() if pdf_path else "") + " " + original_filename.upper()
    
    if 'THANE MEDICAL' in u or 'TMA' in path_u:
        if any(k in path_u for k in ['KOLKATA', 'GUWAHATI', 'MANPADA', 'MUMBAI', 'THANE']):
            if not any(k in path_u for k in ['BANGALORE', 'HYDERABAD']):
                return 'TMA_KOLKATA'
        if any(k in path_u for k in ['BANGALORE', 'HYDERABAD']):
            return 'TMA_BANGALORE'
        header = u[:500]
        if any(k in header for k in ['KOLKATA', 'GUWAHATI', 'LAKE GARDEN', 'MANPADA', 'THANE WEST']):
            return 'TMA_KOLKATA'
        return 'TMA_BANGALORE'
        
    if 'SHRADHA MEDICAL' in u or 'SMA' in u or 'SMA' in path_u:
        return 'SMA'
    if 'GMD' in u or 'GMD' in path_u:
        return 'GMD'
        
    return 'ZELIG'

def extract_invoice_no(text):
    m = re.search(r'Invoice\s*No\.?\s*[:.]?\s*([A-Z0-9\-/]+)', text, re.I) or \
        re.search(r'\b(?:Inv\.?No|Bill\s*No\.?)\s*[:.]?\s*([A-Z0-9\-/]+)', text, re.I)
    if m:
        inv = m.group(1).strip()
        # Clean trailing 'Date' or 'Dt' OCR artifacts
        inv = re.sub(r'(Date|Dt|Dt\.?)$', '', inv, flags=re.I).strip()
        # Fix common OCR errors: O -> 0 in numeric-like invoices (e.g., AOOO081 -> A000081)
        if re.match(r'^[A-Z][O0]+\d+$', inv):
            inv = inv.replace('O', '0')
        return inv
    return 'UNKNOWN'

def extract_date(text):
    m = re.search(r'(?:^|\n)\s*Date\s*[:.]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.I) or \
        re.search(r'(?:Inv\.?Date|Bill\s*Date|Date)\s*[:.]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.I)
    return m.group(1).strip() if m else 'UNKNOWN'

def extract_customer(lines):
    skip_pat = re.compile(r'^THANE\s*MEDICAL\s*AGENCY|BUILDING|FARHAT|BANJARA|HILLS|GSTIN|PAN|DL NO|DLNO|REG NO|TSMC|FSSAI|STATE|CODE|TEL|MOBILE|EMAIL|@|SIGN|COPY|ERR|ORIGINAL|REPRINT|DESCRIPTION|RATES|AMOUNT|PCode|Inv\. No|Due Date|DUPLICATE|SHREE|NAMAHA|PAYMENT|RECORD|SCH\.AMT|DISC\.AMT|TAXABLE|TOTAL\s*AMT|ROUND\s*OFF|PERSON|SIGNATURE|TOTAL', re.I)
    
    # Priority 1: Lines starting with M/S or DR or other prefixes
    for i in range(min(len(lines), 40)):
        l = lines[i].strip()
        if skip_pat.search(l) or len(l) < 5: continue
        if re.search(r'^(M/S\.?|DR\.?|SHRI|SMT\.?|PHARMACY|MEDICAL|HOSPITAL|CLINIC|EYE|SKIN|HEALTH|SRI|SIDDISAI)', l, re.I):
            # Clean labels from the customer line
            customer = re.split(r'Invoice\s*No|Date|Order\s*No|L\.R\.|Page|PH\.NO', l, flags=re.I)[0].strip()
            if i + 1 < len(lines):
                next_l = lines[i+1].strip()
                if not skip_pat.search(next_l) and len(next_l) > 10 and not re.match(r'^[A-Z]{3,4}$', next_l):
                    next_l_clean = re.split(r'Invoice\s*No|Date|Order\s*No|L\.R\.|Page|PH\.NO', next_l, flags=re.I)[0].strip()
                    customer += " " + next_l_clean
            return customer.strip()
            
    # Priority 2: Look for keywords even if no prefix
    for i in range(min(len(lines), 40)):
        l = lines[i].strip()
        if skip_pat.search(l) or len(l) < 5: continue
        if re.search(r'(PHARMACY|MEDICALS?|HOSPITAL|CLINIC|SKIN CARE|EYE CARE|DERMA|SKIN)', l, re.I):
            return l

    # Priority 3: All caps long string fallback
    for i in range(min(len(lines), 40)):
        l = lines[i].strip()
        if re.match(r'^[A-Z.\s]{10,}$', l) and not skip_pat.search(l):
            return l
            
    return 'UNKNOWN'

# --- TMA Specific Parser (translated from tma_parser.js and api.js) ---

def extract_tma_summary(text, invoice_no):
    label = f"[TMA {invoice_no}]"
    # Match 7-token sequences in the GST table
    # <rate>% <gross> <scheme> <cd> <taxable> <cgst_amt> <sgst_amt> <row_total>
    num_pat = r'(\d[\d,]*\.?\d*)'
    sep = r'\s+'
    pattern = re.compile(sep.join([num_pat]*7))
    
    matches = pattern.finditer(text)
    total_cgst = 0.0
    total_sgst = 0.0
    found = False
    last_row_total = 0.0
    seen = set()
    
    for m in matches:
        gross = num(m.group(1))
        scheme = num(m.group(2))
        cd = num(m.group(3))
        taxable = num(m.group(4))
        maybe_cgst = num(m.group(5))
        maybe_sgst = num(m.group(6))
        row_total = num(m.group(7))
        
        if maybe_cgst == 0 and maybe_sgst == 0:
            continue
            
        key = f"{gross}|{scheme}|{taxable}|{maybe_cgst}|{maybe_sgst}|{row_total}"
        if key in seen:
            continue
        seen.add(key)
        
        # Sanity checks
        taxable_ok = abs((gross - scheme - cd) - taxable) < 2
        total_ok = abs((taxable + maybe_cgst + maybe_sgst) - row_total) < 2
        
        if not taxable_ok or not total_ok:
            continue
            
        total_cgst += maybe_cgst
        total_sgst += maybe_sgst
        last_row_total = row_total
        found = True
        
    # Extract Final Amount from labels like "To Pay" or "Grand Total"
    # We use a more specific pattern to avoid matching "Total Amt 0%" header rows
    to_pay_match = re.search(r'To\s*Pay\s*[:.-]?\s*([\d,.]+)', text, re.I) or \
                   re.search(r'Grand\s*Total\s*[:.-]?\s*([\d,.]+)', text, re.I) or \
                   re.search(r'Total\s*Amt\s*[:.-]?\s*([\d,.]+)', text, re.I)
    
    final_invoice = num(to_pay_match.group(1)) if to_pay_match else last_row_total
    
    if not found:
        return None
        
    return {
        "cgst": round_val(total_cgst),
        "sgst": round_val(total_sgst),
        "final_invoice": final_invoice
    }

def parse_tma(text):
    lines = clean_lines(text)
    invoice_no = extract_invoice_no(text)
    date_str = extract_date(text)
    customer = extract_customer(lines)
    
    if 'THANE MEDICAL' in customer.upper() or 'GST INVOICE' in customer.upper():
        # Try harder to find recipient in Mumbai layout
        for l in lines[:20]:
            if re.search(r'(?:DR\.|M/S|HOSPITAL|PHARMACY|CLINIC)', l, re.I) and 'THANE MEDICAL' not in l.upper():
                customer = re.split(r'Invoice\s*No|Date|Order\s*No|L\.R\.|Page|PH\.NO', l, flags=re.I)[0].strip()
                break
    
    # Summary values extraction
    tma_summary = extract_tma_summary(text, invoice_no)
    final_invoice = tma_summary['final_invoice'] if tma_summary else 0.0
    
    items = []
    header_words = {'MFGR', 'LOC', 'QTY', 'FREE', 'HSN', 'PACK', 'BATCH', 'EXP', 'GST', 'GST%', 'MRP', 'RATES', 'AMOUNT', 'PRODUCT', 'DESCRIPTION', 'PCODE', 'DL', 'REG', 'TSMC', 'FSSAI'}
    last_product = ''
    skip_pat = re.compile(r'^THANE\s*MEDICAL\s*AGENCY|BUILDING|FARHAT|BANJARA|HILLS|GSTIN|PAN|DL NO|DLNO|REG NO|TSMC|FSSAI|STATE|CODE|TEL|MOBILE|EMAIL|@|SIGN|COPY|ERR|ORIGINAL|REPRINT|DESCRIPTION|RATES|AMOUNT|PCode|Inv\. No|Due Date|DUPLICATE|SHREE|NAMAHA|PAYMENT|RECORD|SCH\.AMT|DISC\.AMT|TAXABLE|TOTAL\s*AMT|ROUND\s*OFF|PERSON|SIGNATURE|TOTAL', re.I)

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
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
                        if rate_r > 50:
                            qty_r = round(amt_r / rate_r, 0)
                            if qty_r > 0 and qty_r < 5000 and (amt_r % rate_r < 2 or amt_r % rate_r > rate_r - 2):
                                # Found it!
                                # Product is everything before the first numeric column we used
                                product_r = " ".join([t for t in toks[1:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                                if not product_r: # Fallback for SN-less rows
                                    product_r = " ".join([t for t in toks[0:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                                
                                product_r = clean_product_name(product_r)
                                if is_valid_product(product_r):
                                    # Merge logic for 0-amount (100% discount) rows
                                    if amt_r == 0 and items and items[-1]['product'] == product_r:
                                        prev = items[-1]
                                        new_qty = prev['qty'] + qty_r
                                        prev['qty'] = new_qty
                                        prev['disc_pct'] = round((1 - (prev['amount'] / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                                    elif amt_r > 0:
                                        disc_pct = round((1 - (amt_r / (qty_r * rate_r))) * 100, 2) if (qty_r * rate_r) > 0 else 0
                                        items.append({
                                            "product": product_r, "qty": qty_r, "rate": rate_r, 
                                            "gst_pct": 18.0, "amount": amt_r, "disc_pct": disc_pct
                                        })
                                    i += 1
                                    found_any = True
                                    break
                    if found_any: continue

        # Check if line looks like a product line (starts with short uppercase code)
        mfgr_match = re.search(r'^([A-Z]{2,6})(?:\s+|$)', line)
        if mfgr_match and mfgr_match.group(1).upper() not in header_words:
            block = lines[i : i + 15]
            # Optimization: Check if the numeric tail is on the SAME line as MFGR
            # (Common in OCR or high-density layouts)
            line_tokens = [t.strip() for t in line.split('|' if '|' in line else ' ') if t.strip()]
            if len(line_tokens) >= 8:
                # <MFGR> <LOC> <QTY> <FREE> <HSN> <PACK> <PRODUCT> <BATCH> <EXP> <GST> <MRP> <RATE> <AMT>
                num_end = 0
                for t in reversed(line_tokens):
                    if re.match(r'^[\d.,%\[\]{}!|]+$', t): num_end += 1
                    else: break
                
                if num_end >= 4:
                    amt_s = num(line_tokens[-1])
                    rate_s = num(line_tokens[-2])
                    mrp_s = num(line_tokens[-3])
                    gst_s = num(line_tokens[-4])
                    
                    if amt_s > 0 and rate_s > 0:
                        # Extract quantity from tokens or fallback to division
                        qty_s = 0
                        for k_t in range(1, min(4, len(line_tokens))):
                            if re.match(r'^\d+$', line_tokens[k_t]):
                                qty_s = num(line_tokens[k_t])
                                if k_t + 1 < len(line_tokens) and re.match(r'^\d+$', line_tokens[k_t+1]):
                                    qty_s += num(line_tokens[k_t+1])
                                break
                        if qty_s == 0:
                            qty_s = round(amt_s / rate_s, 0)
                        product_s = clean_product_name(" ".join(line_tokens[1 : len(line_tokens)-num_end]))
                        if is_valid_product(product_s):
                            disc_pct = round((1 - (amt_s / (qty_s * rate_s))) * 100, 2) if (qty_s * rate_s) > 0 else 0
                            items.append({
                                "product": product_s, "qty": qty_s, "rate": rate_s, 
                                "gst_pct": gst_s, "amount": amt_s, "disc_pct": disc_pct
                            })
                            i += 1
                            continue

            # Standard block parsing (spread over multiple lines)
            best_k = -1
            best_score = -1
            
            # Look for the numeric tail of the row
            for k in range(7, 13):
                if k+2 >= len(block): break
                gst_token = block[k-1]
                mrp_token = block[k]
                rate_token = block[k+1]
                amt_token = block[k+2]
                
                if any(x in (gst_token or '') for x in ['/', ':']): continue
                
                gst_v = num(gst_token)
                mrp_v = num(mrp_token)
                rate_v = num(rate_token)
                amt_v = num(amt_token)
                
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
                gst_v = num(block[k-1])
                mrp_v = num(block[k])
                rate_v = num(block[k+1])
                amt_v = num(block[k+2])
                paid_v = num(block[1])
                free_v = num(block[2])
                if free_v >= 1000: free_v = 0 # HSN protection
                
                qty_v = paid_v + free_v
                # Use mathematical formula for disc_pct to capture both free schemes and extra discounts
                disc_pct = round((1 - (amt_v / (qty_v * rate_v))) * 100, 2) if (qty_v * rate_v) > 0 else 0
                
                product_parts = block[5 : k-1]
                filtered = [p for p in product_parts if re.search(r'[A-Za-z]{3,}', p) and not re.search(r'^\d+YI|^\d+/\d+|^[A-Z0-9]{8,}|DL\s*NO|FSSAI', p, re.I)]
                
                if filtered:
                    product = " ".join(filtered).strip()
                    last_product = product
                elif last_product:
                    product = last_product
                else:
                    product = " ".join(product_parts).strip()
                
                product = clean_product_name(product)
                if is_valid_product(product):
                    # Merge logic for 0-amount (100% discount) rows
                    if amt_v == 0 and items and items[-1]['product'] == product:
                        prev = items[-1]
                        new_qty = prev['qty'] + qty_v
                        prev['qty'] = new_qty
                        prev['disc_pct'] = round((1 - (prev['amount'] / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                    elif amt_v > 0:
                        items.append({
                            "product": product, "qty": qty_v, "rate": rate_v, 
                            "gst_pct": gst_v, "amount": amt_v, "disc_pct": disc_pct
                        })
                    i += k + 2
                    continue
        
        # Smart Multi-Line Joining
        current_line = line
        current_tokens = [t.strip() for t in current_line.split('|' if '|' in current_line else ' ') if t.strip()]
        
        # Look ahead for multiple lines if this one is truncated
        if len(current_tokens) >= 4:
            has_qty = any(re.match(r'^\d+$', t) for t in current_tokens[1:4])
            has_prices = re.match(r'^[\d.,]+$', current_tokens[-1])
            
            if has_qty and not has_prices:
                peek_idx = i + 1
                while peek_idx < len(lines):
                    next_l = lines[peek_idx]
                    # If next line looks like a NEW item start, stop joining
                    if re.match(r'^[A-Z]{2,6}(\s+|$)', next_l) and any(re.match(r'^\d+$', t) for t in next_l.split()[1:4]):
                        break
                    
                    current_line += " " + next_l
                    current_tokens = [t.strip() for t in current_line.split('|' if '|' in current_line else ' ') if t.strip()]
                    peek_idx += 1
                    i += 1 # Advance main loop index
                    
                    # If we finally found prices at the end, stop joining
                    if re.match(r'^[\d.,]+$', current_tokens[-1]):
                        break
        
        tokens = current_tokens
        if len(tokens) >= 6:
            # Find how many numeric tokens are at the end
            num_end = 0
            for k in range(len(tokens)-1, -1, -1):
                t = tokens[k]
                # Allow numbers with %, or just digits/dots
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
                    elif expected_qty > 0 and expected_qty < 10000:
                        qty = expected_qty
                        qty_idx = 0 # Dummy
                    
                    if qty_idx != -1:
                        
                        # Sanity Check: If a line was cut off, 'rate' might be misread as 'amt'
                        if qty > 1 and rate > amt * 1.2:
                            i += 1
                            continue
                            
                        free_val = 0
                        if qty_idx + 1 < len(left_tokens):
                            free_tok = left_tokens[qty_idx + 1]
                            if re.match(r'^[\d.,%]+$', free_tok) and not free_tok.endswith('%'):
                                free_val = num(free_tok)
                                if free_val >= 1000: free_val = 0
                        
                        # Calculate disc_pct and total qty
                        total_qty = qty + free_val
                        disc_pct = round((1 - (taxable_amt / (total_qty * rate))) * 100, 2) if (total_qty * rate) > 0 else 0
                        
                        p_tokens = []
                        num_left = len(left_tokens[qty_idx + 1:])
                        for idx_p, p in enumerate(left_tokens[qty_idx + 1:]):
                            if re.match(r'^[\d.,%]+$', p): continue
                            if re.match(r'^\d*(ML|GM|S|TABS|CAPS|PACK)\.?$', p, re.I): continue
                            
                            # Improved Batch code filter
                            if idx_p == num_left - 1:
                                # If it's the last token before the date, it might be a batch
                                # Batch codes in TMA are typically alphanumeric (10YI05-2-1)
                                if re.search(r'\d', p) and (re.search(r'[A-Za-z]', p) or len(p) > 5):
                                    continue
                            
                            # Keep most tokens as part of product name
                            if len(p) >= 1:
                                p_tokens.append(p)
                                
                        product = " ".join(p_tokens).strip()
                        
                        if product:
                            last_product = product
                        
                        product = clean_product_name(product)
                        if qty > 0 and is_valid_product(product):
                            items.append({
                                "product": product, "qty": total_qty, "rate": rate, 
                                "gst_pct": gst, "amount": amt, "disc_pct": disc_pct
                            })
        i += 1
        
    unique_items = []
    seen = set()
    for r in items:
        # Deduplicate multi-copy invoices (ORIGINAL, DUPLICATE, etc.)
        # Use only the first word of the product to avoid slight OCR differences across copies
        first_word = r['product'].split()[0] if r['product'] else ''
        key = (first_word, r['qty'], r['rate'], r['amount'])
        if key not in seen:
            seen.add(key)
            unique_items.append(r)
            
    rows = []
    for idx, r in enumerate(unique_items):
        # Format QTY as an integer if it has no decimals
        qty_val = r['qty']
        qty_str = str(int(qty_val)) if isinstance(qty_val, float) and qty_val.is_integer() else str(qty_val)
        
        # Format: [Branch, Customer, InvNo, Date, SNo, Product, Qty, Rate, Disc%, GST%, Amt, CGST, SGST, Final]
        rows.append([
            'TMA (Bangalore/Hyderabad)', customer, invoice_no, date_str, idx + 1, r['product'], f"'{qty_str}",
            r['rate'], r['disc_pct'], r['gst_pct'], r['amount'], "", "", final_invoice
        ])
    return rows


# --- Generic Parser (translated from api.js) ---

def parse_heuristic_items(lines):
    items = []
    in_table = False
    next_sno = 1
    for i in range(len(lines)):
        u = lines[i].upper()
        if 'PRODUCT NAME' in u or 'DESCRIPTION' in u:
            in_table = True
            continue
        if in_table and ('SUB TOTAL' in u or u == 'TOTAL' or 'CLASS' in u):
            break
        
        sno_str = str(next_sno)
        sno_pad = sno_str.zfill(2)
        if in_table and (lines[i] == sno_str or lines[i] == sno_pad):
            r = {"sno": next_sno, "qty": lines[i+2] if i+2 < len(lines) else '1'}
            j = i + 1
            block = []
            while j < len(lines) and j < i + 18:
                next_sno_str = str(next_sno + 1)
                next_sno_pad = next_sno_str.zfill(2)
                if lines[j] == next_sno_str or lines[j] == next_sno_pad: break
                if 'TOTAL' in lines[j].upper(): break
                block.append(lines[j])
                j += 1
            
            name_tokens = []
            for t in block:
                if re.search(r'^\d+(MG|ML|GM|S|CAPS|TABS)$', t, re.I): continue
                if re.match(r'^[A-Z]{3,5}$', t) and t.upper() not in ['NIGHT', 'EYE', 'FACE', 'HAIR', 'GOLD']: continue
                if re.match(r'^[\d.,]+$', t): continue
                if re.match(r'^\d{1,2}/\d{2,4}$', t): continue
                if re.match(r'^[A-Z0-9]{6,}$', t): continue
                name_tokens.append(t)
            
            r['product'] = " ".join(name_tokens).strip()
            p = [num(t) for t in block if re.match(r'^[\d.,]+$', t)]
            if len(p) >= 6:
                r['mrp'], r['rate'], r['disc_pct'], r['cd_pct'], r['gst_pct'], r['amount'] = p[0:6]
            elif len(p) >= 5:
                r['rate'], r['disc_pct'], r['gst_pct'], r['amount'] = p[0], p[1], p[3], p[4]
            
            items.append(r)
            next_sno += 1
    return items

def recovery_items(lines):
    items = []
    skip_pat = re.compile(r'THANE|BUILDING|FARHAT|BANJARA|HILLS|GSTIN|PAN|DL NO|DLNO|REG NO|TSMC|FSSAI|STATE|CODE|TEL|MOBILE|EMAIL|@|SIGN|COPY|ERR|ORIGINAL|REPRINT|DESCRIPTION|RATES|AMOUNT|PCode|Inv\. No|Due Date|DUPLICATE|SHREE|NAMAHA|PAYMENT|RECORD|SCH\.AMT|DISC\.AMT|TAXABLE|TOTAL\s*AMT|ROUND\s*OFF|PERSON|SIGNATURE|TOTAL', re.I)
    for line in lines:
        toks = [t.strip() for t in re.split(r'[|!}\]\[\s]+', line) if t.strip()]
        if len(toks) >= 6:
            amt_r = num(toks[-1])
            if amt_r > 5:
                found_any = False
                for r_idx in range(-2, -7, -1):
                    if abs(r_idx) > len(toks): break
                    rate_r = num(toks[r_idx])
                    if rate_r > 50:
                        # Try to find QTY (usually before rate or at index 2)
                        qty_str = '0'
                        for q_idx in range(1, min(4, len(toks))):
                            if '+' in toks[q_idx] or re.match(r'^\d+$', toks[q_idx]):
                                qty_str = toks[q_idx]
                                break
                                
                        qty_val = 0.0
                        qty_paid = 0.0
                        if '+' in qty_str:
                            parts = qty_str.split('+')
                            qty_val = sum(num(p) for p in parts)
                            qty_paid = num(parts[0])
                        else:
                            qty_val = num(qty_str)
                            qty_paid = qty_val
                            
                        if qty_val == 0:
                            qty_val = round(amt_r / rate_r, 0)
                            qty_paid = qty_val
                            
                        # Check if qty_val * rate approx equals amount OR qty_paid * rate approx equals amount
                        match_ok = (abs(qty_val * rate_r - amt_r) < 5) or (qty_paid > 0 and abs(qty_paid * rate_r - amt_r) < 5)
                        
                        if qty_val > 0 and qty_val < 5000 and match_ok:
                            product_r = " ".join([t for t in toks[1:r_idx-1] if not re.match(r'^[\d.,%|!\]\[]+$', t) and len(t) > 2])
                            if not product_r:
                                product_r = " ".join([t for t in toks[0:r_idx-1] if not re.match(r'^[\d.,%|!\]\[]+$', t) and len(t) > 2])
                            
                            if product_r and not skip_pat.search(product_r):
                                disc_pct = round(((qty_val - qty_paid) / qty_val * 100), 2) if qty_val > 0 else 0
                                items.append({
                                    "product": product_r, "qty": qty_val, "rate": rate_r, 
                                    "gst_pct": 18.0, "amount": amt_r, "disc_pct": disc_pct
                                })
                                found_any = True
                                break
    return items

def parse_zelig(text):
    lines = clean_lines(text)
    supplier = 'ZELIG'
    invoice_no = extract_invoice_no(text)
    date_str = extract_date(text)
    customer = extract_customer(lines)
    
    # Try multiple strategies
    all_variants = []
    all_variants.append(parse_heuristic_items(lines))
    all_variants.append(recovery_items(lines))
    
    items = max(all_variants, key=len)
    
    # Summary values extraction
    m_total = re.search(r'(?:GRAND\s*TOTAL|NET\s*TOTAL|To\s*Pay|Total\s*Amt)[^\d]*([\d,.]+)', text, re.I)
    final_invoice = num(m_total.group(1)) if m_total else 0.0
    
    rows = []
    for idx, r in enumerate(items):
        qty_val = num(r.get('qty', 0))
        qty_str = str(int(qty_val)) if isinstance(qty_val, float) and qty_val.is_integer() else str(qty_val)
        
        rows.append([
            supplier, customer, invoice_no, date_str,
            idx + 1, r.get('product', ''), f"'{qty_str}",
            num(r.get('rate', 0)), num(r.get('disc_pct', 0)), num(r.get('gst_pct', 0)), num(r.get('amount', 0)),
            "", "", final_invoice
        ])
    return rows

def parse_sma_gmd(text, supplier='SMA'):
    lines = clean_lines(text)
    invoice_no = extract_invoice_no(text)
    date_str = extract_date(text)
    customer = extract_customer(lines)
    
    # Specialized customer extraction for SMA/GMD
    for i, line in enumerate(lines[:15]):
        if re.search(r'PARTY DETAILS|BILL TO|PARTY NAME|NAME\s*:', line, re.I):
            for j in range(i+1, min(i+5, len(lines))):
                v = lines[j].strip()
                if v and not re.search(r'GSTIN|MOBILE|GST|FSSAI|DL\s*NO', v, re.I):
                    customer = v
                    break
            break
            
    items = parse_heuristic_items(lines)
    
    # SMA often has qty like "+8" or "10+4"
    for r in items:
        q = str(r.get('qty', '0'))
        if '+' in q:
            parts = q.split('+')
            try:
                r['qty_val'] = sum(num(p) for p in parts)
            except:
                r['qty_val'] = num(q)
        else:
            r['qty_val'] = num(q)

    # Summary values
    m_total = re.search(r'(?:GRAND\s*TOTAL|NET\s*TOTAL|To\s*Pay|Total\s*Amt)[^\d]*([\d,.]+)', text, re.I)
    final_invoice = num(m_total.group(1)) if m_total else 0.0
    
    rows = []
    for idx, r in enumerate(items):
        qty_val = r.get('qty_val', 0)
        qty_str = str(int(qty_val)) if isinstance(qty_val, float) and qty_val.is_integer() else str(qty_val)
        
        rows.append([
            supplier, customer, invoice_no, date_str,
            idx + 1, r.get('product', ''), f"'{qty_str}",
            num(r.get('rate', 0)), num(r.get('disc_pct', 0)), num(r.get('gst_pct', 0)), num(r.get('amount', 0)),
            "", "", final_invoice
        ])
    return rows

def parse_zelig(text):
    # Zelig uses the generic extraction logic
    lines = clean_lines(text)
    supplier = 'ZELIG'
    invoice_no = extract_invoice_no(text)
    date_str = extract_date(text)
    customer = extract_customer(lines)
    items = parse_heuristic_items(lines)
    
    final_invoice = 0.0
    priority = [r'^GRAND\s*TOTAL', r'^NET\s*TOTAL', r'^TO\s*PAY']
    for pat in priority:
        for i, l in enumerate(lines):
            if re.search(pat, l, re.I):
                for j in range(i+1, min(i+6, len(lines))):
                    if re.match(r'^[\d.,+ ]+$', lines[j]):
                        final_invoice = num(lines[j])
                        break
                if final_invoice > 0: break
        if final_invoice > 0: break

    rows = []
    for idx, r in enumerate(items):
        qty_val = num(r.get('qty', 0))
        qty_str = str(int(qty_val)) if isinstance(qty_val, float) and qty_val.is_integer() else str(qty_val)
        
        rows.append([
            supplier, customer, invoice_no, date_str,
            idx + 1, r.get('product', ''), f"'{qty_str}",
            num(r.get('rate', 0)), num(r.get('disc_pct', 0)), num(r.get('gst_pct', 0)), num(r.get('amount', 0)),
            "", "", final_invoice
        ])
    return rows

def extract_with_custom_logic(text, supplier='ZELIG'):
    # Kept for backward compatibility if needed elsewhere
    return parse_zelig(text)

# --- OCR & File Handling ---

def ocr_pdf_to_text(pdf_path):
    dpi = 300
    psm = 4
    tmp_dir = tempfile.mkdtemp(prefix='billgen-ocr-')
    try:
        stem = os.path.join(tmp_dir, 'page')
        # Add BASE_DIR to PATH so DLLs in root can be found
        env = os.environ.copy()
        env["PATH"] = str(BASE_DIR) + os.pathsep + env.get("PATH", "")
        
        # Run pdftoppm
        subprocess.run([str(PDFTOPPM_EXE), '-r', str(dpi), '-png', str(pdf_path), stem], 
                       check=True, capture_output=True, env=env)
        
        # Run tesseract on each image
        pages_text = []
        imgs = sorted([f for f in os.listdir(tmp_dir) if f.endswith('.png')])
        for img in imgs:
            img_path = os.path.join(tmp_dir, img)
            # PSM 4 is good for tables
            res = subprocess.run([str(TESSERACT_EXE), img_path, 'stdout', '--psm', str(psm)], 
                                 capture_output=True, text=True, encoding='utf-8', errors='ignore', env=env)
            pages_text.append(res.stdout)
        
        return "\n".join(pages_text)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

def parse_kolkata(text):
    lines = clean_lines(text)
    invoice_no = extract_invoice_no(text)
    date_str = extract_date(text)
    
    # Extract expected item count to filter out extra rows
    expected_items = None
    m_items = re.search(r'Total\s*[iIl|1]tem[s]?(?:\s*[:-]+)?\s*(\d+)', text, re.I)
    if m_items:
        expected_items = int(m_items.group(1))
        
    skip_pat = re.compile(r'^THANE\s*MEDICAL\s*AGENCY|BUILDING|FARHAT|BANJARA|HILLS|GSTIN|PAN|DL NO|DLNO|REG NO|TSMC|FSSAI|STATE|CODE|TEL|MOBILE|EMAIL|@|SIGN|COPY|ERR|ORIGINAL|REPRINT|DESCRIPTION|RATES|AMOUNT|PCode|Inv\. No|Due Date|DUPLICATE|SHREE|NAMAHA|PAYMENT|RECORD|SCH\.AMT|DISC\.AMT|TAXABLE|TOTAL\s*AMT|ROUND\s*OFF|PERSON|SIGNATURE|TOTAL', re.I)
    
    # Improved customer extraction for Kolkata/Guwahati layout
    customer = "UNKNOWN"
    for line in lines[:8]:
        if 'THANE MEDICAL AGENCY' in line.upper():
            c = line.upper().replace('THANE MEDICAL AGENCY', '').strip()
            c = re.sub(r'ORIGINAL|DUPLICATE|COPY|REPRINT', '', c).strip()
            if c:
                customer = c
                break
    if customer == "UNKNOWN":
        customer = extract_customer(lines)
    
    # Summary values extraction (Grand Total)
    m = re.search(r'(?:GRAND\s*TOTAL|To\s*Pay|Total\s*Amt)[^\d]*([\d,.]+)', text, re.I)
    final_invoice = num(m.group(1)) if m else 0.0
    
    summary_keywords = ['TOTAL', 'GRAND', 'SGST', 'CGST', 'ROUND OFF', 'DISCOUNT', 'CN/DN', 'Goods Once Sold', 'CUSTOMER CARE']

    all_variants = []
    
    # --- Variant 1: Standard Kolkata (Pipes |) ---
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
                qty, taxable, gst_pct, rate = num(tokens[2]), num(tokens[-1]), num(tokens[-2]), num(tokens[-5])
                p_tokens = tokens[4 : date_idx - 1]
                product = " ".join(p_tokens).strip()
                product = clean_product_name(product)
                if is_valid_product(product):
                    # Merge logic for 0-amount rows
                    if taxable == 0 and items1 and items1[-1]['product'] == product:
                        prev = items1[-1]
                        new_qty = prev['qty'] + qty
                        prev['qty'] = new_qty
                        prev['disc_pct'] = round((1 - (prev['amount'] / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                    elif taxable > 0:
                        disc_pct = round((1 - (taxable / (qty * rate))) * 100, 2) if (qty * rate) > 0 else 0
                        items1.append({"product": product, "qty": qty, "rate": rate, "gst_pct": gst_pct, "amount": taxable, "disc_pct": disc_pct})
    all_variants.append(items1)

    # --- Variant 2: Summary / Record Invoice (No pipes, Sno with dot) ---
    items2 = []
    for line in lines:
        u_line = line.upper()
        if any(k in u_line for k in summary_keywords):
            continue
            
        tokens = line.split()
        if len(tokens) >= 6 and re.match(r'^\d+\.$', tokens[0]):
            qty, amount = num(tokens[1]), num(tokens[-1])
            date_idx = -1
            for k in range(len(tokens)-1, 1, -1):
                clean_t = re.sub(r'^[^0-9]+|[^0-9]+$', '', tokens[k])
                if re.match(r'^\d{1,2}/\d{2,4}$', clean_t):
                    date_idx = k
                    break
            if date_idx != -1:
                product = " ".join(tokens[2:date_idx-1]).strip()
                product = clean_product_name(product)
                if is_valid_product(product):
                    rate = round(amount / qty, 2) if qty > 0 else 0
                    items2.append({"product": product, "qty": qty, "rate": rate, "gst_pct": 18.0, "amount": amount, "disc_pct": 0})
    all_variants.append(items2)

    # --- Variant 3: Mumbai/Thane Layout (Manpada) ---
    items3 = []
    for line in lines:
        u_line = line.upper()
        if any(k in u_line for k in summary_keywords):
            continue
            
        if re.match(r'^[0-9Il1]+[\s.|!1]', line):
            toks = [t.strip() for t in re.split(r'[|!}\]\[\s]+', line) if t.strip()]
            if len(toks) >= 8:
                date_idx = -1
                for k in range(len(toks)-1, 1, -1):
                    clean_t = re.sub(r'^[^0-9]+|[^0-9]+$', '', toks[k])
                    if re.match(r'^\d{1,2}/\d{2,4}$', clean_t):
                        date_idx = k
                        break
                if date_idx != -1:
                    nums_after = [num(t) for t in toks[date_idx+1:] if (num(t) > 0 or t in ['0.00','0'])]
                    if len(nums_after) >= 2:
                        amount = nums_after[-1]
                        rate = 0
                        qty_guess = num(toks[1])
                        for r_guess in nums_after[1:-1]:
                            if r_guess > 0 and abs(qty_guess * r_guess - amount) < 10:
                                rate = r_guess; break
                        if rate == 0 and len(nums_after) >= 2:
                            rate = nums_after[2] if len(nums_after) >= 3 else nums_after[1]
                        qty = qty_guess
                        product = " ".join(toks[2:date_idx-1]).strip()
                        product = clean_product_name(product)
                        if is_valid_product(product):
                            # Merge logic
                            if amount == 0 and items3 and items3[-1]['product'] == product:
                                prev = items3[-1]
                                new_qty = prev['qty'] + qty
                                prev['qty'] = new_qty
                                prev['disc_pct'] = round((1 - (prev['amount'] / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                            elif amount > 0:
                                disc_pct = round((1 - (amount / (qty * rate))) * 100, 2) if (qty * rate) > 0 else 0
                                items3.append({"product": product, "qty": qty, "rate": rate, "gst_pct": 18.0, "amount": amount, "disc_pct": disc_pct})
    all_variants.append(items3)
    
    # --- Variant 4: Aggressive Same-Line Recovery ---
    items4 = []
    for line in lines:
        u_line = line.upper()
        if any(k in u_line for k in summary_keywords):
            continue
            
        toks = [t.strip() for t in re.split(r'[|!}\]\[\s]+', line) if t.strip()]
        if len(toks) >= 6:
            amt_r = num(toks[-1])
            if amt_r > 5:
                found_any = False
                for r_idx in range(-2, -7, -1):
                    if abs(r_idx) > len(toks): break
                    rate_r = num(toks[r_idx])
                    if rate_r > 50:
                        # Avoid choosing a duplicate taxable value as the rate!
                        if abs(rate_r - amt_r) < 1.0 and len(toks) > 8:
                            has_other_match = False
                            for other_idx in range(-2, -7, -1):
                                if abs(other_idx) > len(toks) or other_idx == r_idx: continue
                                rate_other = num(toks[other_idx])
                                if rate_other > 50 and rate_other != amt_r:
                                    qty_other = round(amt_r / rate_other, 0)
                                    if qty_other > 0 and qty_other < 5000 and (amt_r % rate_other < 2 or amt_r % rate_other > rate_other - 2):
                                        has_other_match = True; break
                            if has_other_match:
                                continue

                        qty_r = round(amt_r / rate_r, 0)
                        if qty_r > 0 and qty_r < 5000 and (amt_r % rate_r < 2 or amt_r % rate_r > rate_r - 2):
                            product_r = " ".join([t for t in toks[1:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                            if not product_r:
                                product_r = " ".join([t for t in toks[0:r_idx-2] if not re.match(r'^[\d.,]+$', t) and len(t) > 2])
                            product_r = clean_product_name(product_r)
                            if is_valid_product(product_r):
                                # Merge logic
                                if amt_r == 0 and items4 and items4[-1]['product'] == product_r:
                                    prev = items4[-1]
                                    new_qty = prev['qty'] + qty_r
                                    prev['qty'] = new_qty
                                    prev['disc_pct'] = round((1 - (prev['amount'] / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                                elif amt_r > 0:
                                    disc_pct = round((1 - (amt_r / (qty_r * rate_r))) * 100, 2) if (qty_r * rate_r) > 0 else 0
                                    items4.append({"product": product_r, "qty": qty_r, "rate": rate_r, "gst_pct": 18.0, "amount": amt_r, "disc_pct": disc_pct})
                                found_any = True
                                break
                if found_any: continue
    all_variants.append(items4)
    
    # Helper to deduplicate items
    def deduplicate_items(items_list):
        unique_items = []
        seen = set()
        for r in items_list:
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
        return unique_items

    dedup1 = deduplicate_items(items1)
    dedup2 = deduplicate_items(items2)
    dedup3 = deduplicate_items(items3)
    dedup4 = deduplicate_items(items4)

    variants = [dedup1, dedup2, dedup3, dedup4]
    
    unique_items = []
    if expected_items is not None and expected_items > 0:
        # Pick the variant that has the exact number of expected items
        exact_matches = [v for v in variants if len(v) == expected_items]
        if exact_matches:
            unique_items = exact_matches[0]
            print(f"  [TMA KOLKATA] Picked exact match variant with {expected_items} items")
        else:
            # Pick the one closest to expected_items
            def distance(v):
                l = len(v)
                if l >= expected_items:
                    return l - expected_items
                else:
                    return (expected_items - l) * 2
            
            unique_items = min(variants, key=distance)
            print(f"  [TMA KOLKATA] Picked closest variant with {len(unique_items)} items (expected {expected_items})")
            
            # Truncate if we still have more items than expected
            if len(unique_items) > expected_items:
                print(f"  [TMA KOLKATA] Truncating unique_items from {len(unique_items)} to {expected_items}")
                unique_items = unique_items[:expected_items]
    else:
        # Fallback to picking the variant with the most items
        unique_items = max(variants, key=len)
        print(f"  [TMA KOLKATA] No expected count found. Picked max variant with {len(unique_items)} items")

    # Format rows
    rows = []
    for r in unique_items:
        row = [
            "TMA (Kolkata/Guwahati/Mumbai)", customer, invoice_no, date_str, len(rows) + 1,
            r['product'], f"'{int(r['qty'])}", round_val(r['rate']), 
            r['disc_pct'], r['gst_pct'], round_val(r['amount']),
            "", "", round_val(final_invoice, 0)
        ]
        rows.append(row)
        
    return rows


def process_file(pdf_path, original_filename=''):
    # Try text extraction first via pdftotext -layout
    try:
        env = os.environ.copy()
        env["PATH"] = str(BASE_DIR) + os.pathsep + env.get("PATH", "")
        res = subprocess.run([str(PDFTOTEXT_EXE), '-layout', str(pdf_path), '-'], 
                             capture_output=True, text=True, encoding='utf-8', errors='ignore', env=env)
        text = res.stdout
    except Exception:
        text = ""
        
    text_len = len(re.sub(r'\s', '', text))
    rows = []
    source = "text"
    
    if text_len >= 50:
        supplier = detect_supplier(text, pdf_path, original_filename)
        if supplier == 'TMA_BANGALORE':
            rows = parse_tma(text)
            source = "text+tma"
        elif supplier == 'TMA_KOLKATA':
            rows = parse_kolkata(text)
            source = "text+tma_kol"
        elif supplier in ['SMA', 'GMD']:
            rows = parse_sma_gmd(text, supplier)
            source = f"text+{supplier.lower()}"
        else:
            rows = parse_zelig(text)
            source = "text+zelig"
            
    # CRITICAL: If text-based extraction returned 0 rows (junk text), fall back to OCR
    if not rows:
        print(f"  No rows found in text layer. Falling back to OCR...")
        text = ocr_pdf_to_text(pdf_path)
        supplier = detect_supplier(text, pdf_path, original_filename)
        if supplier == 'TMA_BANGALORE':
            rows = parse_tma(text)
            source = "ocr+tma"
        elif supplier == 'TMA_KOLKATA':
            rows = parse_kolkata(text)
            source = "ocr+tma_kol"
        elif supplier in ['SMA', 'GMD']:
            rows = parse_sma_gmd(text, supplier)
            source = f"ocr+{supplier.lower()}"
        else:
            rows = parse_zelig(text)
            source = "ocr+zelig"
            
    # Correct GST percentages using OCR correction rules
    def map_ocr_gst(gst_val):
        val = round(gst_val)
        if val in [0, 5, 12, 18, 28]:
            return float(val)
        if str(val).endswith('8'):
            return 18.0
        if str(val).endswith('2'):
            return 12.0
        standard_slabs = [0.0, 5.0, 12.0, 18.0, 28.0]
        return min(standard_slabs, key=lambda x: abs(x - gst_val))

    if rows:
        for row in rows:
            if len(row) > 9:
                try:
                    current_gst = float(str(row[9]).replace('%','').strip())
                    row[9] = map_ocr_gst(current_gst)
                except ValueError:
                    pass
            
    return rows, source

def main():
    if not INVOICE_FOLDER.exists():
        print(f"Folder '{INVOICE_FOLDER}' not found.")
        return
        
    pdf_files = list(INVOICE_FOLDER.rglob("*.pdf"))
    if not pdf_files:
        print("No PDF files found in 'invoices' folder.")
        return
        
    print(f"Found {len(pdf_files)} PDFs. Processing...\n")
    
    output_file = BASE_DIR / f"output_py_{int(time.time())}.csv"
    headers = ['Supplier', 'Customer', 'Invoice No', 'Date', 'S.No', 'Product', 'Qty', 'Rate', 'Dis%', 'GST%', 'Amount', 'CGST', 'SGST', 'Final Invoice']
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        
        for pdf_path in pdf_files:
            print(f"Processing: {pdf_path.name}...")
            try:
                rows, source = process_file(pdf_path)
                print(f"  Extracted {len(rows)} rows via {source}")
                for row in rows:
                    writer.writerow(row)
            except Exception as e:
                print(f"  Error: {e}")
                
    print(f"\nDone! Data saved to: {output_file}")

if __name__ == "__main__":
    main()
