// Final, bulletproof parser for TMA invoices.
const num = s => {
  if (s == null) return 0;
  const v = parseFloat(String(s).replace(/,/g, '').replace(/[^\d.-]/g, '').trim());
  return Number.isFinite(v) ? v : 0;
};
const round = (x, n = 2) => Math.round(x * Math.pow(10, n)) / Math.pow(10, n);

export function parseTMA(text) {
  const allLines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const lines = [];
  for (let i = 0; i < allLines.length; i++) {
    if (i === 0 || allLines[i] !== allLines[i-1]) lines.push(allLines[i]);
  }
  
  let invoiceNo = 'UNKNOWN', dateStr = 'UNKNOWN', customer = 'UNKNOWN', finalInvoice = 0;
  let cgst = 0, sgst = 0, taxableTotal = 0, foundTax = false;

  for (const l of lines) {
    const invM = l.match(/Invoice\s*No\.?\s*[:\.]?\s*([A-Z0-9\-\/]+)/i) || l.match(/Inv\.?\s*No\.?\s*(\d+)/i);
    if (invM && invoiceNo === 'UNKNOWN') invoiceNo = invM[1];
    const dateM = l.match(/Date\s*[:\.]?\s*(\d{1,2}[\-\/]\d{1,2}[\-\/]\d{2,4})/i);
    if (dateM && dateStr === 'UNKNOWN') dateStr = dateM[1];
    const payM = l.match(/To\s*Pay\s*[:\-]?\s*([\d,]+(?:\.\d+)?)/i);
    if (payM) finalInvoice = num(payM[1]);

    const nums = l.split(/\s+/).filter(p => /^[\d,.]+$/.test(p)).map(num);
    if (nums.length >= 7) {
       const c = nums[nums.length - 3], s = nums[nums.length - 2];
       if (c > 0 && s > 0 && Math.abs(c - s) < 1) {
          cgst = Math.max(cgst, c); sgst = Math.max(sgst, s); foundTax = true;
       }
    }
    if (l.length > 30 && /^[\d.]+$/.test(l)) {
       const tokens = l.split(/(\d+\.\d{1,2})/).filter(t => t.includes('.')).map(num);
       if (tokens.length >= 3) {
          const s1 = tokens[tokens.length - 2], c1 = tokens[tokens.length - 3];
          if (c1 > 0 && s1 > 0 && Math.abs(c1 - s1) < 1) {
             cgst = c1; sgst = s1; foundTax = true;
          }
       }
    }
  }

  // Improved Customer logic
  const skip = /THANE|BUILDING|FARHAT|BANJARA|HILLS|GSTIN|PAN|DL NO|DLNO|REG NO|TSMC|FSSAI|STATE|CODE|TEL|MOBILE|EMAIL|@|SIGN|COPY|ERR|ORIGINAL|REPRINT|DESCRIPTION|RATES|AMOUNT|PCode|Inv\. No|Due Date|DUPLICATE|SHREE|NAMAHA|PAYMENT|RECORD|SCH\.AMT|DISC\.AMT|TAXABLE|TOTAL\s*AMT/i;
  for (let i = 0; i < Math.min(lines.length, 200); i++) {
    const l = lines[i];
    if (skip.test(l) || l.length < 5) continue;
    if (/^(DR\.?|MR\.?|MRS\.?|MS\.?|M\/S\.?|SHRI|SMT\.?|PHARMACY|MEDICAL|HOSPITAL|CLINIC|EYE|SKIN|HEALTH|SRI|SHRI|SIDDISAI)/i.test(l)) {
       customer = l;
       if (lines[i+1] && !skip.test(lines[i+1]) && lines[i+1].length > 10 && !/^[A-Z]{3,4}$/.test(lines[i+1])) {
          customer += ' ' + lines[i+1];
       }
       break;
    }
    if (/^[A-Z\.\s]{10,}$/.test(l) && !skip.test(l)) {
       customer = l; break;
    }
  }

  const items = [];
  const HEADER_WORDS = new Set(['MFGR', 'LOC', 'QTY', 'FREE', 'HSN', 'PACK', 'BATCH', 'EXP', 'GST', 'GST%', 'MRP', 'RATES', 'AMOUNT', 'PRODUCT', 'DESCRIPTION', 'PCODE', 'DL', 'REG', 'TSMC', 'FSSAI']);
  let lastProduct = '';

  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^[A-Z]{2,6}$/.test(l) && !HEADER_WORDS.has(l.toUpperCase())) {
       const block = lines.slice(i, i + 15);
       let bestK = -1, bestScore = -1;

       for (let k = 7; k < 13; k++) {
          const gstToken = block[k-1], mrpToken = block[k], rateToken = block[k+1], amtToken = block[k+2];
          if (gstToken?.includes('/') || mrpToken?.includes('/') || rateToken?.includes('/') || amtToken?.includes('/')) continue;
          if (gstToken?.includes(':') || mrpToken?.includes(':') || rateToken?.includes(':') || amtToken?.includes(':')) continue;

          const gst = num(gstToken), mrp = num(mrpToken), rate = num(rateToken), amt = num(amtToken);
          if (amt > 0 && rate > 0 && mrp > 0 && amt < 1000000) {
             let score = 0;
             if ([0, 5, 12, 18, 28].includes(gst)) score += 10;
             if (amt >= rate && amt >= mrp) score += 5;
             if (rate <= mrp * 1.5) score += 5;
             if (score > bestScore) { bestScore = score; bestK = k; }
          }
       }

       if (bestK > 0) {
          const k = bestK;
          const gst = num(block[k-1]), mrp = num(block[k]), rate = num(block[k+1]), amt = num(block[k+2]);
          const qty = num(block[1]);
          let disc = num(block[2]);
          // If the disc value looks like an HSN (3004, 3304), it's probably not a discount
          if (disc >= 1000) disc = 0;
          
          let product = '';
          const productParts = block.slice(5, k-1);
          const filteredParts = productParts.filter(p => /[A-Za-z]{3,}/.test(p) && !/^\d+YI|^\d+\/\d+|^[A-Z0-9]{8,}|DL\s*NO|FSSAI/i.test(p));
          
          if (filteredParts.length > 0) {
             product = filteredParts.join(' ').trim();
             lastProduct = product;
          } else if (lastProduct) {
             // Fallback to last product name if current row only contains batch info
             product = lastProduct;
          } else {
             product = productParts.join(' ').trim();
          }

          if (product && !skip.test(product)) {
             const total_qty = num(qty) + disc;
             // Merge logic for 0-amount (100% discount) rows
             if (amt === 0 && items.length > 0 && items[items.length - 1].product === product) {
               const prev = items[items.length - 1];
               const newQty = prev.qty + total_qty;
               prev.qty = newQty;
               prev.disc_pct = round((1 - (prev.amount / (newQty * prev.rate))) * 100, 2);
             } else if (amt > 0) {
               const calculated_disc = round((1 - (amt / (total_qty * rate))) * 100, 2);
               items.push({ product, qty: total_qty, rate, gst_pct: gst, amount: amt, disc_pct: calculated_disc });
               taxableTotal += amt;
             }
             i += k + 2;
             continue;
          }
       }
    }

    const tokens = l.includes('|') ? l.split('|').map(s => s.trim()).filter(Boolean) : l.split(/\s+/).filter(Boolean);
    if (tokens.length >= 10) {
       const last = tokens.length - 1;
       const amt = num(tokens[last]), rate = num(tokens[last - 1]), gst = num(tokens[last - 3]);
       if (amt > 0 && rate > 0 && amt < 1000000) {
          let qty = 0, product = '', disc = 0;
          if (/^\d+$/.test(tokens[1])) { 
             qty = num(tokens[1]); 
             disc = num(tokens[2]); if (disc >= 1000) disc = 0;
             product = tokens.slice(6, last - 3).filter(p => /[A-Za-z]{3,}/.test(p)).join(' ').trim();
             if (!product && lastProduct) product = lastProduct;
             else if (product) lastProduct = product;
          }
          else if (/^\d+$/.test(tokens[2])) { 
             qty = num(tokens[2]); 
             disc = num(tokens[3]); if (disc >= 1000) disc = 0;
             product = tokens.slice(7, last - 3).filter(p => /[A-Za-z]{3,}/.test(p)).join(' ').trim();
             if (!product && lastProduct) product = lastProduct;
             else if (product) lastProduct = product;
          }
          if (product && !skip.test(product)) {
             const total_qty = qty + disc;
             // Merge logic for 0-amount rows
             if (amt === 0 && items.length > 0 && items[items.length - 1].product === product) {
               const prev = items[items.length - 1];
               const newQty = prev.qty + total_qty;
               prev.qty = newQty;
               prev.disc_pct = round((1 - (prev.amount / (newQty * prev.rate))) * 100, 2);
             } else if (amt > 0) {
               const calculated_disc = round((1 - (amt / (total_qty * rate))) * 100, 2);
               items.push({ product, qty: total_qty, rate, gst_pct: gst, amount: amt, disc_pct: calculated_disc });
               taxableTotal += amt;
             }
          }
       }
    }
    i++;
  }

  if (!foundTax && taxableTotal > 0) {
     const totalGst = taxableTotal * ( (items[0]?.gst_pct || 18) / 100 );
     cgst = round(totalGst / 2); sgst = round(totalGst / 2);
     if (finalInvoice === 0) finalInvoice = Math.round(taxableTotal + totalGst);
  }

  return items.map((r, idx) => [
    'TMA', customer, invoiceNo, dateStr, idx + 1, r.product, "'" + r.qty, r.rate, r.disc_pct, r.gst_pct, r.amount, "", "", finalInvoice
  ]);
}
