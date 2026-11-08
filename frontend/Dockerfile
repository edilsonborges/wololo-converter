# Frontend Dockerfile - Multi-stage build

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Build context is the repository root (see docker-compose.yml)
# Copy package files
COPY frontend/package.json ./

# Install dependencies
RUN npm install

# Copy source code, plus the changelog shown in the release notes modal
# (imported as ../../CHANGELOG.md from src/)
COPY frontend/ .
COPY CHANGELOG.md /CHANGELOG.md

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built files from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port (unique port: one number lower than backend 47652)
EXPOSE 47651

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
