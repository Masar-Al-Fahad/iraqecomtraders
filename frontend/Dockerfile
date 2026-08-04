# Static Vite frontend for Railway (or any Docker host)
# Set VITE_API_BASE_URL (or VITE_API_URL) on the Railway *frontend* service.
# It must be available at *build* time (Railway injects service vars into the build env).
# Do NOT declare bare ARG/ENV that overwrite those vars with empty strings.
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Railway/build host env is used as-is. Fail fast if API URL missing.
# Alias: VITE_API_URL → VITE_API_BASE_URL (Vite only embeds VITE_* at build).
RUN set -e; \
    if [ -z "$VITE_API_BASE_URL" ] && [ -n "$VITE_API_URL" ]; then \
      export VITE_API_BASE_URL="$VITE_API_URL"; \
    fi; \
    if [ -z "$VITE_API_BASE_URL" ]; then \
      echo "ERROR: Set VITE_API_BASE_URL (or VITE_API_URL) to your FastAPI public URL (no trailing slash) before building."; \
      exit 1; \
    fi; \
    export VITE_API_BASE_URL="${VITE_API_BASE_URL%/}"; \
    echo "Building frontend with VITE_API_BASE_URL=${VITE_API_BASE_URL}"; \
    npm run build

FROM node:20-alpine

WORKDIR /app
RUN npm install -g serve@14

COPY --from=build /app/dist ./dist

ENV PORT=3000
EXPOSE 3000

# -s = SPA mode (all routes → index.html)
CMD ["sh", "-c", "serve -s dist -l tcp://0.0.0.0:${PORT}"]
