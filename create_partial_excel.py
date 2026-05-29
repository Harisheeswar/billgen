import pandas as pd
import json
import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()
JSONL_FILE = BASE_DIR / "extracted_data.jsonl"

def main():
    if not JSONL_FILE.exists():
        print("JSONL file not found yet.")
        return
    
    timestamp = int(time.time())
    EXCEL_FILE = BASE_DIR / f"extracted_invoices_FINAL_{timestamp}.xlsx"

    try:
        data = []
        with open(JSONL_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data.append(json.loads(line))
                except:
                    continue
        
        if data:
            df = pd.DataFrame(data)
            # Final deduplication
            df.drop_duplicates(subset=['Invoice No', 'S.No', 'Product', 'Qty'], keep='first', inplace=True)
            df.to_excel(EXCEL_FILE, index=False)
            print(f"Final Excel created: {EXCEL_FILE}")
        else:
            print("No data found in JSONL yet.")
    except Exception as e:
        print(f"Error creating final Excel: {e}")

if __name__ == "__main__":
    main()
