# Iktsuarpok 前端（Vue 3 + Vite）镜像：构建静态包后用 Nginx 托管
FROM node:22-alpine AS build

WORKDIR /build

# 先装依赖，利用镜像层缓存
COPY package.json package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY . .

# 前端以相对路径 /api 请求后端，由 Nginx 反向代理到 backend 容器；
# 如需直连某个固定地址（如 https://api.example.com），构建时覆盖该参数即可
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 80
