#!/usr/bin/env python3
"""Testa as rotas de um site estático servido pelo nginx da imagem padrão.

Uso:
    python3 testar-rotas.py http://127.0.0.1:8080 <pasta-do-site> [--versao sha-abc1234] [--ignorar 'regex']

O que confere:
  1. Toda página .html da pasta responde 200 na URL limpa (/implante, /termos-de-uso, /).
  2. A URL com .html redireciona (301) para a URL limpa, mantendo a query string.
  3. A URL limpa com barra no fim redireciona (301) para a versão sem barra.
  4. Todo link e recurso interno (href, src, srcset, url() no CSS) responde 200,
     seguindo no máximo 3 redirects.
  5. /healthz e /version.txt respondem; .git, .md e arquivos internos dão 404.

Páginas que o Dockerfile.dockerignore tira da imagem (backups, versões antigas,
duplicatas do Finder) aparecem como "fora da imagem" e não contam como erro.
Só usa a biblioteca padrão do Python.
"""
import argparse
import http.client
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote, quote

FORA_DA_IMAGEM = re.compile(r"( 2\.|backup|antigo)", re.I)
IGNORAR_ESQUEMAS = ("mailto:", "tel:", "javascript:", "data:", "blob:", "#", "about:")


class Coletor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for nome, valor in attrs:
            if not valor:
                continue
            if nome in ("href", "src", "poster", "data-src"):
                self.urls.append(valor.strip())
            elif nome in ("srcset", "imagesrcset"):
                for parte in valor.split(","):
                    item = parte.strip().split(" ")[0]
                    if item:
                        self.urls.append(item)
            elif nome == "style":
                self.urls += re.findall(r"url\(\s*['\"]?([^'\")]+)", valor)

    def handle_data(self, data):
        # CSS dentro de <style>
        self.urls += re.findall(r"url\(\s*['\"]?([^'\")]+)", data)


class Cliente:
    def __init__(self, base):
        p = urlsplit(base)
        self.host, self.porta = p.hostname, p.port or 80
        self.base = f"{p.scheme}://{p.netloc}"

    def get(self, caminho):
        c = http.client.HTTPConnection(self.host, self.porta, timeout=10)
        c.request("GET", quote(caminho, safe="/?&=%:+,;@-._~"))
        r = c.getresponse()
        corpo = r.read()
        c.close()
        return r.status, dict((k.lower(), v) for k, v in r.getheaders()), corpo

    def seguir(self, caminho, max_redir=3):
        cadeia = []
        for _ in range(max_redir + 1):
            st, h, corpo = self.get(caminho)
            cadeia.append((caminho, st))
            if st in (301, 302, 307, 308):
                caminho = urljoin(caminho, h.get("location", ""))
                continue
            return st, h, corpo, cadeia
        return st, h, corpo, cadeia


def url_limpa(rel):
    rel = rel.replace(os.sep, "/")
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("/index.html")]
    return "/" + rel[: -len(".html")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("pasta")
    ap.add_argument("--versao")
    ap.add_argument("--ignorar", default="",
                    help="regex de caminhos quebrados já conhecidos, que viram aviso em vez de erro")
    a = ap.parse_args()

    cli = Cliente(a.base)
    erros, avisos, ok = [], [], 0
    externos = set()

    def falha(msg):
        erros.append(msg)

    # 5. Rotas técnicas
    st, _, corpo, _ = cli.seguir("/healthz")
    if st != 200:
        falha(f"/healthz respondeu {st}")
    st, _, corpo, _ = cli.seguir("/version.txt")
    if st != 200:
        falha(f"/version.txt respondeu {st}")
    elif a.versao and corpo.decode().strip() != a.versao:
        falha(f"/version.txt = {corpo.decode().strip()!r}, esperado {a.versao!r}")
    for proibido in ("/.git/config", "/.gitignore", "/README.md", "/vercel.json"):
        st, _, _, _ = cli.seguir(proibido)
        if st != 404:
            falha(f"{proibido} deveria dar 404, deu {st}")

    paginas = []
    for raiz, dirs, arquivos in os.walk(a.pasta):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "_ci"]
        for nome in arquivos:
            if nome.endswith(".html"):
                rel = os.path.relpath(os.path.join(raiz, nome), a.pasta)
                paginas.append(rel)
    paginas.sort()

    links_vistos = {}
    for rel in paginas:
        limpa = url_limpa(rel)
        st, h, corpo, cadeia = cli.seguir(limpa, max_redir=0)
        if FORA_DA_IMAGEM.search(rel):
            if st == 404:
                avisos.append(f"{rel}: fora da imagem (dockerignore), não publicado")
            else:
                falha(f"{rel}: deveria estar fora da imagem, mas {limpa} respondeu {st}")
            continue
        # 1. URL limpa
        if st != 200 or "text/html" not in h.get("content-type", ""):
            falha(f"{rel}: {limpa} respondeu {st} ({h.get('content-type')})")
            continue
        ok += 1
        # 2. .html redireciona para a limpa, com query
        com_html = "/" + rel.replace(os.sep, "/")
        st2, h2, _ = cli.get(com_html + "?utm_source=teste&x=1")
        esperado = limpa + "?utm_source=teste&x=1"
        if st2 != 301 or h2.get("location") != esperado:
            falha(f"{com_html}?utm...: esperado 301 -> {esperado}, veio {st2} -> {h2.get('location')}")
        # 3. barra no fim
        if limpa != "/":
            st3, h3, _ = cli.get(limpa + "/")
            if st3 != 301 or h3.get("location") != limpa:
                falha(f"{limpa}/: esperado 301 -> {limpa}, veio {st3} -> {h3.get('location')}")
        # 4. links internos
        col = Coletor()
        col.feed(corpo.decode("utf-8", "replace"))
        for bruto in col.urls:
            if bruto.startswith(IGNORAR_ESQUEMAS) or "{{" in bruto or "${" in bruto:
                continue
            alvo = urljoin(a.base + limpa, bruto)
            p = urlsplit(alvo)
            if p.netloc and f"{p.scheme}://{p.netloc}" != cli.base:
                externos.add(p.netloc)
                continue
            caminho = unquote(p.path) + (f"?{p.query}" if p.query else "")
            if caminho not in links_vistos:
                links_vistos[caminho] = (cli.seguir(caminho), rel, bruto)

    # CSS locais: url(...) dentro deles
    for caminho, ((st, h, corpo, _), rel, bruto) in list(links_vistos.items()):
        if st == 200 and "text/css" in h.get("content-type", ""):
            for u in re.findall(r"url\(\s*['\"]?([^'\")]+)", corpo.decode("utf-8", "replace")):
                if u.startswith(IGNORAR_ESQUEMAS):
                    continue
                alvo = urljoin(a.base + caminho, u)
                p = urlsplit(alvo)
                if p.netloc and f"{p.scheme}://{p.netloc}" != cli.base:
                    externos.add(p.netloc)
                    continue
                c2 = unquote(p.path)
                if c2 not in links_vistos:
                    links_vistos[c2] = (cli.seguir(c2), caminho, u)

    quebrados = 0
    for caminho, ((st, h, corpo, cadeia), rel, bruto) in sorted(links_vistos.items()):
        if st != 200 and a.ignorar and re.search(a.ignorar, caminho):
            avisos.append(f"link quebrado CONHECIDO em {rel}: {bruto!r} -> {caminho} ({st})")
        elif st != 200:
            quebrados += 1
            falha(f"link quebrado em {rel}: {bruto!r} -> {caminho} ({' > '.join(f'{c}:{s}' for c, s in cadeia)})")
        elif len(cadeia) > 1:
            avisos.append(f"link com redirect em {rel}: {bruto!r} ({' > '.join(f'{c}:{s}' for c, s in cadeia)})")

    nome = os.path.basename(os.path.abspath(a.pasta))
    print(f"\n== {nome}: {ok} páginas OK, {len(links_vistos)} links internos testados, {quebrados} quebrados")
    if externos:
        print("   domínios externos usados: " + ", ".join(sorted(externos)))
    for m in avisos:
        print("   aviso: " + m)
    for m in erros:
        print("   ERRO: " + m)
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
