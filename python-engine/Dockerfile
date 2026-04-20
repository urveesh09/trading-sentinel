# Build Stage
FROM python:3.11-slim as builder
WORKDIR /app

# Install system dependencies required for building C-extensions (like numpy/pandas-ta)
RUN apt-get update && apt-get install -y gcc g++ libffi-dev

COPY requirements.txt .

# FIX: Added the missing pip install command. 
# --user ensures packages are placed in /root/.local for the next stage to copy.
RUN pip install --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt

# Run Stage
FROM python:3.11-slim

# Install curl for HEALTHCHECK and gosu for privilege drop in entrypoint
RUN apt-get update && apt-get install -y curl gosu && rm -rf /var/lib/apt/lists/*

# Create the non-root user for production security
RUN useradd -m -s /bin/bash quantuser
WORKDIR /app

# Copy the installed Python packages from builder stage
COPY --from=builder /root/.local /home/quantuser/.local
COPY . .

# Set up permissions for the app and the persistent data directory [cite: 117]
RUN chown -R quantuser:quantuser /app && \
    mkdir -p /data && \
    chown -R quantuser:quantuser /data && \
    chmod +x /app/entrypoint.sh

# Ensure the local bin is in PATH so uvicorn can be found
ENV PATH=/home/quantuser/.local/bin:$PATH
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
