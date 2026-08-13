FROM python:3.12-slim

# Install system deps: Chromium for screenshots, rclone for SharePoint sync
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    rclone \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome path for Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create directories
RUN mkdir -p /root/mrg-finance screenshots

# Setup rclone cron (sync every 5 min)
RUN echo "*/5 * * * * rclone copy \"\$RCLONE_REMOTE\" /root/mrg-finance/ 2>&1 | tee -a /var/log/rclone.log" > /etc/cron.d/rclone-sync \
    && chmod 0644 /etc/cron.d/rclone-sync \
    && crontab /etc/cron.d/rclone-sync

# Start script: cron + gunicorn
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 5000

CMD ["./start.sh"]
