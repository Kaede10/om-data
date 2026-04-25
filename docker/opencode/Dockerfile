FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    git \
    gh \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://opencode.ai/install.sh | sh

ENV PATH="/root/.opencode/bin:${PATH}"

WORKDIR /workspace

ENTRYPOINT ["opencode"]