"""init-env: cria o .env da instalação local sem sobrescrever um existente."""
from cryptography.fernet import Fernet

from app import cli


def test_init_env_generates_keys_once(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env.example").write_text(
        "# comentário\nBORGES_ENV=development\nBORGES_SECRET_KEY=\nBORGES_ADMIN_EMAIL=admin@borges.local\n"
        "BORGES_ADMIN_PASSWORD=\nBORGES_ENCRYPTION_KEY=\n", encoding="utf-8")
    env = tmp_path / ".env"
    monkeypatch.setattr(cli, "ENV_FILE", env)
    cli.init_env("111, 222-333")
    values = cli._read_env(env)
    assert values["BORGES_ENV"] == "development" and len(values["BORGES_SECRET_KEY"]) > 40
    Fernet(values["BORGES_ENCRYPTION_KEY"].encode())  # chave válida
    assert values["BORGES_WINDSOR_ALLOWED_ACCOUNTS"] == "111,222-333"
    assert values["BORGES_ADMIN_PASSWORD"] in capsys.readouterr().out
    first = env.read_text(encoding="utf-8")
    cli.init_env("outra")
    assert env.read_text(encoding="utf-8") == first  # nunca sobrescreve: a chave de cifragem precisa ser estável
