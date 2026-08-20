FROM alpine:3.19
RUN apk add --no-cache curl
CMD ["curl", "-sf", "-X", "POST", "https://mobilitytracker-production.up.railway.app/enrichment/refresh-all"]
