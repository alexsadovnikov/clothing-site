FROM node:20-alpine

WORKDIR /app

# КОПИРУЕМ server.js ИЗ apps/web
COPY apps/web/server.js /app/server.js

ENV PORT=3000
EXPOSE 3000

CMD ["node", "server.js"]
