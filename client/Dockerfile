# Client image (Khôi): Python 3.12, thư viện chuẩn, không cần pip install.
# Build context là thư mục gốc repo (xem docker-compose.yml) để COPY được shared/ (giống server).
FROM python:3.12-slim

# PYTHONPATH=/app: cho phép `from shared import protocol` (dùng chung FrameBuffer, encode, decode).
# PYTHONDONTWRITEBYTECODE=1: không tạo file .pyc trong container.
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY shared/ ./shared/
COPY client/src/ ./src/

# -u: không đệm stdout, tin nhắn hiện ngay.
CMD ["python", "-u", "src/client.py"]
