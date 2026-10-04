FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgcc-s1 \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# dlib-bin is installed by requirements.txt; skip face-recognition's dlib dependency.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps face_recognition==1.3.0
RUN python -c "import dlib, face_recognition; print('dlib-bin and face_recognition imports OK')"

COPY . .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
