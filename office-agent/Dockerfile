FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy project files
COPY backend/ backend/
COPY frontend/ frontend/

# Create storage directories
RUN mkdir -p storage/uploads storage/outputs storage/temp storage/cache

# Expose port
EXPOSE 8000

# Run server from backend/ dir so `from app.xxx` imports work.
# main.py resolves _ROOT_DIR = parents[2] = /app, so frontend/storage paths are correct.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
