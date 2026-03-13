ARG PY_VERSION=3.14
FROM python:${PY_VERSION}-bookworm

# Install system dependencies required for Home Assistant core
RUN apt-get update && apt-get install -y \
    git \
    libudev-dev \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspaces/TestFlare

# Clone the repo (shallow clone to save time, we will fetch the specific hash later)
RUN git clone https://github.com/home-assistant/core.git; \
    git config --global user.email "you@example.com"; \
    git config --global user.name "Your Name"

ENV VIRTUAL_ENV=venv
RUN pip install virtualenv
RUN virtualenv $VIRTUAL_ENV
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install pytest and the flake-fighting plugin
RUN pip install --no-cache-dir pytest
# pytest-flakefighters
ADD "pytest-flakefighters" flakefighters
RUN pip install -e flakefighters

# Copy the entrypoint script
COPY flakefighters-experiment/entrypoint.sh entrypoint.sh
COPY flakefighters-experiment/src/reproduce_flakiness.py reproduce_flakiness.py
RUN chmod +x entrypoint.sh
RUN mkdir outputs

ENTRYPOINT ["/bin/bash", "./entrypoint.sh"]
