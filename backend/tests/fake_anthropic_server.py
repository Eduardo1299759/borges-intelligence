"""Anthropic falsa para testes de navegador: responde /v1/messages com uma resposta que só usa números dos
fatos recebidos. Uso: python -m tests.fake_anthropic_server 8098 e BORGES_ANTHROPIC_BASE_URL=http://127.0.0.1:8098
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        facts = json.loads(body["messages"][0]["content"].split("Fatos (JSON):\n", 1)[1])
        first = facts["recommendations"][0]
        answer = (f"Resposta de teste da IA. No período {facts['period']}, o investimento foi de "
                  f"{facts['account']['investimento']}. Prioridade: {first['title']}.")
        payload = {"id": "msg_fake", "type": "message", "role": "assistant", "model": body["model"],
                   "content": [{"type": "text", "text": json.dumps(
                       {"answer": answer, "relevant_recommendation_ids": [first["id"]]}, ensure_ascii=False)}],
                   "stop_reason": "end_turn", "stop_sequence": None,
                   "usage": {"input_tokens": 8000, "output_tokens": 900}}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8098), Handler).serve_forever()
