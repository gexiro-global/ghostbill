FROM python:3.12-slim

WORKDIR /app

# Ensure local app/ takes priority over site-packages
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" --uid 1001 ghostbill

COPY pyproject.toml .

# Test tooling is opt-in so it never ships in the production image.
# docker-compose.test.yml sets INSTALL_TEST_DEPS=true for CI.
ARG INSTALL_TEST_DEPS=false
RUN pip install --no-cache-dir --upgrade pip \
    && if [ "$INSTALL_TEST_DEPS" = "true" ]; then pip install --no-cache-dir ".[test]"; \
       else pip install --no-cache-dir .; fi

COPY . .

EXPOSE 8000

USER ghostbill

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
