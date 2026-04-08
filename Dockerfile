ARG PY_VERSION=3.14
FROM python:${PY_VERSION}-bookworm

RUN addgroup --gid 1002 "flakehunter" && \
    adduser --disabled-password --gecos "FlakeFighters User,,," \
    --home /home/flakehunter --ingroup flakehunter --uid 1002 flakehunter

# Set working directory
WORKDIR /home/flakehunter

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


USER 1002:1002


# Clone the repo and set up config with dummy details
RUN git clone https://github.com/home-assistant/core.git; \
    git config --global user.email "you@example.com"; \
    git config --global user.name "Your Name"

# Install pytest and the flake-fighting plugin
RUN pip install --no-cache-dir pytest
# RUN pip install pytest-flakefighters
RUN pip install git+https://github.com/test-flare/pytest-flakefighters.git@a4215e9b3c6471ca2e95870e0daebb1ee0c10d75


# Copy the entrypoint script
COPY --chown=1002:1002 entrypoint.sh entrypoint.sh
COPY --chown=1002:1002 src/reproduce_flakiness.py reproduce_flakiness.py
RUN chmod +x entrypoint.sh
RUN mkdir outputs && chmod 777 outputs
ENV PATH="$PATH:/home/flakehunter/.local/bin"

ENTRYPOINT ["/bin/bash", "./entrypoint.sh"]
