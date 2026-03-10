FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    python3 \
    default-jdk \
    git \
    make \
    gcc \
    libc6-dev \
    libcap-dev \
    ca-certificates \
    pkg-config \
    libsystemd-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/ioi/isolate.git /tmp/isolate && \
    cd /tmp/isolate && \
    make isolate && make install && \
    rm -rf /tmp/isolate

RUN python3 --version && \
    g++ --version && \
    java -version && \
    isolate --version

WORKDIR /workspace