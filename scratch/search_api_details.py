from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
path = base_dir / "api.js"
with open(path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if "extractor" in line.lower() or "py" in line.lower():
            if "import" in line or "spawn" in line or "exec" in line or "process" in line:
                print(f"Line {idx+1}: {line.strip()}")
