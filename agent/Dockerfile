# Voice agent worker (production). `start` runs the worker in production
# mode: load-aware availability, no dev conveniences.
FROM python:3.11-slim

WORKDIR /srv
COPY pyproject.toml README.md ./
COPY interview_agent.py event_sink.py latency.py ./
COPY engine ./engine
RUN pip install --no-cache-dir -e .

# model files (turn detector / VAD) download at first start; bake them into
# the image so cold starts don't depend on network fetches
RUN python interview_agent.py download-files || true

CMD ["python", "interview_agent.py", "start"]
