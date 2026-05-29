// Bulletproof parser for Zelig invoices.
const num = s => {
  if (s == null) return 0;
  const v = parseFloat(String(s).replace(/,/g, '').replace(/[^\d.-]/g, '').trim());
  return Number.isFinite(v) ? v : 0;
};

export function parseZelig(text) {
  const rawLines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const lines = [];
  // Deduplicate lines (pdf-parse often doubles them)
  for (let i = 0; i < rawLines.length; i++) {
    if (i === 0 || rawLines[i] !== rawLines[i-1]) lines.push(rawLines[i]);
  }

  let invoiceNo = 'UNKNOWN', dateStr = 'UNKNOWN', customer = 'UNKNOWN', finalInvoice = 0;
  
  // Robust metadata extraction
  const invM = text.match(/(?:Invoice\s*No\.?|Inv\.?\s*No\.?|Bill\s*No\.?|INV\.?)\s*[:\.]?\s*([\w\-\/]+)/i);
  if (invM) invoiceNo = invM[1].trim();

  const dateM = text.match(/(?:Inv\.?\s*Date|Date)\s*[:\.]?\s*(\d{1,2}[\-\/]\d{1,2}[\-\/]\d{2,4})/i);
  if (dateM) dateStr = dateM[1].trim();

  const payM = text.match(/(?:To\s*Pay|Grand\s*Total|Net\s*Total)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)/i);
  if (payM) finalInvoice = num(payM[1]);

  // Customer extraction
  for (let i = 0; i < Math.min(lines.length, 60); i++) {
    const upL = lines[i].toUpperCase();
    if (upL.includes("PARTY DETAILS") || upL.includes("BILL TO") || upL.includes("PARTY NAME") || upL.includes("NAME :") || upL.includes("PATIENT NAME")) {
      customer = lines[i+1] || "UNKNOWN"; 
      break;
    }
  }

  const items = [];
  let nextSno = 1;
  let i = 0;

  while (i < lines.length) {
    if (lines[i] === String(nextSno) || lines[i] === String(nextSno).padStart(2, '0')) {
      // Zelig format typically has:
      // Sno
      // HSN
      // Qty
      // Pack
      // MFGR
      // Product Name
      // Expiry
      // Batch
      // MRP
      // Rate
      // Disc %
      // CD %
      // GST %
      // Amount
      
      const block = lines.slice(i, i + 18);
      let qty = '0', product = '', rate = 0, amount = 0, gst = 0, disc = 0;
      
      // Look for the numeric tail
      // Amount is usually the last numeric value before the next Sno or end markers
      let bestK = -1;
      for (let k = 8; k < 15; k++) {
        if (block[k] && /^\d+\.\d{2}$/.test(block[k])) {
           // Possible amount or rate
           if (block[k+1] && /^\d+\.\d{2}$/.test(block[k+1])) {
              // k might be rate, k+1 might be disc, or k is disc, k+1 is gst...
              // In Zelig, it's often: ... MRP(8), Rate(9), Disc(10), CD(11), GST(12), Amount(13)
           }
        }
      }
      
      // Heuristic for Zelig block parsing
      qty = block[2];
      product = block[5];
      rate = num(block[9]);
      disc = num(block[10]);
      gst = num(block[12]);
      amount = num(block[13]);
      
      // Sanity check
      if (product && product.length > 3) {
        if (amount === 0 && items.length > 0 && items[items.length - 1].product === product) {
           const prev = items[items.length - 1];
           prev.qty = String(num(prev.qty) + num(qty));
        } else if (amount > 0) {
           items.push({ product, qty, rate, disc, gst, amount, sno: nextSno });
           nextSno++;
        }
        i += 13; // Skip the processed block
      }
    }
    i++;
  }

  // If sequential block parsing failed, fallback to recovery items
  if (items.length === 0) {
     // Fallback to recovery items logic from extractor.py if needed
  }

  return items.map(r => {
    const qtyVal = num(r.qty);
    const discPct = round((1 - (r.amount / (qtyVal * r.rate))) * 100, 2);
    return [
      'ZELIG', customer, invoiceNo, dateStr, r.sno, r.product, "'" + qtyVal, r.rate, discPct, r.gst, r.amount, "", "", finalInvoice
    ];
  });
}
