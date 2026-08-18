FROM python:3.12-slim

WORKDIR /app

COPY services/notification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared modules first, then the service code.
COPY shared/ ./shared/
COPY services/notification-service/ .

RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -G root --create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
