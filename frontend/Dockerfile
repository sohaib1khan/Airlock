FROM node:22-alpine

WORKDIR /app

# Sane defaults behind Nginx/Cloudflare: any public hostname, no HMR WebSocket (avoids wss issues).
ENV VITE_DEV_HMR=off

COPY package.json /app/package.json
RUN npm install

COPY . /app

CMD ["npm", "run", "dev"]
