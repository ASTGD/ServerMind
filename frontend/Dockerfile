# ── Build stage ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Vite bakes VITE_* vars at build time — pass them as build args.
ARG VITE_API_URL
ARG VITE_WS_URL
ARG VITE_APP_NAME="ServerMind"
ARG VITE_APP_TAGLINE="Manage any server in natural language"
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_APP_NAME=$VITE_APP_NAME \
    VITE_APP_TAGLINE=$VITE_APP_TAGLINE

COPY package*.json ./
# `npm ci` installs exactly what package-lock.json says. `npm install` is free to resolve
# something newer and rewrite the lock, so the lockfile we commit was being ignored — the
# same reproducibility hole the backend had, just quieter because it rarely breaks.
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ── Serve stage ──────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
