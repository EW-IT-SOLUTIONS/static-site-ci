# static-site-ci

Receita única para publicar sites estáticos (HTML, CSS e JS, sem build) no cluster MicroK8s da EW.
Hoje atende os sites do Instituto Dra. Débora Camilo; serve para qualquer landing estática de cliente.

Repositório **público** de propósito: o workflow reutilizável é chamado por repositórios de outra conta,
e o GitHub só permite isso entre donos diferentes quando o repositório é público. Aqui não há segredo
nenhum: as credenciais ficam em cada repositório de site.

## O que tem aqui

| Arquivo | Papel |
|---|---|
| `.github/workflows/static-site.yml` | Pipeline reutilizável: gitleaks, build, teste de rotas, GHCR, deploy no ew-gitops, verificação |
| `docker/Dockerfile` | `nginx-unprivileged:1.30-alpine` + arquivos do site + `/version.txt` |
| `docker/Dockerfile.dockerignore` | O que nunca vai para a imagem: `.git`, `*.md`, backups, versões antigas, duplicatas do Finder |
| `docker/nginx.conf` | Reproduz `cleanUrls: true` e `trailingSlash: false` da Vercel, cache, gzip, cabeçalhos de segurança |
| `test/testar-rotas.py` | Testa URLs limpas, redirects (mantendo `?utm_...`) e todos os links internos |
| `exemplos/deploy.yml` | O arquivo que vai em cada site, em `.github/workflows/deploy.yml` |

## Rotas

| Pedido | Resposta |
|---|---|
| `/implante` | 200, serve `implante.html` |
| `/termos-de-uso` | 200, serve `termos-de-uso/index.html` |
| `/implante.html?utm_source=meta` | 301 para `/implante?utm_source=meta` |
| `/pasta/index.html` | 301 para `/pasta` |
| `/index.html` | 301 para `/` |
| `/implante/` | 301 para `/implante` |
| `/healthz` | 200 `ok` (sondas do Kubernetes), sem cache |
| `/version.txt` | tag da imagem (`sha-abc1234`), sem cache |

## Testar um site no Mac

Precisa do Docker Desktop (ou OrbStack). Na pasta do site:

```bash
CI=~/Sistemas/instituto_dra_debora_camilo/static-site-ci
docker build --build-context ci=$CI/docker -f $CI/docker/Dockerfile \
  --build-arg APP_VERSION=sha-local01 -t site-teste .
docker run --rm -d --name site-teste -p 8080:8080 --read-only --tmpfs /tmp site-teste
python3 $CI/test/testar-rotas.py http://127.0.0.1:8080 . --versao sha-local01
docker rm -f site-teste
```

## Versões

Os sites chamam `@v1`. Mudança compatível: commit na `main` e mover a tag `v1`
(`git tag -f v1 && git push -f origin v1`). Mudança que quebra: nova tag `v2` e atualizar os sites.
