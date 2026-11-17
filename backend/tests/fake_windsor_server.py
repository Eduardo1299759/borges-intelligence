"""Sobe o Windsor.ai falso como servidor HTTP local, para testes de ponta a ponta no navegador.

Uso: python -m tests.fake_windsor_server 8099
     e inicie a API com BORGES_WINDSOR_BASE_URL=http://127.0.0.1:8099
A chave aceita é tests.windsor_fake.VALID_KEY. Nunca aponte um ambiente real para este servidor.
"""
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from tests.windsor_fake import FakeWindsor

fake = FakeWindsor()


class Handler(BaseHTTPRequestHandler):
    def _reply(self, request: httpx.Request) -> None:
        resp = fake(request)
        self.send_response(resp.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp.content)

    def do_GET(self):  # noqa: N802
        self._reply(httpx.Request("GET", f"http://fake{self.path}"))

    def do_POST(self):  # noqa: N802  (ações de escrita)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._reply(httpx.Request("POST", f"http://fake{self.path}", content=body))

    def log_message(self, *args):  # silencioso: a URL contém a chave
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8099), Handler).serve_forever()
