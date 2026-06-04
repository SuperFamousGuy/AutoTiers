FROM node:22-alpine
WORKDIR /app

# Copy only package.json, not package-lock.json: npm bug #4828 silently skips
# optional platform-specific native bindings (e.g. rolldown's Alpine/musl binary)
# when a lockfile is present at install time, crashing Vite on container startup.
COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
