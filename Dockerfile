# ==============================================================================
# TokTracker - Production Dockerfile
# Multi-purpose: FastAPI Dashboard + TikTokLive Worker Threads + Telegram Bot
# ==============================================================================
FROM python:3.11-slim

# Metadaten
LABEL maintainer="TokTracker Team"
LABEL description="TikTok Live Earnings Tracker, Analytics Dashboard & Telegram Bot"

# 1. Python-Laufzeitumgebung optimieren
# - PYTHONDONTWRITEBYTECODE: Keine .pyc Dateien erzeugen (spart I/O & Platz)
# - PYTHONUNBUFFERED: Logs sofort unbuffered nach stdout/stderr leiten (wichtig für docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=5000

# 2. Arbeitsverzeichnis festlegen
WORKDIR /app

# 3. System-Abhängigkeiten installieren
# - curl: Für den Docker HEALTHCHECK
# - gcc, libffi-dev, libssl-dev: Für kryptografische Python-Pakete (cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Dedizierten System-Benutzer anlegen (Security Best Practice: Kein Root-Betrieb)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# 5. Python-Paketabhängigkeiten separat kopieren & installieren (Docker Layer Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 6. Anwendungscode kopieren und Dateiberechtigungen an appuser übergeben
COPY --chown=appuser:appgroup . /app

# 7. Zum nicht-privilegierten Benutzer wechseln
USER appuser

# 8. Port dokumentieren
EXPOSE 5000

# 9. Docker Healthcheck zur automatischen Überwachung
# Prüft alle 30s, ob FastAPI auf Port 5000 HTTP 200 liefert
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:5000/ || exit 1

# 10. Startbefehl: Uvicorn mit genau 1 Worker
# WICHTIG: --workers 1 ist zwingend erforderlich, da TikTokLive-Worker und der
# Telegram-Bot als Singletons im Prozess laufen. Mehrere Worker würden dieselben
# Streams doppelt tracken und Telegram-Polling-Konflikte auslösen.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
