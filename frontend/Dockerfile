# Production build: compile once, serve with next start.
# NEXT_PUBLIC_* values are baked at build time — pass them as build args.
FROM node:20-alpine AS build
WORKDIR /srv
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_YWS_URL=ws://localhost:1234
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID=
ARG NEXT_PUBLIC_ORG_NAME=
ARG NEXT_PUBLIC_CONTACT_EMAIL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_YWS_URL=$NEXT_PUBLIC_YWS_URL \
    NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID \
    NEXT_PUBLIC_ORG_NAME=$NEXT_PUBLIC_ORG_NAME \
    NEXT_PUBLIC_CONTACT_EMAIL=$NEXT_PUBLIC_CONTACT_EMAIL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine
WORKDIR /srv
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /srv/package.json ./
COPY --from=build /srv/node_modules ./node_modules
COPY --from=build /srv/.next ./.next
EXPOSE 3000
CMD ["npm", "run", "start"]
