# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS build

RUN npm install -g "pnpm@11.19.0"
WORKDIR /repo

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN pnpm install --frozen-lockfile --filter @eil/web...

COPY tsconfig.base.json ./
COPY packages ./packages
COPY apps/web ./apps/web

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_OIDC_AUTHORITY=http://localhost:8080/realms/eil
ARG VITE_OIDC_CLIENT_ID=eil-web
ARG VITE_OIDC_REDIRECT_URI=http://localhost:3000/auth/callback
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI

RUN pnpm --filter @eil/web build

FROM nginx:1.29-alpine AS runtime
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
