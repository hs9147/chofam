# 이 리포 Dockerfile은 services/build.py의 "리포 자체 Dockerfile 우선" 규칙에 따라
# templates/dockerfiles/react.*.Dockerfile 대신 쓰인다 — 콘솔을 자기 배포(옵트인,
# PAAS_SELF_DEPLOY_CONSOLE)로 별도 컨테이너로 띄울 때 전용으로 필요하다.
#
# vite.config.ts의 base는 '/console/'(FastAPI가 /console에 정적 마운트하는 기본 배포
# 방식 전제)이지만, 이 컨테이너는 자기 도메인 루트에서 직접 서빙되므로 base를 '/'로
# 덮어써야 한다 — 그래서 일반 react.release.Dockerfile 템플릿을 그대로 못 쓴다.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV NODE_ENV=production
RUN npm run build -- --base=/

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
EXPOSE 80
CMD ["caddy", "file-server", "--root", "/srv", "--listen", ":80"]
