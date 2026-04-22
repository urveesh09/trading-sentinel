# Stage 1 - React build
FROM node:20-alpine AS client-build
WORKDIR /app/client
COPY client/package*.json ./
RUN npm ci --omit=dev
COPY client/ ./
RUN npm run build
# Output -> /app/client/dist

# Stage 2 - Server
FROM node:20-alpine
# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

# Install server dependencies
COPY server/package*.json ./
RUN npm ci --omit=dev

# Copy server code
COPY server/ ./

# Copy built React files to public directory
COPY --from=client-build /app/client/dist ./public

# Setup persistent volume directory with correct permissions
RUN mkdir -p /data && chown appuser:appgroup /data
RUN chown -R appuser:appgroup /app

# Drop privileges
USER appuser

# Define volume for persistent SQLite DBs
VOLUME ["/data"]

EXPOSE 3000

# Docker Healthcheck targeting the Node /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/health || exit 1

CMD ["node", "index.js"]
