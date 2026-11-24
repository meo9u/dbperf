# Custom k6 binary with direct MySQL and MongoDB drivers.
# K6_RELEASE is not named K6_VERSION: xk6 reads that env var itself.
# Every version is pinned so rebuilds produce the same binary. To upgrade,
# change the ARGs below, rebuild and re-check `k6 version` for the extensions.
ARG XK6_RELEASE=1.4.15
ARG K6_RELEASE=2.3.0

FROM grafana/xk6:${XK6_RELEASE} AS builder
ARG K6_RELEASE

# xk6 warns "conflicting k6 versions": xk6-mongo lists both go.k6.io/k6 and
# go.k6.io/k6/v2 in its go.mod. The extensions still load (checked with
# `k6 version` and a probe script); re-check when bumping any version.
RUN xk6 build v${K6_RELEASE} \
    --with github.com/grafana/xk6-sql@v1.2.4 \
    --with github.com/grafana/xk6-sql-driver-mysql@v0.4.3 \
    --with github.com/GhMartingit/xk6-mongo@v1.4.0 \
    --output /tmp/k6

FROM grafana/k6:${K6_RELEASE}

COPY --from=builder /tmp/k6 /usr/bin/k6
ENTRYPOINT ["/usr/bin/k6"]
