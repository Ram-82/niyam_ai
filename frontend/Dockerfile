# Dev image for the Next.js dashboard. Not production yet.
FROM node:20-alpine

WORKDIR /app

# Install deps first so we cache the layer across code edits.
COPY package.json ./
RUN npm install --no-audit --no-fund

# Source is bind-mounted at runtime.
COPY . /app

EXPOSE 3000
CMD ["npm", "run", "dev"]
