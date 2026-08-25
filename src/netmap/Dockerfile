# NetMap - nmap LAN scanner + small web UI.
# Runs as root (nmap needs NET_RAW / raw packets) in the node host network namespace.
FROM python:3.12-alpine

RUN apk add --no-cache nmap nmap-scripts

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV SCAN_SUBNET=192.168.1.0/24
ENV SCAN_INTERVAL=900
ENV DB_PATH=/data/netmap.db

EXPOSE 8000
CMD ["python", "app.py"]
