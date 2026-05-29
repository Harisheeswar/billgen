import fs from 'fs';
import pdf from 'pdf-parse';

async function test() {
  try {
    const buffer = fs.readFileSync('c:/Users/User/Downloads/billgen/invoices/GMD/GMD - Mumbai/Mumbai Invoice_Mar_25/GM304.PDF');
    const data = await pdf(buffer);
    console.log('--- START TEXT ---');
    console.log(data.text);
    console.log('--- END TEXT ---');
  } catch (err) {
    console.error(err);
  }
}

test();
