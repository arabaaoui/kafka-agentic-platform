FROM node:20-slim

WORKDIR /app

# Copy package files from the correct path in context
COPY kafka-agentic-platform/web/package*.json kafka-agentic-platform/web/.npmrc ./
RUN npm install

# Copy all web files
COPY kafka-agentic-platform/web/ .

EXPOSE 3000

# Use dev mode for lab testing
CMD ["npm", "run", "dev"]
