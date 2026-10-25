FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine
# access_log off: access lines would contain room URLs (SR-4)
RUN sed -i 's|access_log /var/log/nginx/access.log main;|access_log off;|' /etc/nginx/nginx.conf
# templated conf: NGINX_CLIENT_MAX_BODY_SIZE (default 16m) must stay above
# the api's MAX_FILE_MB, or nginx rejects large uploads before the app's
# per-room caps can answer with a clean 413
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
