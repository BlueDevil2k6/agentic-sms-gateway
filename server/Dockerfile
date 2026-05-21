FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source
COPY src/ src/

# Create data directories
RUN mkdir -p data/outbound/pending data/outbound/sending data/outbound/done data/outbound/failed \
             data/inbound/pending  data/inbound/processing data/inbound/done  data/inbound/failed

EXPOSE 8080 8765

CMD ["sms-bridge"]
