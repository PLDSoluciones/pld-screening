FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PLD_DB=/data/pld.db PLD_RAW_DIR=/data/raw PLD_INBOX_DIR=/data/inbox
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pldscreen ./pldscreen
COPY data/sample ./data/sample
COPY data/country_risk.csv ./data/country_risk.csv
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "pldscreen", "serve", "--host", "0.0.0.0", "--port", "8000"]
