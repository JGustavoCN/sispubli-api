import pytest


@pytest.mark.e2e
def test_e2e_real_pdf_tunnel(real_client, token_real, cpf_teste):
    """
    DIRETRIZ: O Teste E2E Real (Live Debug - Falso PDF Sispubli).
    Testa se na origem real ele passa %PDF ou aborta com 502/504.
    """
    # 1. Lista os certificados reais
    resp_list = real_client.get(
        "/api/certificados", headers={"Authorization": f"Bearer {token_real}"}
    )
    assert resp_list.status_code == 200

    certificados = resp_list.json().get("data", {}).get("certificados", [])
    if not certificados:
        pytest.skip("Não há certificados na base para testar.")

    # Busca o primeiro certificado que tenha URL de download
    cert_com_url = next((c for c in certificados if c.get("url_download")), None)
    if not cert_com_url:
        pytest.skip("Nenhum dos certificados retornados possui URL de download disponível.")

    url_tunel = cert_com_url.get("url_download")
    resp_pdf = real_client.get(url_tunel)

    # Se o Sispubli falhar, nossa API deve retornar 502 ou 200 OK com PDF real
    if resp_pdf.status_code != 502:
        assert resp_pdf.status_code == 200
        assert resp_pdf.content.startswith(b"%PDF")
        assert resp_pdf.headers["content-type"] == "application/pdf"
