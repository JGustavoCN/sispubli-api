from fastapi.testclient import TestClient

from src.core.security import gerar_ticket_pdf
from src.main import app

client = TestClient(app)

valid_ticket = gerar_ticket_pdf("http://intranet.ifs.edu.br/publicacoes/site/foo.pdf")


def test_magic_bytes_pass(mock_httpx_success):
    """
    DIRETRIZ 1: Teste dos Magic Bytes.
    Garante que quando o Sispubli envia um PDF correto com magic bytes '%PDF',
    nossa API valida e repassa pro Browser do usuario intocado.
    """
    response = client.get(f"/api/pdf/{valid_ticket}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"


def test_anti_falso_pdf_block(mock_httpx_fake_pdf):
    """
    DIRETRIZ 2: Teste Anti-Falso PDF (Interceptacao).
    Agora a API deve retornar 502 Bad Gateway ao detectar HTML em vez de PDF
    antes mesmo de comecar o streaming pro cliente.
    """
    response = client.get(f"/api/pdf/{valid_ticket}")

    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "fake_pdf"
    assert "PDF valido" in data["error"]["message"]


def test_tunnel_timeout_handling(mock_httpx_timeout):
    """Garante que timeouts no upstream retornam 504 Gateway Timeout."""
    response = client.get(f"/api/pdf/{valid_ticket}")
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "gateway_timeout"


def test_tunnel_upstream_refusal(mock_httpx_refusal):
    """Garante que falhas no gatilho retornam 502 Bad Gateway."""
    response = client.get(f"/api/pdf/{valid_ticket}")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_injecao_cpf_no_ticket_unitario(monkeypatch):
    """
    DIRETRIZ 4: Teste de Injecao de CPF (Anti-Blank Page).
    Garante que a API substitui o placeholder '{cpf}' pelo CPF real do usuario
    dentro do Ticket encriptado, evitando o erro de 'Pagina em Branco' do JasperReports.
    """
    from src.core.security import ler_ticket_pdf

    cpf_fake = "74839210055"
    mock_certs = {
        "usuario_id": "***.222.333-**",
        "total": 1,
        "certificados": [
            {
                "id_unico": "hash123",
                "titulo": "Certificado Teste",
                "url_download": "http://servidor.com/relat?cpf={cpf}&id=99",
                "ano": 2024,
                "tipo_codigo": 1,
                "tipo_descricao": "Participacao",
            }
        ],
    }

    # Mockamos o scraper para retornar o placeholder literal
    monkeypatch.setattr("src.certificates.router.fetch_all_certificates", lambda x: mock_certs)
    # Mockamos a validacao do token de sessao para retornar nosso CPF fake
    monkeypatch.setattr("src.certificates.router.ler_token_sessao", lambda x: cpf_fake)

    # Chamamos a rota de listagem (o token 'xyz' é ignorado pelo mock)
    response = client.get("/api/certificados", headers={"Authorization": "Bearer xyz"})

    assert response.status_code == 200
    data = response.json()["data"]
    url_com_ticket = data["certificados"][0]["url_download"]

    # Extraimos o ticket da URL /api/pdf/{ticket}
    ticket = url_com_ticket.replace("/api/pdf/", "")

    # Descriptografamos para ver se o CPF fake entrou no lugar de {cpf}
    url_real_decrypted = ler_ticket_pdf(ticket)

    assert cpf_fake in url_real_decrypted
    assert "{cpf}" not in url_real_decrypted
    assert url_real_decrypted == f"http://servidor.com/relat?cpf={cpf_fake}&id=99"
