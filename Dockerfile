# Use a lightweight Python base image
FROM python:3.10-slim

# Install system dependencies (Poppler for pdftoppm/pdftotext, and Tesseract OCR)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose the API port (api.py runs on port 5557)
EXPOSE 5557

# Start the Flask server
CMD ["python", "api.py"]
