// AI fallback extractor for image-only PDFs (no text layer).
// Uses OpenAI's Responses API with a PDF file upload + JSON-schema response.
//
// Requires:
//   process.env.OPENAI_API_KEY  - your OpenAI API key
//   openai >= 4.x with .responses.create()
//
// Cost: ~$0.005-0.02 per invoice with gpt-4o-mini.

import fs from 'fs';
import OpenAI from 'openai';

const JSON_SCHEMA = {
  name: 'invoice_extraction',
  strict: true,
  schema: {
    type: 'object',
    additionalProperties: false,
    required: ['supplier', 'customer', 'invoice_no', 'date',
               'items', 'cgst', 'sgst', 'final_invoice'],
    properties: {
      supplier: { type: 'string',
        description: 'Supplier code: TMA (Thane Medical), SMA (Shradha Medical), ZELIG, or full name if unknown.' },
      customer: { type: 'string' },
      invoice_no: { type: 'string' },
      date: { type: 'string',
        description: 'Invoice date in DD-MM-YYYY format' },
      items: {
        type: 'array',
        items: {
          type: 'object',
          additionalProperties: false,
          required: ['sno', 'product', 'qty', 'rate', 'disc_pct', 'gst_pct', 'amount'],
          properties: {
            sno: { type: 'number' },
            product: { type: 'string',
              description: 'Product / item name as printed' },
            qty: { type: 'string',
              description: 'Literal quantity text including any free notation. Examples: "20", "+8", "10+4". Keep the leading + sign for free-item rows.' },
            rate: { type: 'number',
              description: 'Per-unit selling rate (not MRP)' },
            disc_pct: { type: 'number' },
            gst_pct: { type: 'number' },
            amount: { type: 'number',
              description: 'Line total as printed on the invoice (typically rate * qty before tax)' },
          },
        },
      },
      cgst: { type: 'number',
        description: 'Total CGST. For interstate invoices (IGST), set cgst=0 and put the IGST amount into sgst, OR set both to 0 — but never duplicate it across both columns.' },
      sgst: { type: 'number',
        description: 'Total SGST. See cgst note for interstate handling.' },
      final_invoice: { type: 'number',
        description: 'Grand total / final amount payable' },
    },
  },
};

const PROMPT = `Extract every line item and totals from this Indian pharmaceutical / medical-supplies invoice PDF.

Rules:
- supplier: use code TMA / SMA / ZELIG when the supplier name matches Thane Medical Agency, Shradha Medical Agency, or Zelig respectively. Otherwise use the supplier's short name.
- date: format strictly as DD-MM-YYYY.
- qty: keep the literal text exactly as printed. If the row shows "10+4" (10 paid + 4 free) keep "10+4". If it shows "+8" (8 free), keep "+8". If it's just "20", use "20".
- rate: the per-unit selling rate (not MRP).
- amount: the line total as shown on the invoice (typically rate * qty before tax). Do not include taxes here.
- For interstate invoices that show IGST instead of CGST/SGST, set cgst=0 and sgst=0 (the schema doesn't have an IGST column; the IGST is implicitly inside final_invoice).
- All numbers must be plain JSON numbers, no commas, no currency symbols.
- final_invoice is the grand total (final amount payable on the bill).

Return only the structured JSON.`;

export async function extractWithAI(pdfPath, opts = {}) {
  const apiKey = opts.apiKey || process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY not set');
  const model = opts.model || 'gpt-4o-mini';
  const client = new OpenAI({ apiKey });

  // 1) Upload the PDF
  const file = await client.files.create({
    file: fs.createReadStream(pdfPath),
    purpose: 'user_data',
  });

  try {
    // 2) Ask the model to extract, constrained to our JSON schema
    const resp = await client.responses.create({
      model,
      input: [{
        role: 'user',
        content: [
          { type: 'input_file', file_id: file.id },
          { type: 'input_text', text: PROMPT },
        ],
      }],
      text: { format: { type: 'json_schema', ...JSON_SCHEMA } },
    });

    const text = resp.output_text;
    if (!text) throw new Error('No output_text from model');
    const data = JSON.parse(text);

    // 3) Convert to the same row schema produced by local_extractor
    return data.items.map((it, i) => [
      data.supplier || 'UNKNOWN',
      data.customer || 'UNKNOWN',
      data.invoice_no || 'UNKNOWN',
      data.date || 'UNKNOWN',
      it.sno || (i + 1),
      it.product || '',
      it.qty || '',
      Number(it.rate) || 0,
      Number(it.disc_pct) || 0,
      Number(it.gst_pct) || 0,
      Number(it.amount) || 0,
      Number(data.cgst) || 0,
      Number(data.sgst) || 0,
      Number(data.final_invoice) || 0,
    ]);
  } finally {
    // 4) Clean up the uploaded file (best effort)
    try { await client.files.delete(file.id); } catch (_) {}
  }
}
