# --- Build Stage ---
FROM python:3.9-slim-buster AS build

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# --- Final Stage ---
FROM python:3.9-slim-buster

WORKDIR /app

# Create a non-root user
RUN addgroup --system --gid 1001 appuser && \
    adduser --system --uid 1001 --gid 1001 appuser

# Copy only necessary files from the build stage
COPY --from=build --chown=appuser:appuser /app/ /app/

# Copy your bot's code
COPY --chown=appuser:appuser bot_setup.py bot_core.py commands.py config.yaml.example ./

# Run as non-root user
USER appuser

CMD ["python", "bot_core.py"]