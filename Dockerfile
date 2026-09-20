FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps face_recognition==1.3.0

COPY . .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
