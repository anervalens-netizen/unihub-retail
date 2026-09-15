# The exact base digest is resolved/pinned during the first local sandbox build checkpoint.
ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/workspace/.npm-global/bin:${PATH} \
    NPM_CONFIG_PREFIX=/workspace/.npm-global

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      chromium \
      curl \
      file \
      fonts-dejavu \
      fonts-liberation \
      git \
      jq \
      libreoffice \
      nodejs \
      npm \
      pandoc \
      poppler-utils \
      postgresql-client \
      ripgrep \
      unzip \
      zip \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --disable-pip-version-check --upgrade pip

COPY requirements.lock /tmp/ai-sandbox-requirements.lock
RUN /opt/venv/bin/python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --require-hashes \
      -r /tmp/ai-sandbox-requirements.lock \
    && rm /tmp/ai-sandbox-requirements.lock

RUN useradd --create-home --uid 1000 --shell /bin/bash sandbox \
    && mkdir -p \
      /workspace/knowledge \
      /workspace/input \
      /workspace/work \
      /workspace/output \
      /workspace/.npm-global \
    && chown -R sandbox:sandbox /workspace /opt/venv

WORKDIR /workspace
USER sandbox

# DockerSandboxClient supplies its own long-running container command. This
# default keeps the image convenient to inspect manually as well.
CMD ["tail", "-f", "/dev/null"]
