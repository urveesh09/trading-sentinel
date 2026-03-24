FROM python:3.11-slim-bookworm

# Set environment variables for Python and Timezone
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Kolkata

# Install timezone data and lxml dependencies
RUN apt-get update && apt-get install -y tzdata gcc libxml2-dev libxslt-dev && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script
COPY agent.py .

# Run as unprivileged user
RUN useradd -m appuser
USER appuser

CMD ["python", "agent.py"]

