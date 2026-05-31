# ── Build stage ────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Bagimliliklari once kopyala — layer cache icin
COPY package*.json ./
RUN npm ci

# Kaynak kodu kopyala ve uygulama metnini derle
COPY . .

# VITE_API_URL build arg ile bake edilir (production: /api)
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Production stage (nginx:alpine) ────────────────────────────────────────────
FROM nginx:alpine

# Derlenmis statik dosyalar
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx yapilandirmasi (SPA routing + Flask proxy)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
