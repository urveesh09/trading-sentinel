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
COPY . .

# Run as unprivileged user
RUN useradd -m appuser
USER appuser

# [ROADMAP-2.2 2026-07-12] Liveness: agent.py touches /tmp/agent_heartbeat
# from its main loop (30s) and inside per-signal iterations. 900s threshold
# comfortably exceeds the longest legitimate gap (one signal's Gemini
# analysis); a hang past it means EXEC alerts have stopped -> unhealthy ->
# autoheal restarts us. start-period covers boot until the first touch.
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,sys,time; sys.exit(0 if time.time()-os.path.getmtime('/tmp/agent_heartbeat') < 900 else 1)"

CMD ["python", "agent.py"]

