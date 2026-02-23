FROM python:3.11-slim

WORKDIR /app

# Copy shared source code
COPY src/ /app/src/

# Copy Docker configuration
COPY config/config.yaml /app/config/config.yaml

# Copy service requirements and install
COPY services/planner/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy service main
COPY services/planner/main.py /app/main.py

# Set Python path
ENV PYTHONPATH=/app

# Run the service
CMD ["python", "main.py"]
