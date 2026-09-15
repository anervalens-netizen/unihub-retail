# The exact base digest is resolved/pinned during the first local sandbox build checkpoint.
ARG BASE_IMAGE=python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/workspace/work/python/bin:/workspace/work/npm/bin:/opt/venv/bin:${PATH} \
    HOME=/workspace/home \
    XDG_CACHE_HOME=/workspace/work/cache \
    NPM_CONFIG_PREFIX=/workspace/work/npm \
    NPM_CONFIG_CACHE=/workspace/work/cache/npm \
    PIP_TARGET=/workspace/work/python \
    PYTHONPATH=/workspace/work/python

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      build-essential \
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
    && env -u PIP_TARGET /opt/venv/bin/python -m pip install --disable-pip-version-check --upgrade pip

COPY requirements.lock /tmp/ai-sandbox-requirements.lock
RUN env -u PIP_TARGET /opt/venv/bin/python -m pip install \
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
      /workspace/home \
      /workspace/work/npm \
      /workspace/work/python \
    && chown -R sandbox:sandbox /workspace

# SDK shell execution uses sh -lc, whose /etc/profile resets PATH. Restore the
# bounded user environment for login shells as well as direct exec processes.
RUN printf '%s\n' \
      'export HOME=/workspace/home' \
      'export PATH=/workspace/work/python/bin:/workspace/work/npm/bin:/opt/venv/bin:/usr/local/bin:/usr/bin:/bin' \
      > /etc/profile.d/unihub-workspace.sh

WORKDIR /workspace
USER sandbox

# DockerSandboxClient supplies its own long-running container command. This
# default keeps the image convenient to inspect manually as well.
CMD ["tail", "-f", "/dev/null"]
