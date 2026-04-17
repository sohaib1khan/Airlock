# Production UI: static Vite build + nginx (reliable behind HTTPS reverse proxies).
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . /app
ARG VITE_REPO_URL=
ENV VITE_REPO_URL=$VITE_REPO_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
