FROM python:3.11-slim

# Create non-root user
RUN groupadd -r webhook && useradd -r -g webhook webhook

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Create certs directory
RUN mkdir -p /etc/certs && chown webhook:webhook /etc/certs

# Set permissions
RUN chown -R webhook:webhook /app
USER webhook

# Expose webhook port
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8443/health || exit 1

# Run the webhook server
CMD ["python", "src/webhook_server.py"]
