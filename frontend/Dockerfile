# Frontend build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_URL is injected at build time so the JS bundle knows the backend URL.
# Override via: docker build --build-arg VITE_API_URL=https://api.example.com
ARG VITE_API_URL=http://localhost/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Production stage — Nginx serving the static bundle
FROM nginx:1.27-alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
