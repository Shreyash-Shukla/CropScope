# CropScope Production Container
# Optimized for Google Cloud Run, Railway, Render, and Linux VPS

FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install minimal OS runtime packages required for Rasterio / NumPy OpenMP and SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create cache directory and non-root application user for container security
RUN mkdir -p /app/cache && \
    useradd -u 1000 -m appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose default Streamlit port (can be overridden by cloud platform via $PORT)
EXPOSE 8501

# Streamlit Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8501}/_stcore/health || exit 1

# Execute Streamlit with dynamic cloud $PORT support
ENTRYPOINT ["sh", "-c", "exec streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true"]
