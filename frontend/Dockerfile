# 前端镜像：两阶段构建 —— Node 负责编译，Nginx 只托管产物
FROM node:22-alpine AS build

WORKDIR /app
# 先只拷 package*.json 装依赖：源码改动不会触发重装，缓存命中率高
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# = vue-tsc --noEmit && vite build（类型不过关直接构建失败，天然兜底）
RUN npm run build


FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
