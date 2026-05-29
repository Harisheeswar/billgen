import fs from 'fs';
import pdf from 'pdf-parse';

async function test() {
  try {
    const buffer = fs.readFileSync('c:/Users/User/Downloads/billgen/invoices/Zelig/Zelig Invoice_Mar_25/Z0421.PDF');
    const data = await pdf(buffer);
    console.log('--- START TEXT ---');
    console.log(data.text);
    console.log('--- END TEXT ---');
  } catch (err) {
    console.error(err);
  }
}

test();
