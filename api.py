import os
import base64
import tempfile
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from extractor import (
    process_file, 
    detect_supplier, 
    extract_invoice_no, 
    clean_lines,
    PDFTOTEXT_EXE
)
from pathlib import Path
import subprocess

app = Flask(__name__)
CORS(app)

# Increase max content length for large PDF uploads (100MB)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

@app.route('/health', methods=['GET'])
@app.route('/', methods=['GET'])
def health():
    return jsonify({
        "success": True,
        "message": "Python API Server is running",
        "time": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    })

@app.route('/', methods=['GET', 'POST'])
@app.route('/extract-pdf', methods=['GET', 'POST'])
@app.route('/process', methods=['GET', 'POST'])
@app.route('/upload', methods=['GET', 'POST'])
def extract_pdf():
    print(f"\n{'='*60}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Incoming request: {request.path} ({request.method})")
    
    if request.method == 'GET':
        return jsonify({
            "success": True,
            "message": "Endpoint is ready for POST requests",
            "time": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        })
        
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON body found"}), 400
            
        base64_data = data.get('base64') or data.get('pdfBase64')
        file_name = data.get('fileName', data.get('filename', 'unknown.pdf'))
        file_id = data.get('fileId', data.get('file_id', ''))
        
        if not base64_data:
            return jsonify({"error": "Missing base64 data"}), 400
            
        # 1. Decode base64 to temp file
        pdf_bytes = base64.b64decode(base64_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)
            
        try:
            print(f"[INFO] fileName=\"{file_name}\" processing...")
            
            # 2. Process using the extractor logic
            rows, source = process_file(tmp_path, original_filename=file_name)
            
            print(f"[DONE] source={source} rows={len(rows)}")
            
            # DEBUG: Save every PDF to debug_pdfs folder
            try:
                import re
                import shutil
                debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_pdfs')
                os.makedirs(debug_dir, exist_ok=True)
                safe_name = re.sub(r'[\\/*?:"<>|]', '_', file_name)
                debug_path = os.path.join(debug_dir, f"{safe_name}_{int(time.time())}.pdf")
                shutil.copy(tmp_path, debug_path)
                print(f"[DEBUG] Saved PDF to {debug_path}")
            except Exception as debug_err:
                print(f"[DEBUG_ERROR] Failed to save debug PDF: {debug_err}")

            return jsonify({
                "success": True, 
                "rows": rows, 
                "source": source,
                "fileName": file_name,
                "fileId": file_id
            })
            
        finally:
            # 3. Cleanup temp file
            if tmp_path.exists():
                os.unlink(tmp_path)
                
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Extraction error: {str(e)}\n{tb}")
        return jsonify({
            "success": False, 
            "error": str(e)
        }), 500

if __name__ == '__main__':
    PORT = 5557
    print(f"Python Server running on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
