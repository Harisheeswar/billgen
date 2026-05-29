import fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const pdf = require('pdf-parse');

async function dump(filePath) {
  try {
    let dataBuffer = fs.readFileSync(filePath);
    const data = await pdf(dataBuffer);
    console.log("--- START TEXT ---");
    console.log(data.text);
    console.log("--- END TEXT ---");
  } catch (err) {
    console.error(err);
  }
}
dump(process.argv[2]);
