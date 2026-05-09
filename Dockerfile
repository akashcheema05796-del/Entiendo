# ── Stage 1: Build frontend ───────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# ── Stage 2: Production runtime ───────────────────────────────────────────────
FROM node:22-alpine AS production
WORKDIR /app

# tsx is a regular dependency so it's available after --omit=dev install
COPY package*.json ./
RUN npm install --omit=dev

# Compiled frontend assets
COPY --from=builder /app/dist ./dist

# Server source (TypeScript, run directly via tsx)
COPY server.ts ./
COPY src/orchestration ./src/orchestration
COPY src/infrastructure ./src/infrastructure
COPY src/tools ./src/tools

ENV NODE_ENV=production
EXPOSE 3000

CMD ["node_modules/.bin/tsx", "server.ts"]

# ── Dev target (docker-compose) ───────────────────────────────────────────────
FROM node:22-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
