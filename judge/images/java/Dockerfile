FROM eclipse-temurin:21-alpine

RUN apk add --no-cache \
    time \
    coreutils \
    ca-certificates

RUN adduser -D -u 1000 run && \
    mkdir -p /workspace && \
    chown -R run:run /workspace

WORKDIR /workspace
USER run

CMD ["sleep", "infinity"]
