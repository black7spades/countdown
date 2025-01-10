FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY bot_setup.py .
COPY bot_core.py .
COPY commands.py .

CMD ["python", "bot_core.py"]