FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browser dependencies
RUN playwright install chromium

# Copy application source code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HEADLESS_BROWSER=true
ENV DASHBOARD_PORT=5000

# Expose web dashboard port
EXPOSE 5000

# Start dashboard and engine
CMD ["python", "run.py", "--auto"]
