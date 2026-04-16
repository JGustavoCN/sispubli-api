"""
Testes do Scraper Sispubli — Milestone 1: Seguranca e Enriquecimento.

Cobertura:
    - mask_cpf: mascaramento de CPF
    - generate_cert_id: hash SHA-256 + SALT deterministico (64 chars)
    - montar_url: URL Template com {cpf} por tipo (1-11 + fallback)
    - extract_next_offset: deteccao de paginacao no HTML
    - fetch_all_certificates: motor iterativo com paginacao e cache
    - Campos enriquecidos: ano, tipo_codigo, tipo_descricao
    - Seguranca: CPF nao aparece em texto claro nas urls retornadas
"""

from unittest.mock import MagicMock, patch

from scraper import (
    TIPO_DESCRICAO_MAP,
    extract_next_offset,
    fetch_all_certificates,
    generate_cert_id,
    mask_cpf,
    montar_url,
)

# ---------------------------------------------------------------------------
# Fixtures: HTML mocks inline
# ---------------------------------------------------------------------------

MOCK_PAGE_1 = """
<html>
<body>
<FORM NAME="form" METHOD="POST" ACTION="indexCertificados.wsp">
  <INPUT NAME="wi.token" VALUE="TOKEN_MOCK_001" TYPE="hidden" />
  <INPUT NAME="tmp.tx_cpf" VALUE="12345678900" TYPE="hidden" />
  <table>
    <tr>
      <th>Descricao</th>
      <th>Imprimir</th>
    </tr>
    <tr>
      <td valign="center">
        Participacao no(a) Evento Alpha 2024
      </td>
      <td valign="center" align="center">
        <a href="javascript:abrirCertificado('12345678900', '1', '100', '200', '0', 2024, 0)">
          Imprimir
        </a>
      </td>
    </tr>
  </table>

  <a href="javascript:submitWIGrid('grid.certificadosDisponiveis',17)"
     class='nav_go'><b>Proximo</b></a>

</FORM>
</body>
</html>
"""

MOCK_PAGE_2 = """
<html>
<body>
<FORM NAME="form" METHOD="POST" ACTION="indexCertificados.wsp">
  <INPUT NAME="wi.token" VALUE="TOKEN_MOCK_002" TYPE="hidden" />
  <INPUT NAME="tmp.tx_cpf" VALUE="12345678900" TYPE="hidden" />
  <table>
    <tr>
      <th>Descricao</th>
      <th>Imprimir</th>
    </tr>
    <tr>
      <td valign="center">
        Participacao no(a) Evento Beta 2024
      </td>
      <td valign="center" align="center">
        <a href="javascript:abrirCertificado('12345678900', '2', '300', '400', '0', 2024, 0)">
          Imprimir
        </a>
      </td>
    </tr>
  </table>

  <!-- SEM link nav_go = ultima pagina -->

</FORM>
</body>
</html>
"""

MOCK_PAGE_INITIAL = """
<html>
<body>
<FORM NAME="form" METHOD="POST" ACTION="indexCertificados.wsp">
  <INPUT NAME="wi.token" VALUE="TOKEN_INITIAL" TYPE="hidden" />
</FORM>
</body>
</html>
"""


# ===================================================================
# TESTES UNITARIOS: mask_cpf
# ===================================================================


class TestMaskCpf:
    """Testes para a funcao de mascaramento de CPF."""

    def test_mask_cpf_formato_correto(self):
        """CPF com 11 digitos deve ser mascarado no formato ***.XXX.XXX-**."""
        result = mask_cpf("12345678900")
        assert result == "***.456.789-**"

    def test_mask_cpf_outro_cpf(self):
        """Segundo CPF para validar posicoes corretas."""
        result = mask_cpf("98765432100")
        assert result == "***.654.321-**"

    def test_mask_cpf_curto(self):
        """CPF com menos de 11 digitos retorna string mascarada generica."""
        result = mask_cpf("123")
        assert "***" in result

    def test_mask_cpf_vazio(self):
        """CPF vazio retorna string mascarada."""
        result = mask_cpf("")
        assert "***" in result


# ===================================================================
# TESTES UNITARIOS: generate_cert_id (SHA-256 + SALT)
# ===================================================================


class TestGenerateCertId:
    """Testes para geracao de ID unico via hash SHA-256 com SALT."""

    def test_hash_deterministico(self):
        """Mesmos parametros devem gerar o mesmo hash."""
        h1 = generate_cert_id("12345678900", "1", "100", "200")
        h2 = generate_cert_id("12345678900", "1", "100", "200")
        assert h1 == h2

    def test_hash_unicidade(self):
        """Parametros diferentes devem gerar hashes diferentes."""
        h1 = generate_cert_id("12345678900", "1", "100", "200")
        h2 = generate_cert_id("12345678900", "1", "100", "201")
        assert h1 != h2

    def test_hash_formato_sha256(self):
        """Hash deve ter 64 caracteres hexadecimais (SHA-256)."""
        h = generate_cert_id("12345678900", "1", "100", "200")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_diferente_sem_salt(self):
        """Hash com SALT deve diferir de um hash sem SALT para os mesmos dados.

        Garante que o SALT esta sendo efetivamente aplicado.
        """
        import hashlib

        raw_sem_salt = "12345678900" + "1" + "100" + "200"
        hash_sem_salt = hashlib.sha256(raw_sem_salt.encode()).hexdigest()
        hash_com_salt = generate_cert_id("12345678900", "1", "100", "200")
        # Podem ser iguais apenas se HASH_SALT for vazio — o que nao deve ocorrer
        # Em ambiente de teste, o SALT padrao e "chave_secreta_padrao"
        assert hash_com_salt != hash_sem_salt


# ===================================================================
# TESTES UNITARIOS: montar_url (URL Template)
# ===================================================================


class TestMontarUrl:
    """Testes para montagem de URL Template (sem CPF real)."""

    def test_tipo_1_participacao(self):
        """Tipo 1: URL template com {cpf}, sem CPF real."""
        params = ["12345678900", "1", "100", "200", "0", "2024", "0"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_participacao_process.wsp" in url
        assert "tmp.tx_cpf={cpf}" in url
        assert "12345678900" not in url  # CPF real nao deve aparecer
        assert "tmp.id_programa=100" in url
        assert "tmp.id_edicao=200" in url

    def test_tipo_2_autor(self):
        """Tipo 2: URL template de autor com {cpf}."""
        params = ["12345678900", "2", "300", "400", "0", "2024", "0"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_autor_process.wsp" in url
        assert "tmp.tx_cpf={cpf}" in url
        assert "12345678900" not in url

    def test_tipo_3_sub_evento(self):
        """Tipo 3: URL template de participacao em sub-evento."""
        params = ["12345678900", "3", "100", "200", "55", "2024", "0"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_participacao_sub_evento_process.wsp" in url
        assert "tmp.id_sub_evento=55" in url
        assert "tmp.tx_cpf={cpf}" in url

    def test_tipo_4_avaliacao(self):
        """Tipo 4: certificado de avaliacao."""
        params = ["12345678900", "4", "100", "200", "0", "2024", "0"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_avaliacao_process.wsp" in url
        assert "tmp.tx_cpf={cpf}" in url

    def test_tipo_5_avaliacao_programa(self):
        """Tipo 5: certificado de avaliacao de programa."""
        params = ["12345678900", "5", "100", "200", "0", "2024", "0"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_avaliacao_programa_process.wsp" in url

    def test_tipo_6_gerado_internamente(self):
        """Tipo 6: certificado interno — usa id_artigo, sem CPF na URL."""
        params = ["12345678900", "6", "100", "200", "0", "2024", "99"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_process.wsp" in url
        assert "tmp.id=99" in url
        assert "tmp.id_programa=100" in url
        assert "12345678900" not in url

    def test_tipo_7_orientador(self):
        """Tipo 7: certificado de orientacao com {cpf}."""
        params = ["12345678900", "7", "100", "200", "0", "2024", "88"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_orientador_process.wsp" in url
        assert "tmp.id_artigo=88" in url
        assert "tmp.tx_cpf={cpf}" in url

    def test_tipo_8_aluno_voluntario(self):
        """Tipo 8: certificado de aluno voluntario."""
        params = ["12345678900", "8", "100", "200", "0", "2024", "77"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_aluno_voluntario_process.wsp" in url
        assert "tmp.id_artigo=77" in url
        assert "tmp.tx_cpf={cpf}" in url

    def test_tipo_9_aluno_bolsista(self):
        """Tipo 9: certificado de aluno bolsista."""
        params = ["12345678900", "9", "100", "200", "0", "2024", "66"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_aluno_bolsista_process.wsp" in url
        assert "tmp.id_artigo=66" in url

    def test_tipo_10_ministrante_sub_evento(self):
        """Tipo 10: nao usa CPF na URL."""
        params = ["12345678900", "10", "100", "200", "55", "2024", "0"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_ministrante_sub_evento_process.wsp" in url
        assert "tmp.id_sub_evento=55" in url
        assert "12345678900" not in url

    def test_tipo_11_coorientador(self):
        """Tipo 11: certificado de coorientacao com {cpf}."""
        params = ["12345678900", "11", "100", "200", "0", "2024", "44"]
        url = montar_url(params)
        assert url is not None
        assert "certificado_coorientador_process.wsp" in url
        assert "tmp.id_artigo=44" in url
        assert "tmp.tx_cpf={cpf}" in url

    def test_tipo_desconhecido_retorna_none(self):
        """Tipo nao mapeado deve retornar None."""
        params = ["12345678900", "99", "100", "200", "0", "2024", "0"]
        url = montar_url(params)
        assert url is None

    def test_url_usa_template_cpf(self):
        """SEGURANCA: todas as URLs que referenciam CPF devem usar {cpf}, nao o CPF real."""
        cpf_real = "12345678900"
        for tipo in ["1", "2", "3", "4", "5", "7", "8", "9", "11"]:
            params = [cpf_real, tipo, "100", "200", "55", "2024", "88"]
            url = montar_url(params)
            assert url is not None, f"URL nao gerada para tipo {tipo}"
            assert cpf_real not in url, f"CPF real encontrado na URL do tipo {tipo}: {url}"
            if "tmp.tx_cpf" in url:
                assert "{cpf}" in url, f"Template {{cpf}} ausente na URL do tipo {tipo}"


# ===================================================================
# TESTES UNITARIOS: extract_next_offset
# ===================================================================


class TestExtractNextOffset:
    """Testes para extracao do offset de paginacao do HTML."""

    def test_offset_presente(self):
        """HTML com link nav_go deve retornar o offset numerico."""
        offset = extract_next_offset(MOCK_PAGE_1)
        assert offset == 17

    def test_offset_ausente(self):
        """HTML sem link nav_go deve retornar None."""
        offset = extract_next_offset(MOCK_PAGE_2)
        assert offset is None

    def test_offset_pagina_vazia(self):
        """HTML minimo (sem formulario) retorna None."""
        offset = extract_next_offset("<html><body></body></html>")
        assert offset is None


# ===================================================================
# TESTES DE INTEGRACAO MOCKADA: fetch_all_certificates
# ===================================================================


class TestFetchAllCertificates:
    """Testes do motor iterativo com paginacao mockada."""

    def setup_method(self):
        """Limpa o cache antes de cada teste para isolamento."""
        fetch_all_certificates.cache_clear()

    def teardown_method(self):
        """Limpa o cache apos cada teste."""
        fetch_all_certificates.cache_clear()

    @patch("scraper.requests.Session")
    def test_pagination_two_pages(self, mock_session_class):
        """Simula 2 paginas: pagina 1 com 'Proximo', pagina 2 sem.
        Valida que 2 POSTs sao feitos e o total e a soma.
        """
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.text = MOCK_PAGE_INITIAL
        mock_session.get.return_value = mock_get_response

        mock_post_response_1 = MagicMock()
        mock_post_response_1.status_code = 200
        mock_post_response_1.text = MOCK_PAGE_1

        mock_post_response_2 = MagicMock()
        mock_post_response_2.status_code = 200
        mock_post_response_2.text = MOCK_PAGE_2

        mock_session.post.side_effect = [
            mock_post_response_1,
            mock_post_response_2,
        ]

        result = fetch_all_certificates("12345678900")

        assert result["usuario_id"] == "***.456.789-**"
        assert result["total"] == 2
        assert len(result["certificados"]) == 2
        assert mock_session.post.call_count == 2

        titulos = [c["titulo"] for c in result["certificados"]]
        assert "Participacao no(a) Evento Alpha 2024" in titulos
        assert "Participacao no(a) Evento Beta 2024" in titulos

        for cert in result["certificados"]:
            assert "id_unico" in cert
            assert "titulo" in cert
            assert "url_download" in cert
            assert "ano" in cert
            assert "tipo_codigo" in cert
            assert "tipo_descricao" in cert
            # SHA-256 = 64 chars
            assert len(cert["id_unico"]) == 64

    @patch("scraper.requests.Session")
    def test_single_page_no_pagination(self, mock_session_class):
        """Simula retorno de pagina unica (sem link nav_go).
        Valida que apenas 1 POST e feito.
        """
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.text = MOCK_PAGE_INITIAL
        mock_session.get.return_value = mock_get_response

        mock_post_response = MagicMock()
        mock_post_response.status_code = 200
        mock_post_response.text = MOCK_PAGE_2
        mock_session.post.return_value = mock_post_response

        result = fetch_all_certificates("12345678900")

        assert result["total"] == 1
        assert mock_session.post.call_count == 1

    @patch("scraper.requests.Session")
    def test_campos_enriquecidos(self, mock_session_class):
        """Valida campos de enriquecimento: ano, tipo_codigo, tipo_descricao."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = MOCK_PAGE_INITIAL
        mock_session.get.return_value = mock_get

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.text = MOCK_PAGE_1  # tipo=1, ano=2024
        mock_session.post.return_value = mock_post

        result = fetch_all_certificates("12345678900")

        assert result["total"] >= 1
        cert = result["certificados"][0]

        assert cert["ano"] == 2024
        assert cert["tipo_codigo"] == 1
        assert cert["tipo_descricao"] == "Participacao"

    @patch("scraper.requests.Session")
    def test_url_download_usa_template(self, mock_session_class):
        """SEGURANCA: url_download nao deve conter o CPF real."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = MOCK_PAGE_INITIAL
        mock_session.get.return_value = mock_get

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.text = MOCK_PAGE_1
        mock_session.post.return_value = mock_post

        result = fetch_all_certificates("12345678900")

        for cert in result["certificados"]:
            if cert["url_download"]:
                assert "12345678900" not in cert["url_download"], (
                    f"CPF real encontrado na url_download: {cert['url_download']}"
                )

    @patch("scraper.requests.Session")
    def test_lru_cache_reutiliza_resultado(self, mock_session_class):
        """lru_cache: segunda chamada com mesmo CPF nao bate no Sispubli."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = MOCK_PAGE_INITIAL
        mock_session.get.return_value = mock_get

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.text = MOCK_PAGE_2
        mock_session.post.return_value = mock_post

        result1 = fetch_all_certificates("99988877766")
        result2 = fetch_all_certificates("99988877766")

        assert result1 is result2  # mesmo objeto em memoria (cache hit)
        assert mock_session.get.call_count == 1  # GET feito apenas uma vez


# ===================================================================
# TESTES DE ESTRUTURA DE RETORNO
# ===================================================================


class TestResultStructure:
    """Valida a estrutura completa do dicionario de retorno."""

    def setup_method(self):
        fetch_all_certificates.cache_clear()

    def teardown_method(self):
        fetch_all_certificates.cache_clear()

    @patch("scraper.requests.Session")
    def test_chaves_obrigatorias(self, mock_session_class):
        """Resultado deve conter usuario_id, total e certificados."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = MOCK_PAGE_INITIAL
        mock_session.get.return_value = mock_get

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.text = MOCK_PAGE_2
        mock_session.post.return_value = mock_post

        result = fetch_all_certificates("12345678900")

        assert "usuario_id" in result
        assert "total" in result
        assert "certificados" in result

        assert isinstance(result["usuario_id"], str)
        assert isinstance(result["total"], int)
        assert isinstance(result["certificados"], list)

        for cert in result["certificados"]:
            assert isinstance(cert, dict)
            assert "id_unico" in cert
            assert "titulo" in cert
            assert "url_download" in cert
            assert "ano" in cert
            assert "tipo_codigo" in cert
            assert "tipo_descricao" in cert


# ===================================================================
# TESTES: TIPO_DESCRICAO_MAP
# ===================================================================


class TestTipoDescricaoMap:
    """Valida o mapeamento de codigos para descricoes."""

    def test_tipos_conhecidos(self):
        """Tipos de 1 a 11 devem ter descricao mapeada."""
        tipos_esperados = {
            "1": "Participacao",
            "2": "Autor",
            "3": "Mini-Curso",
            "4": "Avaliacao",
            "7": "Orientacao",
            "11": "Coorientacao",
        }
        for codigo, descricao in tipos_esperados.items():
            assert TIPO_DESCRICAO_MAP[codigo] == descricao

    def test_cobertura_completa_tipos(self):
        """Todos os tipos mapeados no URL_TYPE_MAP devem ter descricao."""
        from scraper import URL_TYPE_MAP

        for tipo in URL_TYPE_MAP:
            assert tipo in TIPO_DESCRICAO_MAP, f"Tipo {tipo} sem descricao no TIPO_DESCRICAO_MAP"


# ===================================================================
# Fim dos testes do scraper
# ===================================================================
