import express from 'express';
import pdf from 'pdf-parse';
import path from 'path';
import os from 'os';
import fs from 'fs';
import { fileURLToPath } from 'url';
import cors from 'cors';
import { ocrPdfToText, getOcrToolPaths } from './ocr_extractor.js';
import { parseTMA } from './tma_parser.js';
import { parseSMAGMD } from './smagmd_parser.js';
import { parseZelig } from './zelig_parser.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(cors());
app.use(express.json({ limit: '100mb' }));

function cleanLines(text) {
  const all = text.split('\n').map(l => l.trim());
  let kept = all;
  if (all.length >= 4) {
    let pairs = 0, total = 0;
    for (let i = 0; i + 1 < all.length; i += 2) {
      total++;
      if (all[i] === all[i + 1]) pairs++;
    }
    if (total > 0 && pairs / total >= 0.8) {
      kept = all.filter((_, i) => i % 2 === 0);
    }
  }
  return kept.filter(l => l !== '');
}

const num = s => {
  if (s == null) return 0;
  const v = parseFloat(String(s).replace(/,/g, '').replace(/[^\d.-]/g, '').trim());
  return Number.isFinite(v) ? v : 0;
};

const isPureNumber = s =>
  typeof s === 'string' && /^-?\d+(\.\d+)?$/.test(s.replace(/,/g, '').trim());

function detectSupplier(text, fileName = '') {
  const u = text.toUpperCase();
  const f = fileName.toUpperCase();
  if (u.includes('THANE MEDICAL') || f.includes('TMA')) return 'TMA';
  if (u.includes('SHRADHA MEDICAL') || f.includes('SMA')) return 'SMA';
  if (u.includes('GOA MEDICAL') || f.includes('GMD')) return 'GMD';
  return 'ZELIG';
}

function extractInvoiceNo(text) {
  const m = text.match(/Invoice\s*No\.?\s*[:\.]?\s*([A-Z0-9\-\/]+)/i)
        || text.match(/\b(?:Inv\.?No|Bill\s*No\.?)\s*[:\.]?\s*([A-Z0-9\-\/]+)/i);
  return m ? m[1].trim() : 'UNKNOWN';
}

function extractDate(text) {
  const m = text.match(/(?:^|\n)\s*Date\s*[:\.]?\s*(\d{1,2}[\-\/]\d{1,2}[\-\/]\d{2,4})/i)
        || text.match(/(?:Inv\.?Date|Bill\s*Date|Date)\s*[:\.]?\s*(\d{1,2}[\-\/]\d{1,2}[\-\/]\d{2,4})/i);
  return m ? m[1].trim() : 'UNKNOWN';
}

function extractCustomer(lines) {
  const skip = /THANE|BUILDING|FARHAT|BANJARA|GSTIN|PAN|DL NO|DLNO|REG NO|TSMC|FSSAI|STATE|CODE|TEL|MOBILE|EMAIL|@|SIGN|COPY|ERR|ORIGINAL|REPRINT|DESCRIPTION|RATES|AMOUNT|PCode|Inv\. No|Due Date|DUPLICATE|SHREE|NAMAHA|PAYMENT|RECORD|SCH\.AMT|DISC\.AMT|TAXABLE|TOTAL\s*AMT/i;
  for (let i = 0; i < Math.min(lines.length, 100); i++) {
    const l = lines[i].trim();
    if (skip.test(l) || l.length < 5) continue;
    if (/^(DR\.?|MR\.?|MRS\.?|MS\.?|M\/S\.?|SHRI|SMT\.?|PHARMACY|MEDICAL|HOSPITAL|CLINIC|EYE|SKIN|HEALTH|SRI|SHRI|SIDDISAI)/i.test(l)) {
       let customer = l;
       if (lines[i+1] && !skip.test(lines[i+1]) && lines[i+1].length > 10 && !/^[A-Z]{3,4}$/.test(lines[i+1])) {
          customer += ' ' + lines[i+1];
       }
       return customer;
    }
    if (/^[A-Z\.\s]{10,}$/.test(l) && !skip.test(l)) return l;
  }
  return 'UNKNOWN';
}

function extractCgstSgst(lines) {
  let cgst = 0, sgst = 0;
  for (let i = 0; i < lines.length; i++) {
    const u = lines[i].trim().toUpperCase();
    if (/^CGST(\s|$|:)/.test(u)) {
      for (let j = i + 1; j < Math.min(i + 4, lines.length); j++) {
        if (isPureNumber(lines[j])) { cgst += num(lines[j]); break; }
      }
    }
    if (/^SGST(\s|$|:)/.test(u)) {
      for (let j = i + 1; j < Math.min(i + 4, lines.length); j++) {
        if (isPureNumber(lines[j])) { sgst += num(lines[j]); break; }
      }
    }
  }
  if (cgst > 0 || sgst > 0) return { cgst: +cgst.toFixed(2), sgst: +sgst.toFixed(2) };

  const fullText = lines.join('\n');
  const gstMatch = fullText.match(/\bGST\b[\s\n]+([\d,.]+)/i);
  if (gstMatch) {
    const total = num(gstMatch[1]);
    return { sgst: +(total / 2).toFixed(2), cgst: +(total / 2).toFixed(2) };
  }
  return { sgst: 0, cgst: 0 };
}

// ─────────────────────────────────────────────────────────────────────────────
// extractTmaSummary — reads CGST, SGST and final invoice total DIRECTLY from
// the GST-slab summary table printed at the bottom of every TMA invoice.
//
// TMA format (one row per GST slab):
//   <rate>%  <gross>  <scheme>  <cd>  <taxable>  <cgst_amt>  <sgst_amt>  <row_total>
//
// Previous bugs fixed:
//   Bug 1 — .match() returned only the FIRST 7-token sequence ("0% 0 0 0 0 0 0")
//            so cgst=0, function returned null, override silently skipped.
//   Bug 2 — TMA PDFs print 3-4 copies of each invoice on one page, so same
//            slab row appears 4x, multiplying totals by 4 (1696.05 x4 = 6784.20)
//
// Fix: iterate ALL matches with /g, skip zero rows, deduplicate by value.
// ─────────────────────────────────────────────────────────────────────────────
function extractTmaSummary(text, invoiceNo) {
  const label = `[TMA ${invoiceNo}]`;
  const NUM = '(\\d[\\d,]*\\.?\\d*)';
  const SEP = '\\s+';
  const pat = new RegExp(NUM+SEP+NUM+SEP+NUM+SEP+NUM+SEP+NUM+SEP+NUM+SEP+NUM, 'g');

  let m;
  let totalCgst = 0, totalSgst = 0, found = false, lastRowTotal = 0;
  const seen = new Set();

  console.log(`\n${label} ── Scanning GST slab table ──────────────────`);

  while ((m = pat.exec(text)) !== null) {
    const gross     = num(m[1]);
    const scheme    = num(m[2]);
    const cd        = num(m[3]);
    const taxable   = num(m[4]);
    const maybeCgst = num(m[5]);
    const maybeSgst = num(m[6]);
    const rowTotal  = num(m[7]);

    if (maybeCgst === 0 && maybeSgst === 0) continue;

    const key = `${gross}|${scheme}|${taxable}|${maybeCgst}|${maybeSgst}|${rowTotal}`;
    if (seen.has(key)) {
      console.log(`${label}   SKIP duplicate: gross=${gross} taxable=${taxable} cgst=${maybeCgst} sgst=${maybeSgst}`);
      continue;
    }
    seen.add(key);

    const taxableOk = Math.abs((gross - scheme - cd) - taxable) < 2;
    const totalOk   = Math.abs((taxable + maybeCgst + maybeSgst) - rowTotal) < 2;

    console.log(`${label}   ROW  gross=${gross}  scheme=${scheme}  cd=${cd}  taxable=${taxable}  cgst=${maybeCgst}  sgst=${maybeSgst}  rowTotal=${rowTotal}`);
    console.log(`${label}        CHECK gross-scheme-cd=${+(gross-scheme-cd).toFixed(2)} vs taxable=${taxable} → taxableOk=${taxableOk}`);
    console.log(`${label}        CHECK taxable+cgst+sgst=${+(taxable+maybeCgst+maybeSgst).toFixed(2)} vs rowTotal=${rowTotal} → totalOk=${totalOk}`);

    if (!taxableOk || !totalOk) {
      console.log(`${label}   SKIP (sanity check failed)`);
      continue;
    }

    totalCgst   += maybeCgst;
    totalSgst   += maybeSgst;
    lastRowTotal = rowTotal;
    found = true;
    console.log(`${label}   ACCEPTED ✓   running CGST=${+totalCgst.toFixed(2)}  SGST=${+totalSgst.toFixed(2)}`);
  }

  const toPayMatch = text.match(/To\s*Pay\s*[:\.]?\s*([\d,]+)/i)
                  || text.match(/Grand\s*Total\s*[:\.]?\s*([\d,]+)/i);
  const finalInvoice = toPayMatch ? num(toPayMatch[1]) : lastRowTotal;

  console.log(`${label} ── RESULT ────────────────────────────────────`);
  if (!found) {
    console.log(`${label}   WARNING: no valid slab found — CGST/SGST not overridden`);
    return null;
  }
  console.log(`${label}   CGST = ${+totalCgst.toFixed(2)}`);
  console.log(`${label}   SGST = ${+totalSgst.toFixed(2)}`);
  console.log(`${label}   FinalInvoice = ${finalInvoice}  (from "To Pay")`);
  console.log(`${label} ──────────────────────────────────────────────\n`);

  return {
    cgst:         +totalCgst.toFixed(2),
    sgst:         +totalSgst.toFixed(2),
    finalInvoice,
  };
}

function extractFinalInvoice(lines) {
  const priority = [/^GRAND\s*TOTAL/i, /^NET\s*TOTAL/i, /^TO\s*PAY/i];
  for (const re of priority) {
    for (let i = 0; i < lines.length; i++) {
      if (re.test(lines[i].trim())) {
        for (let j = i + 1; j < Math.min(i + 6, lines.length); j++) {
          if (isPureNumber(lines[j])) return num(lines[j]);
        }
      }
    }
  }
  return 0;
}

function parseStructuredItems(lines) {
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].toUpperCase().includes('PRODUCT NAME')) { start = i + 1; break; }
  }
  if (start < 0) return null;
  const endMarkers = ['SUB TOTAL', 'GRAND TOTAL', 'NET TOTAL', 'CLASS', 'AUTHORISED'];
  const items = [];
  let sno = 1;
  let i = start;
  while (i < lines.length) {
    let k = -1;
    for (let j = i; j < Math.min(lines.length, i + 40); j++) {
      const u = lines[j].toUpperCase();
      if (endMarkers.some(m => u.includes(m))) { j = lines.length; break; }
      if (lines[j].trim() === String(sno) || lines[j].trim() === String(sno).padStart(2, '0')) {
        if (j + 1 < lines.length && /^\d{4,}$/.test(lines[j + 1].trim())) { k = j; break; }
      }
    }
    if (k < 0 || k + 13 >= lines.length) break;
    items.push({
      sno,
      hsn:      lines[k + 1].trim(),
      qty:      lines[k + 2].trim(),
      pack:     lines[k + 3].trim(),
      mfg:      lines[k + 4].trim(),
      product:  lines[k + 5].trim(),
      exp:      lines[k + 6].trim(),
      batch:    lines[k + 7].trim(),
      mrp:      num(lines[k + 8]),
      rate:     num(lines[k + 9]),
      disc_pct: num(lines[k + 10]),
      cd_pct:   num(lines[k + 11]),
      gst_pct:  num(lines[k + 12]),
      amount:   num(lines[k + 13]),
    });
    sno++;
    i = k + 14;
  }
  return items.length ? items : null;
}

function parseHeuristicItems(lines) {
  const items = [];
  let inTable = false, nextSno = 1;
  for (let i = 0; i < lines.length; i++) {
    const u = lines[i].toUpperCase();
    if (u.includes('PRODUCT NAME')) { inTable = true; continue; }
    if (inTable && (u.includes('SUB TOTAL') || u === 'TOTAL')) break;
    if (inTable && (lines[i] === String(nextSno) || lines[i] === String(nextSno).padStart(2, '0'))) {
      const r = { sno: nextSno, qty: lines[i + 2] || '1' };
      let j = i + 3;
      const block = [];
      while (j < lines.length && j < i + 18) {
        if (lines[j] === String(nextSno + 1) || lines[j] === String(nextSno + 1).padStart(2, '0')) break;
        if (lines[j].toUpperCase().includes('TOTAL')) break;
        block.push(lines[j]); j++;
      }
      const nameTokens = [];
      for (const t of block) {
        if (/^\d+(MG|ML|GM|S|CAPS|TABS)$/i.test(t)) continue;
        if (/^[A-Z]{3,5}$/.test(t) && !/^(NIGHT|EYE|FACE|HAIR|GOLD)$/i.test(t)) continue;
        if (/^[\d.,]+$/.test(t)) continue;
        if (/^\d{1,2}\/\d{2,4}$/.test(t)) continue;
        if (/^[A-Z0-9]{6,}$/.test(t)) continue;
        nameTokens.push(t);
      }
      r.product = nameTokens.join(' ');
      const p = block.filter(t => /^[\d.,]+$/.test(t)).map(num);
      if (p.length >= 6)      { r.mrp = p[0]; r.rate = p[1]; r.disc_pct = p[2]; r.cd_pct = p[3]; r.gst_pct = p[4]; r.amount = p[5]; }
      else if (p.length >= 5) { r.rate = p[0]; r.disc_pct = p[1]; r.gst_pct = p[3]; r.amount = p[4]; }
      items.push(r);
      nextSno++;
      i = j - 1;
    }
  }
  return items;
}

function extractWithCustomLogic(text, fileName = '') {
  const lines = cleanLines(text);
  const supplier = detectSupplier(text);
  const invoiceNo = extractInvoiceNo(text);
  const dateStr = extractDate(text);
  const customer = extractCustomer(lines);
  const structured = parseStructuredItems(lines);
  const items = structured && structured.length ? structured : parseHeuristicItems(lines);

  if (!items || items.length === 0) {
    console.log(`\n[DEBUG] FAILED INVOICE (${fileName}): NO ITEMS EXTRACTED`);
  }

  const { sgst, cgst } = extractCgstSgst(lines);
  const finalInvoice = extractFinalInvoice(lines);
  return (items || []).map((r, idx) => [
    supplier, customer, invoiceNo, dateStr,
    r.sno || idx + 1, r.product || '', "'" + (r.qty || ''),
    num(r.rate), num(r.disc_pct), num(r.gst_pct), num(r.amount),
    "", "", finalInvoice,
  ]);
}

// ── Health check ──────────────────────────────────────────────────────────────
app.get(['/', '/health'], (req, res) => {
  res.json({ success: true, message: 'Server is running', time: new Date().toISOString() });
});

// ── Main endpoint ─────────────────────────────────────────────────────────────
app.post(['/', '/extract-pdf', '/process', '/upload'], async (req, res) => {
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`[${new Date().toISOString()}] Incoming: ${req.url}`);
  let tmpPath = null;
  try {
    const base64 = req.body.base64 || req.body.pdfBase64;
    const fileName = req.body.fileName || '';
    if (!base64) return res.status(400).json({ error: 'Missing base64 data' });

    const buffer = Buffer.from(base64, 'base64');
    const data = await pdf(buffer);
    const textLen = (data.text || '').replace(/\s/g, '').length;
    console.log(`[INFO] fileName="${fileName}"  textLen=${textLen}`);

    let rows = [];
    let source = 'text';

    if (textLen >= 50) {
      const supplier = detectSupplier(data.text, fileName);
      const invoiceNo = extractInvoiceNo(data.text);
      console.log(`[INFO] supplier=${supplier}  invoiceNo=${invoiceNo}`);

      if (supplier === 'TMA') {
        rows = parseTMA(data.text);
        const tmaSummary = extractTmaSummary(data.text, invoiceNo);
        if (tmaSummary && rows.length > 0) {
          rows = rows.map(r => {
            const u = [...r];
            u[11] = ""; u[12] = ""; u[13] = tmaSummary.finalInvoice;
            return u;
          });
        }
        source = 'text+tma';
      } else if (supplier === 'SMA' || supplier === 'GMD') {
        rows = parseSMAGMD(data.text, supplier);
        source = `text+${supplier.toLowerCase()}`;
      } else if (supplier === 'ZELIG') {
        rows = parseZelig(data.text);
        source = 'text+zelig';
      } else {
        rows = extractWithCustomLogic(data.text, fileName);
        source = 'text+generic';
      }
    }

    if (rows.length === 0) {
      console.log(`[INFO] No text rows — falling back to OCR`);
      const tools = getOcrToolPaths();
      if (!tools.tesseract || !tools.pdftoppm) {
        return res.status(422).json({ success: false, error: 'OCR tools missing.' });
      }
      tmpPath = path.join(os.tmpdir(), `inv_${Date.now()}.pdf`);
      fs.writeFileSync(tmpPath, buffer);
      const ocrText = ocrPdfToText(tmpPath, { dpi: 300, psm: 4 });
      const supplier = detectSupplier(ocrText, fileName);
      const invoiceNo = extractInvoiceNo(ocrText);
      console.log(`[OCR] supplier=${supplier}  invoiceNo=${invoiceNo}`);

      if (supplier === 'TMA') {
        rows = parseTMA(ocrText);
        const tmaSummary = extractTmaSummary(ocrText, invoiceNo);
        if (tmaSummary && rows.length > 0) {
          rows = rows.map(r => {
            const u = [...r];
            u[11] = ""; u[12] = ""; u[13] = tmaSummary.finalInvoice;
            return u;
          });
        }
        source = 'ocr+tma';
      } else if (supplier === 'SMA' || supplier === 'GMD') {
        rows = parseSMAGMD(ocrText, supplier);
        source = `ocr+${supplier.toLowerCase()}`;
      } else if (supplier === 'ZELIG') {
        rows = parseZelig(ocrText);
        source = 'ocr+zelig';
      } else {
        rows = extractWithCustomLogic(ocrText, fileName);
        source = 'ocr+generic';
      }
    }

    console.log(`[DONE] source=${source}  rows=${rows.length}`);
    res.json({ success: true, rows, source });
  } catch (err) {
    console.error('Extraction error:', err);
    res.status(500).json({ success: false, error: err.message });
  } finally {
    if (tmpPath) { try { fs.unlinkSync(tmpPath); } catch (_) {} }
  }
});

const PORT = 5557;
app.listen(PORT, '0.0.0.0', () => console.log(`Server running on port ${PORT}`));