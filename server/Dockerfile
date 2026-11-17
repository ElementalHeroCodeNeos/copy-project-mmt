# Server image: Python 3.12, thư viện chuẩn, không cần pip install.
# Build context là thư mục gốc repo (xem docker-compose.yml) để COPY được cả shared/.
FROM python:3.12-slim

# PYTHONPATH=/app: cho phép `import shared.protocol` từ code server.
# PYTHONDONTWRITEBYTECODE=1: không tạo file .pyc trong container.
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY shared/ ./shared/
COPY server/src/ ./src/

EXPOSE 5000

# -u: không đệm stdout/stderr, log hiện ngay trong `docker compose logs`.
CMD ["python", "-u", "src/server.py"]
