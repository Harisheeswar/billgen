from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
path = base_dir / "api.js"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
    
print("python in api.js:", "python" in content.lower())
print("extractor in api.js:", "extractor" in content.lower())
print("python in ocr_extractor.js:", "python" in (base_dir / "ocr_extractor.js").read_text(encoding="utf-8", errors="ignore").lower())
