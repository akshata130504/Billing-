# syntax=docker/dockerfile:1.7
# Rooman Billing - web image (static SPA served by nginx, /api/ proxied to the backend).
#
# Build context is frontend/:
#   docker build -t rooman-billing-web ./frontend

# ---- Stage 1: build the SPA -------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /src
# VITE_API_BASE_URL is empty on purpose: the SPA then calls same-origin /api/v1 and
# nginx proxies it to the backend container. Set an absolute URL only when the API
# lives on a different origin (and add that origin to ALLOWED_ORIGINS).
# VITE_SUPPORT_EMAIL is baked into the bundle at build time (Help > "Contact support").
# CI passes the GitHub repository variable SUPPORT_EMAIL; empty = "contact your administrator".
ARG VITE_SUPPORT_EMAIL=""
ENV CI=true \
    VITE_API_BASE_URL="" \
    VITE_APP_TITLE="Rooman Billing" \
    VITE_SUPPORT_EMAIL=${VITE_SUPPORT_EMAIL}

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# "build" = tsc && vite build (type errors fail the image build).
RUN npm run build

# ---- Stage 2: serve ----------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the stock site with ours (SPA fallback, /api/ proxy, caching, headers).
RUN rm -f /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/snippets
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/security-headers.conf /etc/nginx/snippets/security-headers.conf

COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

# The nginx image's default entrypoint/CMD run nginx in the foreground.
