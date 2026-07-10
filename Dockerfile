FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY nexus/ nexus/
COPY web/ web/

ENV NEXUS_DATA_DIR=/data
EXPOSE 8675

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8675/api/v1/health', timeout=4)"

CMD ["python", "-m", "nexus"]
