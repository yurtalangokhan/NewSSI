ARG APISIX_IMAGE_TAG=3.18.0-debian
FROM apache/apisix:${APISIX_IMAGE_TAG}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl python3 python3-yaml \
    && rm -rf /var/lib/apt/lists/*
COPY configs/apisix/plugins/ /usr/local/apisix/apisix/plugins/
