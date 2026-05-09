FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pocketreader /app/pocketreader

EXPOSE 4780

CMD ["uvicorn", "pocketreader.main:app", "--host", "0.0.0.0", "--port", "4780", "--workers", "1"]

