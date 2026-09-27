FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked in by `next build`: rewrites (next.config.ts) and client-side NEXT_PUBLIC_* values.
ARG INTERNAL_API_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_BASEMAP_PMTILES_URL=
ARG NEXT_PUBLIC_MAPTILER_KEY=
ENV NEXT_TELEMETRY_DISABLED=1 \
    INTERNAL_API_ORIGIN=$INTERNAL_API_ORIGIN \
    NEXT_PUBLIC_BASEMAP_PMTILES_URL=$NEXT_PUBLIC_BASEMAP_PMTILES_URL \
    NEXT_PUBLIC_MAPTILER_KEY=$NEXT_PUBLIC_MAPTILER_KEY
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
# Server components call the API directly (src/lib/api/client.ts), at request time.
ARG INTERNAL_API_ORIGIN=http://api:8000
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0 \
    INTERNAL_API_ORIGIN=$INTERNAL_API_ORIGIN
RUN adduser -S -u 10001 app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
