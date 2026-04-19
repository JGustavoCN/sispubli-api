"""
Servicos de Proxy e Streaming de PDF — Sispubli API.
"""

from collections.abc import AsyncGenerator

import httpx

from src.core.logger import logger

log = logger.bind(module=__name__)


async def pdf_streamer(
    client: httpx.AsyncClient,
    first_chunk: bytes,
    upstream_response: httpx.Response,
    content_iterator: AsyncGenerator[bytes],
) -> AsyncGenerator[bytes]:
    """Gerador assincrono que consome o PDF do Sispubli em pedacos.

    Garante o fechamento correto do client HTTP ao final do stream.
    """
    try:
        yield first_chunk
        total_bytes = len(first_chunk)
        async for chunk in content_iterator:
            total_bytes += len(chunk)
            yield chunk

        log.info(f"✅ [TUNEL SUCESSO] Certificado entregue. Total: {total_bytes} bytes.")
    except Exception as e:
        log.error(f"❌ [TUNEL ERRO] Falha durante o streaming: {str(e)}")
    finally:
        await upstream_response.aclose()
        await client.aclose()


async def get_certificate_stream(
    url: str,
    base_sispubli: str,
) -> tuple[httpx.AsyncClient, bytes, httpx.Response, AsyncGenerator[bytes]]:
    """Executa a logica de Gatilho e Captura do Sispubli.

    Retorna os componentes necessarios para iniciar o StreamingResponse.

    Raises:
        httpx.HTTPError: Em caso de erro na comunicacao.
        ValueError: Em caso de PDF invalido ou erro logico.
    """
    browser_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",  # noqa: E501
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    }

    client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    try:
        # ETAPA A: O Gatilho (Arma o PDF no backend)
        prep_response = await client.get(url, headers=browser_headers)
        if prep_response.status_code >= 400:
            await client.aclose()
            raise ValueError(f"falha_gatilho:{prep_response.status_code}")

        # ETAPA B: A Captura (Requisita o binario)
        target_url = f"{base_sispubli}/publicacoes/ReportConnector.wsp?tmp.reportShow=true"
        pdf_headers = browser_headers.copy()
        pdf_headers["Referer"] = url

        stream_req = client.build_request("GET", target_url, headers=pdf_headers)
        upstream_response = await client.send(stream_req, stream=True)

        if upstream_response.status_code != 200:
            await upstream_response.aclose()
            await client.aclose()
            raise ValueError(f"upstream_refusal:{upstream_response.status_code}")

        # Validacao de Magic Bytes (%PDF-)
        content_iterator = upstream_response.aiter_bytes()
        try:
            primeiro_chunk = await anext(content_iterator)
        except StopAsyncIteration:
            primeiro_chunk = b""

        if not primeiro_chunk.lstrip().startswith(b"%PDF-"):
            log.error("❌ [TUNEL ERRO] O Sispubli retornou HTML/Erro em vez de PDF!")
            log.error(f"Conteudo inicial: {primeiro_chunk[:100]!r}")
            await upstream_response.aclose()
            await client.aclose()
            raise ValueError("fake_pdf")

        return client, primeiro_chunk, upstream_response, content_iterator

    except Exception:
        if "client" in locals():
            await client.aclose()
        raise
