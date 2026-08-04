# Static Vite frontend for Railway (or any Docker host)
# Build arg VITE_API_BASE_URL must be your Railway FastAPI public URL (no trailing slash).
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM node:20-alpine

WORKDIR /app
RUN npm install -g serve@14

COPY --from=build /app/dist ./dist

ENV PORT=3000
EXPOSE 3000

# -s = SPA mode (all routes → index.html)
CMD ["sh", "-c", "serve -s dist -l tcp://0.0.0.0:${PORT}"]
