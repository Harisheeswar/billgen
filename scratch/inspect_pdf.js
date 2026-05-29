import fs from 'fs';
import pdf from 'pdf-parse';

async function dump() {
  const file = process.argv[2] || 'invoices/000117 hyd aug 24.pdf';
  if (!fs.existsSync(file)) {
     console.error("File not found:", file);
     return;
  }
  const buf = fs.readFileSync(file);
  const data = await pdf(buf);
  console.log("TEXT START ----------------");
  console.log(data.text);
  console.log("TEXT END ------------------");
}
dump();
