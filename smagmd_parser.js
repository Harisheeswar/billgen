// Bulletproof parser for SMA and GMD invoices.
const num = s => {
  if (s == null) return 0;
  const v = parseFloat(String(s).replace(/,/g, '').replace(/[^\d.-]/g, '').trim());
  return Number.isFinite(v) ? v : 0;
};

export function parseSMAGMD(text, supplier = 'SMA') {
  const rawLines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const lines = [];
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
  const skipWords = ["LOC", "QTY", "HSN", "EXP", "MRP", "MFG", "MFGR", "PACK", "RATE", "FREE", "DESC", "TOTAL", "SR. HSN", "PRODUCT NAME", "SR NO", "HSN CODE", "HILLS"];
  
  let inTable = false;
  let chunk = [];
  let nextSno = 1;

  const processChunk = (c, sno) => {
    if (c.length < 3) return;
    
    // In GMD/SMA, HSN is often the first element after Sno, then Qty, then Product
    // Or sometimes Product is before Qty.
    // Let's use a more flexible approach.
    
    let qty = 0, product = '', rate = 0, amount = 0, hsn = '';
    
    // Find numeric tokens at the end (Rate and Amount)
    const numericTokens = c.filter(t => /^-?[\d,.]+(?:\s*%|%?)$/.test(t) && !t.includes('/')).map(num);
    if (numericTokens.length >= 2) {
      amount = numericTokens[numericTokens.length - 1];
      rate = numericTokens[numericTokens.length - 2];
    }

    // Qty is often at the beginning or after HSN
    for (let i = 0; i < Math.min(c.length, 3); i++) {
      if (/^\d+(\+\d+)?$/.test(c[i])) {
        qty = c[i];
        break;
      }
    }
    
    // Product is the longest non-numeric string
    const textTokens = c.filter(t => !/^-?[\d,.]+(?:\s*%|%?)$/.test(t) && !skipWords.includes(t.toUpperCase()) && t.length > 3);
    product = textTokens.join(' ').trim();

    if (product) {
      if (amount === 0 && items.length > 0 && items[items.length - 1].product === product) {
        const prev = items[items.length - 1];
        const prevQty = String(prev.qty).includes('+') ? prev.qty.split('+').reduce((a, b) => a + num(b), 0) : num(prev.qty);
        const currQty = String(qty).includes('+') ? qty.split('+').reduce((a, b) => a + num(b), 0) : num(qty);
        prev.qty = String(prevQty + currQty);
      } else if (amount >= 0) {
        items.push({ product, qty, rate, amount, sno });
      }
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const upLine = lines[i].toUpperCase();
    if (upLine.includes("SR. HSN") || upLine.includes("PRODUCT NAME") || upLine.includes("HSN       QTY") || upLine.includes("ITEM DESCRIPTION") || upLine.includes("MFGR")) {
      inTable = true; continue;
    }
    if (inTable && (upLine.includes("SUB TOTAL") || upLine.includes("TOTAL") || upLine.includes("GRAND") || upLine.includes("REMARK"))) {
      if (chunk.length > 0) processChunk(chunk, nextSno - 1);
      inTable = false; break;
    }
    if (inTable) {
      const isNextSno = lines[i] === String(nextSno) || lines[i] === String(nextSno).padStart(2, '0');
      if (isNextSno) {
        if (chunk.length > 0) processChunk(chunk, nextSno - 1);
        chunk = []; nextSno++;
      } else {
        // Skip some reference codes if needed
        if (/^CA\d{4,}/i.test(lines[i])) continue;
        chunk.push(lines[i]);
      }
    }
  }
  // Process last chunk if still in table
  if (inTable && chunk.length > 0) processChunk(chunk, nextSno - 1);

  return items.map(r => {
    const qtyVal = String(r.qty).includes('+') ? r.qty.split('+').reduce((a, b) => a + num(b), 0) : num(r.qty);
    const discPct = round((1 - (r.amount / (qtyVal * r.rate))) * 100, 2);
    return [
      supplier, customer, invoiceNo, dateStr, r.sno, r.product, "'" + qtyVal, r.rate, discPct, 0, r.amount, "", "", finalInvoice
    ];
  });
}
