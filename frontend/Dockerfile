# syntax=docker/dockerfile:1.7
#
# Frontend image: nginx plus three static files.
#
# There is no build stage because there is no build. That is the whole argument
# for vanilla JS here — no node_modules, no transitive npm advisories in the
# vulnerability scan, and an image that is essentially just nginx.

FROM nginx:1.29-alpine AS runtime

# Patch OS packages before installing anything.
#
# Base images are rebuilt on the maintainer's schedule, not on the security
# advisory schedule, so even a current tag ships packages that lag behind
# Alpine's fixed versions. Trivy caught exactly this: 11 HIGH findings in
# c-ares, curl, and openssl — all with fixes already published — and the gate
# blocked the push. `apk upgrade` pulls those fixes in at build time.
#
# The trade-off is honest: this makes builds slightly non-reproducible, since
# the same Dockerfile produces different package versions on different days.
# For a security-patch layer that is the correct trade — pinning every package
# version would mean the image silently rots instead. Reproducibility is
# recovered where it matters, via the image digest recorded at publish time.
RUN apk upgrade --no-cache \
    && apk add --no-cache gettext curl

# nginx:alpine already defines an `nginx` user (uid 101). Give it ownership of
# every path it must write to at runtime.
#
# /etc/nginx is in that list and it is easy to miss: the stock entrypoint renders
# the template with envsubst and writes the result back into /etc/nginx, so a
# non-root container fails at startup with a permission error before nginx is
# ever invoked. Chowning only /var/cache/nginx — the obvious one — is not enough.
RUN mkdir -p /var/cache/nginx \
    && chown -R nginx:nginx /var/cache/nginx /usr/share/nginx/html /etc/nginx

COPY nginx.conf /etc/nginx/templates/nginx.conf.template
COPY --chown=nginx:nginx src/ /usr/share/nginx/html/

ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="url-shortener-frontend" \
      org.opencontainers.image.source="https://github.com/sudhamshrama/url-shortener" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="MIT"

ENV BACKEND_HOST=backend \
    BACKEND_PORT=8000

USER nginx

# 8080, not 80. Binding a port below 1024 needs CAP_NET_BIND_SERVICE, which a
# non-root process does not have. Using a high port is simpler and safer than
# granting the capability back.
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail --silent http://localhost:8080/healthz || exit 1

# The stock nginx entrypoint runs envsubst over /etc/nginx/templates/*.template
# and writes the result to NGINX_ENVSUBST_OUTPUT_DIR.
#
# The FILTER is a guardrail worth setting explicitly. The config is full of
# nginx's own runtime variables ($host, $remote_addr, $request_time, ...) which
# envsubst cannot distinguish from shell variables. The entrypoint only
# substitutes names that exist in the environment, so those survive by
# accident — but add an env var called, say, `host` and the log format silently
# breaks. Restricting substitution to BACKEND_* makes the contract explicit.
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx \
    NGINX_ENVSUBST_FILTER="^BACKEND_"

CMD ["nginx", "-g", "daemon off;"]
