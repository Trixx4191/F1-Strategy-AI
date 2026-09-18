# Build stage
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend/ .

# VITE_API_URL is a BUILD-TIME value — Vite bakes import.meta.env.VITE_*
# into the compiled JS, since this code runs in the browser, not inside
# the Docker network. It must be a URL the browser can reach (e.g.
# http://localhost:8000 for local docker-compose, where the backend's
# port is published to the host) — NOT a Docker service name like
# http://backend:8000, which only resolves from inside the compose
# network, never from a user's browser.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# Serve stage — nginx serving the static build output
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD wget -qO- http://localhost:80/ >/dev/null || exit 1
