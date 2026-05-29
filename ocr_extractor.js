// OCR extractor for image-only PDFs.
// Pipeline:  PDF --(pdftoppm)--> PNG --(tesseract)--> text
//
// Requires the user to have installed:
//   - Tesseract OCR  (https://github.com/UB-Mannheim/tesseract/wiki)
//   - Poppler        (https://github.com/oschwartz10612/poppler-windows)
//
// Both binaries are auto-detected. If they aren't on PATH, we look in common
// install folders including the project's billgen folder.

import fs from 'fs';
import os from 'os';
import path from 'path';
import { execFileSync, execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/* ------------------------- exe path detection ---------------------- */

function findExe(name, candidatesGlobs) {
  // 1) try PATH
  try {
    const cmd = process.platform === 'win32' ? `where ${name}` : `which ${name}`;
    const out = execSync(cmd, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim().split(/\r?\n/)[0];
    if (out && fs.existsSync(out)) return out;
  } catch (_) {}

  // 2) try given candidate paths / globs
  for (const g of candidatesGlobs) {
    if (g.includes('*')) {
      const dir = path.dirname(g);
      const pat = path.basename(g);
      try {
        if (!fs.existsSync(dir)) continue;
        const re = new RegExp('^' + pat.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$', 'i');
        for (const entry of fs.readdirSync(dir)) {
          if (re.test(entry)) {
            const full = path.join(dir, entry);
            if (fs.existsSync(full) && fs.statSync(full).isFile()) return full;
            // entry might be a folder; look inside
            if (fs.statSync(full).isDirectory()) {
              const inner = [
                path.join(full, name + (process.platform === 'win32' ? '.exe' : '')),
                path.join(full, 'bin', name + (process.platform === 'win32' ? '.exe' : '')),
                path.join(full, 'Library', 'bin', name + (process.platform === 'win32' ? '.exe' : '')),
              ];
              for (const p of inner) if (fs.existsSync(p)) return p;
            }
          }
        }
      } catch (_) {}
    } else if (fs.existsSync(g)) {
      return g;
    }
  }
  return null;
}

const tesseractPath = (() => {
  const ext = process.platform === 'win32' ? '.exe' : '';
  return findExe('tesseract', [
    `C:\\Program Files\\Tesseract-OCR\\tesseract${ext}`,
    `C:\\Program Files (x86)\\Tesseract-OCR\\tesseract${ext}`,
    path.join(__dirname, `Tesseract-OCR\\tesseract${ext}`),
    path.join(__dirname, `tesseract\\tesseract${ext}`),
    path.join(__dirname, `tesseract${ext}`),
  ]);
})();

const pdftoppmPath = (() => {
  const ext = process.platform === 'win32' ? '.exe' : '';
  return findExe('pdftoppm', [
    path.join(__dirname, `poppler-*`),
    path.join(__dirname, `poppler\\bin\\pdftoppm${ext}`),
    `C:\\Program Files\\poppler-*`,
    `C:\\Program Files (x86)\\poppler-*`,
  ]);
})();

export function getOcrToolPaths() {
  return { tesseract: tesseractPath, pdftoppm: pdftoppmPath };
}

/* ----------------------- PDF -> text via OCR ----------------------- */

export function ocrPdfToText(pdfPath, opts = {}) {
  if (!tesseractPath) {
    throw new Error(
      'Tesseract not found. Install from https://github.com/UB-Mannheim/tesseract/wiki ' +
      'and ensure tesseract.exe is on PATH or in C:\\Program Files\\Tesseract-OCR\\.'
    );
  }
  if (!pdftoppmPath) {
    throw new Error(
      'pdftoppm (Poppler) not found. Install from https://github.com/oschwartz10612/poppler-windows/releases ' +
      'and add the poppler "bin" folder to PATH (or extract to billgen/poppler).'
    );
  }

  const dpi = opts.dpi || 300;
  const psm = opts.psm || 4;        // single column of text of variable sizes
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'billgen-ocr-'));
  const stem = path.join(tmpDir, 'page');

  try {
    // 1) PDF -> PNG (one file per page: page-1.png, page-2.png, ...)
    execFileSync(pdftoppmPath, ['-r', String(dpi), '-png', pdfPath, stem], { stdio: 'pipe' });

    const pages = fs.readdirSync(tmpDir)
      .filter(f => f.startsWith('page') && f.endsWith('.png'))
      .sort();

    if (pages.length === 0) throw new Error('pdftoppm produced no PNG output');

    // 2) Tesseract on each page
    const texts = [];
    for (const png of pages) {
      const imgPath = path.join(tmpDir, png);
      const out = execFileSync(
        tesseractPath,
        [imgPath, '-', '--psm', String(psm), '-c', 'preserve_interword_spaces=0'],
        { stdio: ['ignore', 'pipe', 'pipe'] }
      ).toString();
      texts.push(out);
    }
    return texts.join('\n');
  } finally {
    // 3) cleanup
    try {
      for (const f of fs.readdirSync(tmpDir)) fs.unlinkSync(path.join(tmpDir, f));
      fs.rmdirSync(tmpDir);
    } catch (_) {}
  }
}
