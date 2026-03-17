FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    python3 \
    default-jdk \
    time \
    coreutils \
    && rm -rf /var/lib/apt/lists/*

# Verify all runtimes are functional
RUN python3 --version && \
    g++ --version && \
    java -version && \
    /usr/bin/time --version 2>&1 | head -1

WORKDIR /workspace