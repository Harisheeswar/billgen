import os
import re
import json
import subprocess
import pandas as pd
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- Configuration & Paths ---
BASE_DIR = Path(__file__).parent.absolute()
INVOICE_FOLDER = BASE_DIR / "invoices"
POPPLER_DIR = BASE_DIR / "poppler-26.02.0"
PDFTOTEXT_EXE = POPPLER_DIR / "Library" / "bin" / "pdftotext.exe"

if not PDFTOTEXT_EXE.exists(): PDFTOTEXT_EXE = Path("pdftotext")

def num(s):
    if s is None: return 0.0
    try:
        clean = re.sub(r'[,%\s]', '', str(s))
        clean = re.sub(r'[^\d.-]', '', clean)
        if not clean or clean == '.': return 0.0
        return float(clean)
    except ValueError: return 0.0

def clean_lines(text):
    if not text: return []
    return [l for l in text.split('\n') if l.strip()]

def detect_supplier(text, original_filename=''):
    u = text.upper()
    f = original_filename.upper()
    if 'THANE MEDICAL' in u or 'TMA' in f: return 'TMA'
    if 'SHRADHA MEDICAL' in u or 'SMA' in f or re.match(r'^SMA\d+', original_filename, re.I): return 'SMA'
    if 'GOA MEDICAL' in u or 'GMD' in f or re.match(r'^GM(DC)?\d+', original_filename, re.I): return 'GMD'
    if 'ZELIG' in u or 'ZELIG' in f or re.match(r'^Z\d+', original_filename, re.I): return 'ZELIG'
    return 'UNKNOWN'

def extract_metadata(text):
    inv_no = 'UNKNOWN'
    date_str = 'UNKNOWN'
    m_inv = re.search(r'(?:Invoice\s*No\.?|Inv\.?\s*No\.?|Bill\s*No\.?|INV\.?\s*No\.?)\s*[:.-]?\s*([A-Z0-9\-/]+)', text, re.I)
    if m_inv:
        cand = m_inv.group(1).strip()
        if cand.upper() != "OICE": inv_no = cand
    if inv_no == 'UNKNOWN' or inv_no == 'OICE':
        m_zelig = re.search(r'Invoice\s*No\.?\s*[:.-]?\s*([A-Z0-9\-/]+)', text, re.I)
        if m_zelig: inv_no = m_zelig.group(1).strip()

    m_date = re.search(r'(?:Inv\.?\s*Date|Date)\s*[:.]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.I)
    if m_date: date_str = m_date.group(1).strip()
    m_pay = re.search(r'(?:To\s*Pay|Grand\s*Total|Net\s*Total)\s*[:.-]?\s*([\d,.]+)', text, re.I)
    final_invoice = num(m_pay.group(1)) if m_pay else 0.0
    return inv_no, date_str, final_invoice

def clean_name(name):
    if not name: return "UNKNOWN"
    name = re.split(r'\s{2,}', name)[0].strip()
    name = re.sub(r'[:;,]', '', name).strip()
    if any(k in name.upper() for k in ['GSTIN', 'EMAIL', 'PHONE', 'MOBILE', 'DL NO', 'DL.NO', 'FSSAI']): return "UNKNOWN"
    return name

def extract_customer_zelig_layout(text):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'Party Details' in line:
            idx = line.find('Party Details')
            if i + 1 < len(lines):
                next_line = lines[i+1]
                if len(next_line) > idx:
                    cand = next_line[idx:].strip()
                    cand = re.split(r'\s{4,}', cand)[0].strip()
                    if cand: return cand
    return "UNKNOWN"

def extract_customer_tma(text):
    m = re.search(r'(?:RECORD/PAYMENT COPY|TAX INVOICE).*\n\s*(.+)', text, re.I)
    if m:
        name = clean_name(m.group(1))
        if name != "UNKNOWN": return name
    lines = clean_lines(text)
    for i, line in enumerate(lines[:30]):
        if any(k in line.upper() for k in ['BILL TO', 'PARTY NAME', 'NAME :']):
            if i+1 < len(lines): return clean_name(lines[i+1])
    return "UNKNOWN"

def parse_tma(text, filename):
    lines_raw = clean_lines(text)
    inv_no, date_str, final_invoice = extract_metadata(text)
    customer = extract_customer_tma(text)
    items, in_table = [], False
    i = 0
    while i < len(lines_raw):
        line = lines_raw[i].strip()
        if 'QTY' in line.upper() and 'FREE' in line.upper() and 'PRODUCT' in line.upper(): in_table = True; i += 1; continue
        if in_table and any(k in line.upper() for k in ['FOR THANE MEDICAL', 'TOTAL', 'GRAND TOTAL', 'PAGE', 'CGST%', 'SGST%']):
            in_table = False; i += 1; continue
        if in_table:
            toks = line.split()
            if len(toks) >= 2:
                try:
                    qty, start_idx = 0.0, -1
                    if re.match(r'^\d+$', toks[0]): qty, start_idx = num(toks[0]), 0
                    elif len(toks) > 1 and re.match(r'^\d+$', toks[1]): qty, start_idx = num(toks[1]), 1
                    if 0 < qty < 1000:
                        disc_tok = toks[start_idx + 1]
                        disc_pct = num(disc_tok) if '%' in disc_tok else 0.0
                        combined_line = line
                        look_ahead = 0
                        while look_ahead < 3 and i + look_ahead < len(lines_raw):
                            test_line = lines_raw[i+look_ahead].strip()
                            if look_ahead > 0: combined_line += " " + test_line
                            all_nums = [num(t) for t in combined_line.split() if re.match(r'^[\d.]+$', t)]
                            if len(all_nums) >= 2:
                                best_rate, best_amt = 0.0, 0.0
                                for r_cand in [all_nums[-1], all_nums[-2] if len(all_nums)>1 else 0]:
                                    if r_cand <= 0: continue
                                    calc_a = (r_cand * qty * (1 - disc_pct/100)) * 1.18
                                    found_a = False
                                    for a_cand in all_nums:
                                        if abs(a_cand - calc_a) < 1.0: best_rate, best_amt = r_cand, a_cand; found_a = True; break
                                    if not found_a:
                                        mrp_cand = all_nums[-2] if len(all_nums)>1 else 0
                                        if r_cand > 50 and (mrp_cand == 0 or r_cand <= mrp_cand * 1.1):
                                            best_rate, best_amt = r_cand, round(calc_a, 2); found_a = True
                                    if found_a: break
                                if best_rate > 0:
                                    all_toks = combined_line.split()
                                    p_start = start_idx + 4 if '%' in disc_tok else start_idx + 3
                                    p_end = -1
                                    for k in range(len(all_toks)-1, p_start, -1):
                                        if re.match(r'^\d{2}/\d{2}$', all_toks[k]): p_end = k - 1; break
                                    if p_end == -1:
                                        for k in range(len(all_toks)-1, p_start, -1):
                                            if num(all_toks[k]) == best_rate: p_end = k-1; break
                                    if p_end == -1: p_end = len(all_toks) - 2
                                    product = " ".join(all_toks[p_start : p_end + 1]).strip()
                                    product = re.split(r'\s+[A-Z0-9\-]{6,}\s*$', product)[0].strip()
                                    if len(product) > 2 and 'HILLS' not in product.upper():
                                        # Calculate actual disc_pct from amount and rate
                                        taxable_amt = best_amt / 1.18
                                        actual_disc = round((1 - (taxable_amt / (qty * best_rate))) * 100, 2) if (qty * best_rate) > 0 else 0
                                        
                                        # Merge logic for 100% discount rows
                                        if best_amt == 0 and items and items[-1]['product'] == product:
                                            prev = items[-1]
                                            new_qty = float(prev['qty']) + qty
                                            prev['qty'] = str(int(new_qty))
                                            prev_taxable = prev['amount'] / 1.18
                                            prev['disc_pct'] = round((1 - (prev_taxable / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                                        elif best_amt > 0:
                                            items.append({"product": product, "qty": str(int(qty)), "rate": best_rate, "disc_pct": actual_disc, "gst_pct": 18.0, "amount": best_amt})
                                        
                                        i += look_ahead; break
                            look_ahead += 1
                except: pass
        i += 1
    return [["TMA", customer, inv_no, date_str, idx + 1, r['product'], r['qty'], r['rate'], r['disc_pct'], r['gst_pct'], r['amount'], "", "", final_invoice, filename] for idx, r in enumerate(items)]

def parse_zelig_layout(text, filename, supplier):
    lines = clean_lines(text)
    inv_no, date_str, final_invoice = extract_metadata(text)
    customer = extract_customer_zelig_layout(text)
    items, in_table = [], False
    for i, line in enumerate(lines):
        u = line.upper()
        if 'SR.' in u and 'HSN' in u and 'PRODUCT NAME' in u: in_table = True; continue
        if in_table and any(k in u for k in ['SUB TOTAL', 'SGST', 'CGST', 'GRAND TOTAL', 'AUTHORISED', 'REMARK']): in_table = False; break
        if in_table:
            toks = line.split()
            if len(toks) >= 10 and re.match(r'^\d+$', toks[0]):
                try:
                    sno = int(toks[0])
                    amt, gst, disc, rate = num(toks[-1]), num(toks[-2]), num(toks[-4]), num(toks[-5])
                    qty_str = toks[2]
                    
                    # Convert "5+1" to Total Qty=6 and calculate Free% -> Dis%
                    total_qty_val = 0
                    free_pct = 0.0
                    if '+' in qty_str:
                        parts = qty_str.split('+')
                        paid = int(parts[0]) if parts[0].strip() else 0
                        free = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
                        total_qty_val = paid + free
                        if total_qty_val > 0:
                            free_pct = round((free / total_qty_val) * 100, 2)
                    else:
                        total_qty_val = int(qty_str) if qty_str.isdigit() else 1
                    
                    # Merge Free% into Dis% column
                    if free_pct > 0 and disc == 0.0:
                        disc = free_pct
                    elif free_pct > 0 and disc > 0.0:
                        disc = round(disc + free_pct, 2)
                        
                    qty = str(total_qty_val)
                    
                    product = " ".join(toks[3:-6]).strip()
                    if (amt >= 0 or rate > 0) and len(product) > 3 and 'HILLS' not in product.upper():
                        # Use formula for Dis% to be safe
                        actual_disc = round((1 - (amt / (total_qty_val * rate))) * 100, 2) if (total_qty_val * rate) > 0 else 0
                        
                        # Merge logic for 100% discount rows
                        if amt == 0 and items and items[-1]['product'] == product:
                            prev = items[-1]
                            new_qty = int(prev['qty']) + total_qty_val
                            prev['qty'] = str(new_qty)
                            prev['disc'] = round((1 - (prev['amount'] / (new_qty * prev['rate']))) * 100, 2) if (new_qty * prev['rate']) > 0 else 0
                        elif amt > 0:
                            items.append({"sno": sno, "product": product, "qty": qty, "rate": rate, "disc": actual_disc, "gst": gst, "amount": amt})
                except: pass
    return [[supplier, customer, inv_no, date_str, r['sno'], r['product'], r['qty'], r['rate'], r['disc'], r['gst'], r['amount'], "", "", final_invoice, filename] for r in items]

def process_file_parallel(pdf_path):
    pdf_path = Path(pdf_path)
    filename = pdf_path.name
    try:
        env = os.environ.copy(); env["PATH"] = str(BASE_DIR) + os.pathsep + env.get("PATH", "")
        res = subprocess.run([str(PDFTOTEXT_EXE), '-layout', str(pdf_path), '-'], capture_output=True, text=True, encoding='utf-8', errors='ignore', env=env)
        text = res.stdout
        if len(re.sub(r'\s', '', text)) < 50: return []
        supplier = detect_supplier(text, filename)
        if supplier == 'TMA': return parse_tma(text, filename)
        if supplier in ['SMA', 'GMD', 'ZELIG']: return parse_zelig_layout(text, filename, supplier)
        return []
    except: return []

def main():
    if not INVOICE_FOLDER.exists(): print(f"Folder {INVOICE_FOLDER} not found."); return
    all_pdf_files = list(INVOICE_FOLDER.rglob("*.pdf"))
    unique_pdfs = {}
    for f in all_pdf_files:
        if f.name not in unique_pdfs: unique_pdfs[f.name] = f
    pdf_files = list(unique_pdfs.values())
    print(f"Found {len(all_pdf_files)} files. Unique PDFs to process: {len(pdf_files)}")
    
    output_jsonl = BASE_DIR / "extracted_data.jsonl"
    headers = ['Supplier', 'Customer', 'Invoice No', 'Date', 'S.No', 'Product', 'Qty', 'Rate', 'Dis%', 'GST', 'Amount', 'CGST', 'SGST', 'Final Invoice', 'PDF Name']
    
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        with ProcessPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(process_file_parallel, str(pdf)): pdf.name for pdf in pdf_files}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                rows = future.result()
                if rows:
                    for r in rows: f.write(json.dumps(dict(zip(headers, r))) + "\n")
                if done_count % 100 == 0:
                    f.flush()
                    print(f"[{done_count}/{len(pdf_files)}] Processed...")
            
    print("\nExtraction complete. Building final Excel...")
    data = []
    if output_jsonl.exists():
        with open(output_jsonl, 'r', encoding='utf-8') as f:
            for line in f:
                try: data.append(json.loads(line))
                except: continue
    if data:
        df = pd.DataFrame(data)
        df.drop_duplicates(subset=['Invoice No', 'S.No', 'Product', 'Qty'], keep='first', inplace=True)
        timestamp = int(time.time())
        output_xlsx = BASE_DIR / f"extracted_invoices_{timestamp}.xlsx"
        try:
            df.to_excel(output_xlsx, index=False)
            print(f"Success! All data saved to: {output_xlsx}")
        except:
            print("Failed to save final file.")

if __name__ == "__main__":
    main()
