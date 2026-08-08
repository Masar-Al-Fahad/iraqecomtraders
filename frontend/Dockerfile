# Static Vite frontend for Railway (or any Docker host)
# Set VITE_API_BASE_URL (or VITE_API_URL) on the Railway *frontend* service.
# It must be available at *build* time (Railway injects service vars into the build env).
# Do NOT declare bare ARG/ENV that overwrite those vars with empty strings.
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Railway exposes service variables to Docker builds through matching ARG declarations.
# Do not copy an empty ARG into ENV; resolve the preferred value only in this RUN layer.
ARG VITE_API_BASE_URL
ARG VITE_API_URL

# Alias: VITE_API_URL → VITE_API_BASE_URL (Vite only embeds VITE_* at build).
# Default to the production FastAPI URL when unset so deploys still work.
RUN set -e; \
    if [ -z "$VITE_API_BASE_URL" ] && [ -n "$VITE_API_URL" ]; then \
      export VITE_API_BASE_URL="$VITE_API_URL"; \
    fi; \
    if [ -z "$VITE_API_BASE_URL" ]; then \
      export VITE_API_BASE_URL="https://iraqecomtraders-production.up.railway.app"; \
      echo "WARNING: VITE_API_BASE_URL unset; defaulting to ${VITE_API_BASE_URL}"; \
    fi; \
    export VITE_API_BASE_URL="${VITE_API_BASE_URL%/}"; \
    echo "Building frontend with VITE_API_BASE_URL=${VITE_API_BASE_URL}"; \
    npm run build; \
    ! grep -R -F "/api/config" dist; \
    grep -R -F "$VITE_API_BASE_URL" dist >/dev/null

FROM node:20-alpine

WORKDIR /app
RUN npm install -g serve@14.2.5

COPY --from=build /app/dist ./dist
COPY package.json ./package.json
# Explicit SPA rewrites (also enabled via -s). Lives next to dist so `serve -c` finds it.
COPY serve.json ./serve.json

ENV PORT=3000
EXPOSE 3000

# -s / serve.json rewrites: every non-file path → /index.html (assets under /assets/* still served as files)
CMD ["sh", "-c", "serve -s dist -c serve.json -l tcp://0.0.0.0:${PORT}"]
