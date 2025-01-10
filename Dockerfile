FROM python:3.9-slim

WORKDIR /app

# Install dependencies directly
RUN pip install --no-cache-dir discord.py PyNaCl PyYAML

COPY bot_setup.py .
COPY bot_core.py .
COPY commands.py .
COPY config.yaml .

CMD ["python", "bot_core.py"]