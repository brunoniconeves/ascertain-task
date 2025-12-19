FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential curl \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fix line endings for shell scripts and ensure they're executable
RUN apt-get update && \
    apt-get install -y --no-install-recommends dos2unix && \
    find /app/scripts -name "*.sh" -type f -exec dos2unix {} \; && \
    chmod +x /app/scripts/*.sh && \
    apt-get purge -y dos2unix && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 8000

CMD ["bash", "/app/scripts/start.sh"]

