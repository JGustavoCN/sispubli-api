from scraper import extract_data


def test_extract_data_sanity_mock():
    """
    Valida a extração de dados (token e certificados) de um HTML mockado do Sispubli.
    Garante que as expressões regulares e seletores BS4 estão funcionando.
    """
    mock_html = """
    <html>
        <body>
            <input type="hidden" name="wi.token" value="MOCK_TOKEN_12345">
            <table>
                <tr class="linha_par">
                    <td valign="center">Frequencia no Curso de Python</td>
                    <td>15/05/2023</td>
                    <td>1234</td>
                    <td>2023</td>
                    <td><a href="javascript:abrirCertificado('74839210055', '1', '1234', '2023', '0', '2023', '0')">Download</a></td>
                </tr>
            </table>
        </body>
    </html>
    """

    data = extract_data(mock_html)

    # Valida Token
    assert data["token"] == "MOCK_TOKEN_12345"

    # Valida Certificados
    assert len(data["certificates"]) == 1
    cert = data["certificates"][0]
    assert "Python" in cert["title"]
    assert cert["params"] == ["74839210055", "1", "1234", "2023", "0", "2023", "0"]


def test_extract_data_empty_html():
    """Garante que o extrator não crasha com HTML vazio."""
    data = extract_data("<html></html>")
    assert data["token"] is None
    assert data["certificates"] == []
