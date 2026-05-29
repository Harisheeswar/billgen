import fs from 'fs';
import path from 'path';
import pdf from 'pdf-parse';
import os from 'os';
import { ocrPdfToText, getOcrToolPaths } from './ocr_extractor.js';
import { parseTMA } from './tma_parser.js';
import { parseSMAGMD } from './smagmd_parser.js';
import { parseZelig } from './zelig_parser.js';

const INVOICE_FOLDER = 'invoices';
const OUTPUT_FILE = `output_${Date.now()}.csv`;

const num = s => {
  if (s == null) return 0;
  const v = parseFloat(String(s).replace(/,/g, '').trim());
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

function cleanLines(text) {
  return text.split('\n').map(l => l.trim()).filter(l => l !== '');
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
  for (let i = 0; i < lines.length; i++) {
    const u = lines[i].toUpperCase();
    if (u.includes('PARTY DETAILS') || u.startsWith('BILL TO') || u.includes('PARTY NAME') || /^NAME\s*:/.test(u)) {
      for (let j = i + 1; j < Math.min(i + 4, lines.length); j++) {
        const v = lines[j].trim();
        if (!v || /^GSTIN|^MOBILE|^GST|^FSSAI|^DL\s*NO/i.test(v)) continue;
        return v;
      }
    }
  }
  return 'UNKNOWN';
}

function extractCgstSgst(lines) {
  let sgst = 0, cgst = 0, found = false;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].trim().match(/^(\d+(?:\.\d+)?)\s*%$/);
    if (!m) continue;
    const nums = [];
    for (let j = i + 1; j < lines.length && nums.length < 7; j++) {
      if (isPureNumber(lines[j])) {
        nums.push(num(lines[j]));
      } else {
        const u = lines[j].toUpperCase();
        if (/^(NET TOTAL|GRAND TOTAL|REMARK|FOR\s+|AUTHORISED|DUE DATE|TO PAY|TAXABLE|TOTAL)/.test(u)) break;
        continue;
      }
    }
    if (nums.length >= 6) {
      cgst += nums[4];
      sgst += nums[5];
      found = true;
    } else if (nums.length >= 2) {
      cgst += nums[0];
      sgst += nums[1];
      found = true;
    }
  }
  if (found) return { sgst, cgst };
  const fullText = lines.join('\n');
  const cgstM = fullText.match(/\bCGST\b[^\d]*([\d,]+(?:\.\d+)?)/i);
  const sgstM = fullText.match(/\bSGST\b[^\d]*([\d,]+(?:\.\d+)?)/i);
  if (cgstM && sgstM) return { cgst: num(cgstM[1]), sgst: num(sgstM[1]) };
  return { sgst: 0, cgst: 0 };
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
        if (/^[A-Z]{3,5}$/.test(t)) continue;
        if (/^[\d.,]+$/.test(t) || /^\d{1,2}\/\d{2,4}$/.test(t) || /^[A-Z0-9]{6,}$/.test(t)) continue;
        nameTokens.push(t);
      }
      r.product = nameTokens.join(' ');
      const p = block.filter(t => /^[\d.,]+$/.test(t)).map(num);
      if (p.length >= 6) { r.mrp = p[0]; r.rate = p[1]; r.disc_pct = p[2]; r.cd_pct = p[3]; r.gst_pct = p[4]; r.amount = p[5]; }
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
  const items = parseHeuristicItems(lines);
  const { sgst, cgst } = extractCgstSgst(lines);
  const finalInvoice = extractFinalInvoice(lines);
  
  return (items || []).map((r, idx) => [
    supplier, customer, invoiceNo, dateStr,
    r.sno || idx + 1, r.product || '', "'" + (r.qty || ''),
    num(r.rate), num(r.disc_pct), num(r.gst_pct), num(r.amount),
    "", "", finalInvoice,
  ]);
}

async function processFile(fullPath) {
  const fileName = path.basename(fullPath);
  try {
    const buffer = fs.readFileSync(fullPath);
    const data = await pdf(buffer);
    const textLen = (data.text || '').replace(/\s/g, '').length;

    if (textLen >= 50) {
      const supplier = detectSupplier(data.text, fileName);
      if (supplier === 'TMA') {
        const rows = parseTMA(data.text);
        if (rows.length) return { rows, source: 'text+tma' };
      } else if (supplier === 'SMA' || supplier === 'GMD') {
        const rows = parseSMAGMD(data.text, supplier);
        if (rows.length) return { rows, source: `text+${supplier.toLowerCase()}` };
      } else if (supplier === 'ZELIG') {
        const rows = parseZelig(data.text);
        if (rows.length) return { rows, source: 'text+zelig' };
      }
      const rows = extractWithCustomLogic(data.text, fileName);
      if (rows.length) return { rows, source: 'text' };
    }

    console.log(`  No text layer or extraction failed. Running OCR...`);
    const ocrText = ocrPdfToText(fullPath, { dpi: 300, psm: 4 });
    const supplier = detectSupplier(ocrText, fileName);
    if (supplier === 'TMA') {
      return { rows: parseTMA(ocrText), source: 'ocr+tma' };
    } else if (supplier === 'SMA' || supplier === 'GMD') {
      return { rows: parseSMAGMD(ocrText, supplier), source: `ocr+${supplier.toLowerCase()}` };
    } else if (supplier === 'ZELIG') {
      return { rows: parseZelig(ocrText), source: 'ocr+zelig' };
    }
    return { rows: extractWithCustomLogic(ocrText, fileName), source: 'ocr+generic' };
  } catch (err) {
    console.error(`  Error processing ${fileName}:`, err.message);
    return { rows: [], source: 'error' };
  }
}

const csvEscape = s => {
  const str = String(s || '').replace(/"/g, '""');
  return `"${str}"`;
};

function getAllFiles(dirPath, arrayOfFiles) {
  const files = fs.readdirSync(dirPath);
  arrayOfFiles = arrayOfFiles || [];
  files.forEach(function(file) {
    if (fs.statSync(dirPath + "/" + file).isDirectory()) {
      arrayOfFiles = getAllFiles(dirPath + "/" + file, arrayOfFiles);
    } else if (file.toLowerCase().endsWith('.pdf')) {
      arrayOfFiles.push(path.join(dirPath, "/", file));
    }
  });
  return arrayOfFiles;
}

async function main() {
  const tools = getOcrToolPaths();
  console.log(`OCR tools: tesseract=${tools.tesseract || 'NOT FOUND'}, pdftoppm=${tools.pdftoppm || 'NOT FOUND'}`);
  
  if (!fs.existsSync(INVOICE_FOLDER)) {
    console.error(`Folder '${INVOICE_FOLDER}' not found.`);
    return;
  }

  const files = getAllFiles(INVOICE_FOLDER);
  console.log(`Found ${files.length} PDFs. Processing...\n`);

  const headers = ['Supplier', 'Customer', 'Invoice No', 'Date', 'S.No', 'Product', 'Qty', 'Rate', 'Dis%', 'GST%', 'Amount', 'CGST', 'SGST', 'Final Invoice'];
  fs.writeFileSync(OUTPUT_FILE, headers.map(csvEscape).join(',') + '\n');

  for (const f of files) {
    console.log(`Processing: ${f}...`);
    const { rows, source } = await processFile(path.join(INVOICE_FOLDER, f));
    console.log(`  Extracted ${rows.length} rows via ${source}`);
    for (const r of rows) {
      fs.appendFileSync(OUTPUT_FILE, r.map(csvEscape).join(',') + '\n');
    }
  }

  console.log(`\nDone! Data saved to: ${OUTPUT_FILE}`);
}

main();
