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
# templated conf: the body bound is auto-derived from MAX_FILE_MB (+6 MB
# margin) by start.sh unless NGINX_MAX_BODY_SIZE is set explicitly — keeping
# nginx above the app's caps by construction
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY start.sh /start.sh
RUN chmod +x /start.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["/start.sh"]
