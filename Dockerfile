FROM python:3.11-slim

WORKDIR /app

# Create a non-root user (required by Hugging Face Spaces)
RUN useradd -m -u 1000 user

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directory with proper write permissions
RUN mkdir -p /app/data && chown -R user:user /app

USER user

# Hugging Face Spaces uses port 7860
EXPOSE 7860

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
