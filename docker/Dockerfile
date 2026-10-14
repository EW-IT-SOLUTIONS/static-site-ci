# syntax=docker/dockerfile:1
#
# Imagem padrão dos sites estáticos (HTML/CSS/JS sem build).
# O contexto do build é a raiz do repositório do site; a config do nginx vem
# deste repositório por um contexto nomeado "ci":
#
#   docker build \
#     --build-context ci=<caminho>/static-site-ci/docker \
#     -f <caminho>/static-site-ci/docker/Dockerfile \
#     --build-arg APP_VERSION=sha-abc1234 -t meu-site .
#
# As exclusões ficam em Dockerfile.dockerignore, ao lado deste arquivo.

FROM nginxinc/nginx-unprivileged:1.30-alpine

ARG APP_VERSION=dev

USER root
RUN rm -rf /usr/share/nginx/html/*

COPY --from=ci nginx.conf /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html/

RUN printf '%s\n' "$APP_VERSION" > /usr/share/nginx/html/version.txt \
 && chmod -R a+rX /usr/share/nginx/html \
 && nginx -t

# 101 é o usuário nginx da imagem unprivileged; numérico para o runAsNonRoot do Kubernetes.
USER 101
ENV NGINX_ENTRYPOINT_QUIET_LOGS=1
EXPOSE 8080
