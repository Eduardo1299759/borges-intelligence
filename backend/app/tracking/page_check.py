"""Agente 08 — Tracking & CRO: verificação de uma página de destino.

O que é conferido no HTML entregue pelo servidor: HTTPS, resposta 200, tempo e tamanho, versão para celular
(meta viewport), Pixel da Meta, Google Tag Manager, GA4, tag do Google Ads, formulários e link de WhatsApp.
Limite: tags inseridas depois, por JavaScript ou pelo próprio GTM, não aparecem no HTML; nesse caso o resultado
diz "não encontrado no HTML", não "ausente".

Segurança (o servidor acessa um endereço digitado por um usuário): só http/https nas portas 80/443, só
endereços IP públicos (nada de rede interna, localhost ou metadados de nuvem), redirecionamentos seguidos um a
um e conferidos de novo, no máximo 10 s e 3 MB.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 3_000_000
TIMEOUT = 10.0
MAX_REDIRECTS = 4
UA = "BorgesIntelligence-PageCheck/1.0"


class PageCheckError(ValueError):
    pass


def resolve(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def assert_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise PageCheckError("Só endereços http:// ou https:// podem ser verificados.")
    if not parts.hostname:
        raise PageCheckError("Endereço inválido.")
    if parts.port not in (None, 80, 443):
        raise PageCheckError("Só as portas padrão (80 e 443) são permitidas.")
    try:
        addresses = resolve(parts.hostname)
    except socket.gaierror as exc:
        raise PageCheckError("Não foi possível encontrar este domínio.") from exc
    for addr in addresses:
        if not ipaddress.ip_address(addr.split("%")[0]).is_global:
            raise PageCheckError("Endereço não público (rede interna ou local) não pode ser verificado.")


def fetch(url: str, client: httpx.Client) -> tuple[httpx.Response, bytes, float, list[str]]:
    chain = []
    started = time.monotonic()
    for _ in range(MAX_REDIRECTS + 1):
        assert_public(url)
        chain.append(url)
        with client.stream("GET", url, headers={"User-Agent": UA}, follow_redirects=False) as resp:
            if resp.is_redirect and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                continue
            body = b""
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise PageCheckError("Página maior que 3 MB; verificação interrompida.")
            return resp, body, time.monotonic() - started, chain
    raise PageCheckError("Redirecionamentos demais.")


PATTERNS = {
    "meta_pixel": re.compile(r"connect\.facebook\.net/[^\"']*/fbevents\.js|fbq\(\s*['\"]init", re.I),
    "gtm": re.compile(r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]{4,}", re.I),
    "ga4": re.compile(r"gtag/js\?id=G-[A-Z0-9]+|['\"]G-[A-Z0-9]{6,}['\"]", re.I),
    "google_ads": re.compile(r"['\"=]AW-\d{6,}", re.I),
    "viewport": re.compile(r"<meta[^>]+name=['\"]viewport['\"]", re.I),
    "form": re.compile(r"<form\b", re.I),
    "whatsapp": re.compile(r"wa\.me/|api\.whatsapp\.com/send|whatsapp://send", re.I),
}
IDS = {
    "meta_pixel": re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{10,20})['\"]"),
    "gtm": re.compile(r"(GTM-[A-Z0-9]{4,})"),
    "ga4": re.compile(r"(G-[A-Z0-9]{6,})"),
    "google_ads": re.compile(r"(AW-\d{6,})"),
}


def check(url: str, client: httpx.Client | None = None) -> dict[str, Any]:
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        resp, body, seconds, chain = fetch(url.strip(), client)
    except httpx.HTTPError as exc:
        raise PageCheckError(f"Não foi possível abrir a página ({type(exc).__name__}).") from exc
    finally:
        if own:
            client.close()
    html = body.decode(resp.encoding or "utf-8", errors="replace")
    final = chain[-1]
    found = {k: bool(p.search(html)) for k, p in PATTERNS.items()}
    ids = {k: sorted(set(p.findall(html)))[:3] for k, p in IDS.items()}
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)

    items = []

    def item(key: str, label: str, ok: bool | None, detail: str, severity: str) -> None:
        items.append({"key": key, "label": label, "ok": ok, "detail": detail, "severity": severity})

    item("status", "Página responde", resp.status_code == 200, f"HTTP {resp.status_code}", "alta")
    item("https", "HTTPS", final.startswith("https://"), "Endereço final: " + final, "alta")
    item("speed", "Tempo de carregamento do HTML", seconds <= 3, f"{seconds:.1f} s (sem imagens e scripts)".replace(
        ".", ","), "media")
    item("size", "Tamanho do HTML", len(body) <= 1_500_000, f"{len(body) / 1024:.0f} KB", "baixa")
    item("viewport", "Pronta para celular (meta viewport)", found["viewport"],
         "Encontrada" if found["viewport"] else "Sem meta viewport: a página pode aparecer miniaturizada no celular.",
         "alta")
    for key, label in (("meta_pixel", "Pixel da Meta"), ("gtm", "Google Tag Manager"), ("ga4", "Google Analytics 4"),
                       ("google_ads", "Tag do Google Ads")):
        detail = ", ".join(ids[key]) if ids[key] else ("Encontrado" if found[key] else
                                                       "Não encontrado no HTML (pode estar dentro do GTM)")
        item(key, label, True if found[key] else (None if found["gtm"] and key != "gtm" else False), detail,
             "alta" if key == "meta_pixel" else "media")
    item("conversion_path", "Caminho de conversão (formulário ou WhatsApp)", found["form"] or found["whatsapp"],
         ", ".join(x for x, ok in (("formulário", found["form"]), ("link de WhatsApp", found["whatsapp"])) if ok)
         or "Nenhum formulário nem link de WhatsApp no HTML.", "media")
    return {"url": url, "final_url": final, "redirects": chain[1:], "status": resp.status_code,
            "seconds": round(seconds, 2), "bytes": len(body), "title": title.group(1).strip()[:200] if title else None,
            "items": items, "problems": sum(1 for i in items if i["ok"] is False),
            "notes": ["Verifica o HTML entregue pelo servidor; tags inseridas por JavaScript ou pelo GTM aparecem "
                      "como 'não encontrado no HTML' ou 'possível via GTM'.",
                      "Para confirmar disparos de eventos, use o Gerenciador de Eventos da Meta e o Tag Assistant."]}
