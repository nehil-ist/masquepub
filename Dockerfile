# Masque on Railway: Python only (serve.py answers the site and runs the background jobs).
FROM python:3.12-slim
# curl and perl are only used once, at build time, by tools/fetch-fonts.sh (saves the web fonts on this server).
RUN apt-get update && apt-get install -y --no-install-recommends curl perl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
# Save the web fonts on this server so visitors never contact Google. If Google cannot be reached during the build, the site just keeps using Google Fonts.
RUN sh tools/fetch-fonts.sh || echo "WARNING: fonts were not saved; the site will still load them from Google Fonts"
# serve.py listens on $PORT, creates the tables and runs the background jobs.
CMD ["python3","serve.py"]
