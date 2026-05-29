import fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const pdf = require('pdf-parse');

async function dump(filePath) {
  try {
    let dataBuffer = fs.readFileSync(filePath);
    const data = await pdf(dataBuffer);
    const rawLines = data.text.split('\n').map(l => l.trim()).filter(l => l !== "");
    const lines = [];
    for (let i = 0; i < rawLines.length; i++) {
      if (i > 0 && rawLines[i] === rawLines[i-1]) continue;
      lines.push(rawLines[i]);
    }
    console.log(JSON.stringify(lines, null, 2));
  } catch (err) {
    console.error(err);
  }
}
dump(process.argv[2]);
