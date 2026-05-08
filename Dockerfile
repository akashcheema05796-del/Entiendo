FROM node:22-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

FROM base AS dev
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM base AS builder
RUN npm run build

FROM node:22-alpine AS production
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY --from=builder /app/dist ./dist
COPY server.ts ./
COPY src/orchestration ./src/orchestration
COPY src/infrastructure ./src/infrastructure
COPY src/tools ./src/tools
ENV NODE_ENV=production
EXPOSE 3000
CMD ["npx", "tsx", "server.ts"]
