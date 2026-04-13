from bs4 import BeautifulSoup
import re
import requests

URL = "http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp"


def extract_data(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Extrair token
    token_input = soup.find("input", {"name": "wi.token"})
    token = token_input["value"] if token_input else None

    certificates = []

    # Extrair certificados
    # Os certificados estão em uma tabela dentro de <tr> após o cabeçalho "Descrição" e "Imprimir"
    # Procuramos links que chamam abrirCertificado
    links = soup.find_all("a", href=re.compile(r"abrirCertificado"))

    for link in links:
        href = link["href"]
        # Regex para extrair parâmetros: abrirCertificado('...', '...', ...)
        match = re.search(r"abrirCertificado\((.*?)\)", href)
        if match:
            # Pegar os parâmetros e remover aspas simples e espaços extras
            params_raw = match.group(1).split(",")
            params = [p.strip().replace("'", "") for p in params_raw]

            # O título está no <td> anterior ao link (o link está no seu próprio <td>)
            # Estrutura: <tr> <td>Título</td> <td><a>...</a></td> </tr>
            row = link.find_parent("tr")
            if row:
                title_td = row.find("td", valign="center", align=None)
                if title_td:
                    title = title_td.get_text(strip=True)
                    certificates.append({"title": title, "params": params})

    return {"token": token, "certificates": certificates}


def fetch_certificates(cpf):
    session = requests.Session()

    # 1. GET para pegar cookies e token inicial
    response_get = session.get(URL)
    if response_get.status_code != 200:
        raise Exception(f"Erro ao acessar página inicial: {response_get.status_code}")

    # Extrair token do HTML inicial
    initial_data = extract_data(response_get.text)
    token = initial_data["token"]

    if not token:
        raise Exception("Token não encontrado na página inicial")

    # 2. POST com o CPF e o token
    payload = {
        "wi.page.prev": "site/indexCertificados",
        "wi.token": token,
        "tmp.acao": "",
        "tmp.params": "",
        "tmp.tx_cpf": cpf,
    }

    response_post = session.post(URL, data=payload)
    if response_post.status_code != 200:
        raise Exception(f"Erro ao enviar POST: {response_post.status_code}")

    # 3. Extrair dados da resposta final
    return extract_data(response_post.text)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    cpf = os.getenv("CPF_TESTE")

    if not cpf:
        print("Erro: CPF_TESTE não definido no .env")
    else:
        print(f"Buscando certificados para CPF: {cpf[:3]}***{cpf[-2:]}...")
        try:
            result = fetch_certificates(cpf)
            print(f"\nToken encontrado: {result['token']}")
            print(f"Total de certificados encontrados: {len(result['certificates'])}")

            for i, cert in enumerate(result["certificates"], 1):
                print(f"\n[{i}] {cert['title']}")
                print(f"    Parâmetros: {', '.join(cert['params'])}")
        except Exception as e:
            print(f"Ocorreu um erro: {e}")
