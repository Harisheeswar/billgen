import fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const pdf = require('pdf-parse');

async function extract(filePath) {
  let dataBuffer = fs.readFileSync(filePath);
  const data = await pdf(dataBuffer);
  const text = data.text;
  
  const rawLines = text.split('\n').map(l => l.trim()).filter(l => l !== "");
  const lines = [];
  for (let i = 0; i < rawLines.length; i++) {
    if (i > 0 && rawLines[i] === rawLines[i-1]) continue;
    lines.push(rawLines[i]);
  }
  
  const fullText = text.toUpperCase();
  let supplier = "ZELIG";
  if (fullText.includes("THANE MEDICAL")) supplier = "TMA";
  else if (fullText.includes("GUWAHATI")) supplier = "TMA";

  const items = [];
  const skipWords = ["LOC", "QTY", "HSN", "EXP", "MRP", "MFG", "MFGR", "PACK", "RATE", "FREE", "DESC", "TOTAL"];

  if (supplier === "TMA") {
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (!/^[A-Z]{3,4}$/.test(line)) continue;
        if (skipWords.includes(line.toUpperCase())) continue;

        let rowTokens = [line];
        let j = i + 1;
        while (j < lines.length) {
          const nextToken = lines[j];
          const upNext = nextToken.toUpperCase();
          if (/^[A-Z]{3,4}$/.test(nextToken) && !skipWords.includes(upNext)) break;
          if (upNext.includes("TOTAL") || upNext.includes("GST:") || upNext.includes("GRAND") || upNext.includes("SCH:")) break;
          rowTokens.push(nextToken);
          j++;
        }

        if (rowTokens.length >= 10) {
          let row = { sno: items.length + 1 };
          if (rowTokens.length === 11) {
            row.mfg = rowTokens[0]; row.qty = rowTokens[1]; row.free = 0;
            row.hsn = rowTokens[2]; row.pack = rowTokens[3]; row.product = rowTokens[4];
            row.batch = rowTokens[5]; row.exp = rowTokens[6]; row.gst_pct = rowTokens[7];
            row.mrp = rowTokens[8]; row.rate = rowTokens[9]; row.amount = rowTokens[10];
          } else if (rowTokens.length === 12) {
            row.mfg = rowTokens[0]; row.qty = rowTokens[1]; row.free = rowTokens[2];
            row.hsn = rowTokens[3]; row.pack = rowTokens[4]; row.product = rowTokens[5];
            row.batch = rowTokens[6]; row.exp = rowTokens[7]; row.gst_pct = rowTokens[8];
            row.mrp = rowTokens[9]; row.rate = rowTokens[10]; row.amount = rowTokens[11];
          } else if (rowTokens.length >= 13) {
            row.mfg = rowTokens[0]; row.qty = rowTokens[2]; row.free = rowTokens[3];
            row.hsn = rowTokens[4]; row.pack = rowTokens[5]; row.product = rowTokens[6];
            row.batch = rowTokens[7]; row.exp = rowTokens[8]; row.gst_pct = rowTokens[9];
            row.mrp = rowTokens[10]; row.rate = rowTokens[11]; row.amount = rowTokens[12];
          }

          if (row.amount && /^[\d\.]+$/.test(row.amount.replace(/,/g, ''))) {
            items.push(row);
            i = j - 1;
          }
        }
      }
  }
  console.log(`Extracted ${items.length} items from ${filePath}`);
  if (items.length > 0) console.log(JSON.stringify(items[0], null, 2));
}

extract(process.argv[2]);
