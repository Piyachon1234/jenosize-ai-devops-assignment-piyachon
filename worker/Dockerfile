FROM python:3.11-slim

RUN groupadd -r jenie && useradd -r -g jenie -u 10002 jenie
WORKDIR /worker

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY indexer/ ./indexer/
USER 10002

CMD ["python", "-m", "indexer.main"]