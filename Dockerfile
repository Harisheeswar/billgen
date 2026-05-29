# Use a lightweight Node.js base image
FROM node:20-slim

# Install system dependencies (Poppler for pdftoppm, and Tesseract OCR)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install --production

# Copy all project files
COPY . .

# Expose the API port
EXPOSE 5557

# Start the server
CMD ["node", "api.js"]
