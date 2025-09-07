FROM python:3.11-slim

# Create non-root user
RUN groupadd -r egress && useradd -r -g egress egress

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set permissions
RUN chown -R egress:egress /app
USER egress

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the agent
CMD ["python", "src/egress_agent.py"]
