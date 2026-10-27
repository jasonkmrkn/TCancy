FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod -R a+rX /app \
    && mkdir -p /data/uploads \
    && chown app:app /data/uploads \
    && chmod 700 /data/uploads

USER app

EXPOSE 8000

CMD ["sh", "-c", "if [ -f alembic.ini ]; then alembic upgrade heads; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers"]