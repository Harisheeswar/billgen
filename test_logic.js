import { readFileSync } from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const TABLE_HEADERS = [
  "TOTAL AMT", "AMOUNT", "MFGR", "PRODUCT DESCRIPTION",
  "BATCH", "HSN", "PACK", "QTY", "RATES", "SCH.AMT",
  "DISC.AMT", "TAXABLE", "CGST%", "SGST%", "LOC", "FREE",
  "MRP", "EXP", "GST%", "PRODUCT NAME", "SR. HSN"
];

function isJunkLine(line) {
  const up = line.toUpperCase().trim();
  if (!up || up.length < 3) return true;
  if (up.includes("@")) return true;
  if (up.includes("||")) return true;
  if (/^[\d\s\.\,\-\/\%\(\)\+]+$/.test(up)) return true;
  if (/^(GSTIN|PAN|DL)\s*[:\-]/.test(up)) return true;
  if (/^(INVOICE|INV\.|BILL)\s*(NO|DATE)/i.test(up)) return true;
  if (/^(DUE DATE|SALESMAN|REPRINT|PCODE|CN DN|ROUND|FSSAI)/i.test(up)) return true;
  if (/^(TO PAY|TAXABLE|SCH:|CD:|GST:|COMPETENT)/i.test(up)) return true;
  if (/^(SHREE|GST INVOICE|ORIGINAL|DUPLICATE|TRIPLICATE|PAYMENT|RECORD)/i.test(up)) return true;
  if (/^FOR THANE/i.test(up)) return true;
  if (/^\(COMPETENT/i.test(up)) return true;
  if (/^STATE\s*\/\s*CODE/i.test(up)) return true;
  if (/^PHONE\s*:/i.test(up)) return true;
  if (/^EMAIL\s*:/i.test(up)) return true;
  if (TABLE_HEADERS.some(h => up.includes(h))) return true;
  if (up.includes("THANE MEDICAL")) return true;
  if (up.includes("BANJARA HILLS")) return true;
  if (up.includes("FARHAT AFZA")) return true;
  if (up.includes("LALBAUG ROAD")) return true;
  if (up.includes("RANKA PARK")) return true;
  if (up.includes("OFFICE NO")) return true;
  if (up.includes("BUILDING NO")) return true;
  if (up.includes("BUILDING-8")) return true;
  return false;
}

function runLogic() {
  const text = `
THANE MEDICAL AGENCY
OFFICE NO.5,
BUILDING NO.5/B, RANKA PARK APARTMENT
LALBAUG ROAD, BANGALORE-560027
Email : banglore@thanemedical.com
Phone : 9324022224 Mobile :
GSTIN : 29AAEFT2202R1ZU PAN No. AAEFT2202R
STATE / CODE : MAH / 29 FSSAI NO. 11519014000088
DL NO : 20B-KA-B31-212561, 20B-KA-B31-212562
DR.SHRUTHI MADHAVI ( SKIN SUMMIT CLINIC ) PCode: R243
NO.1196/60, 18TH A MAIN ROAD, 5TH BLOCK,
RAJAJI NAGAR
GSTIN :29BRVPG1363B1ZQ
DL NO :KMC 110130
FSSAI NO. :
MFGR LOC QTY FREE HSN PACK PRODUCT DESCRIPTION BATCH EXP GST% MRP RATES AMOUNT
  `;

  const rawLines = text.split('\n').map(l => l.trim()).filter(l => l !== "");
  const lines = [];
  for (let i = 0; i < rawLines.length; i++) {
    if (i > 0 && rawLines[i] === rawLines[i - 1]) continue;
    lines.push(rawLines[i]);
  }

  const fullText = text.toUpperCase();
  let supplier = "ZELIG";
  if (fullText.includes("THANE MEDICAL")) supplier = "TMA";

  let customer = "UNKNOWN";

  // Pass 1
  for (let i = 0; i < Math.min(lines.length, 80); i++) {
    const up = lines[i].toUpperCase();
    if (up.startsWith("DL NO") && up.includes("20B")) {
      for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
        const candidate = lines[j].trim();
        if (!isJunkLine(candidate)) {
          customer = candidate;
          break;
        }
      }
      if (customer !== "UNKNOWN") break;
    }
  }

  if (customer === "UNKNOWN") {
    // Pass 4
    for (let i = 0; i < Math.min(lines.length, 60); i++) {
      const up = lines[i].toUpperCase();
      if ((up.includes("DR.") || up.includes("DR ") || up.includes("M/S")) && !isJunkLine(lines[i])) {
        customer = lines[i].trim();
        break;
      }
    }
  }

  console.log("Extracted Customer:", customer);
}

runLogic();
