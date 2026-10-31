FROM python:3.12-slim

WORKDIR /app

COPY src/requirements.txt .
# pip is left unpinned on purpose: always take the latest security fixes.
# hadolint ignore=DL3013
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY templates/ templates/
COPY static/ static/
COPY alembic.ini entrypoint.sh ./

RUN chmod +x entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

EXPOSE 8999

ENTRYPOINT ["./entrypoint.sh"]
