# Caddy with the rate_limit handler (github.com/mholt/caddy-ratelimit), which the stock image
# lacks. It caps map tile requests per client (Caddyfile), since Martin has no limits of its own.
FROM caddy:2.11-builder-alpine AS builder
RUN xcaddy build --with github.com/mholt/caddy-ratelimit@v0.1.0

FROM caddy:2.11-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
