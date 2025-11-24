FROM python:3.11-slim

# Install Chrome and dependencies for headless operation
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    libxi6 \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libnspr4 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    fonts-liberation \
    libgbm1 \
    ca-certificates \
    libdrm2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libwayland-client0 \
    libxkbcommon0 \
    xdg-utils \
    procps \
    && wget -q -O /tmp/google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y /tmp/google-chrome-stable_current_amd64.deb \
    && rm /tmp/google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Set up environment for headless Chrome
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
# Prevent Chrome crashes in containers
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null
# Increase shared memory for Chrome (prevents crashes)
ENV CHROME_DEVEL_SANDBOX=/usr/local/sbin/chrome-devel-sandbox
# Force single-process mode to prevent crashes
ENV CHROME_FLAGS="--single-process --disable-dev-shm-usage"

# Set working directory
WORKDIR /app

# Create tmp directory for Chrome and ensure proper /dev/shm setup
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix \
    && mkdir -p /dev/shm && chmod 1777 /dev/shm

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the main script
CMD ["python", "-u", "main_runner.py"]
