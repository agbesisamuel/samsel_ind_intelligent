# Development and reproducible production-bundle check share the same locked toolchain.
FROM node:24.22.0-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5
# Match the API's explicit Debian security patch baseline; rebuild/scan on pin updates.
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    libcap2=1:2.66-4+deb12u3+b1 libgnutls30=3.7.9-2+deb12u7 \
    libpcre2-8-0=10.42-1+deb12u2 libssl3=3.0.22-1~deb12u1 \
    openssl=3.0.22-1~deb12u1 perl-base=5.36.0-7+deb12u4 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace/apps/web
RUN chown node:node /workspace/apps/web
# Install and create caches as the runtime user, avoiding a recursive ownership
# layer over node_modules on every source rebuild.
COPY --chown=node:node apps/web/package*.json ./
USER node
RUN npm ci
COPY --chown=node:node apps/web ./
COPY --chown=node:node packages/api-contracts /workspace/packages/api-contracts
EXPOSE 5173
CMD ["npm", "run", "dev"]
