"""
Motor de Criptografia — Sispubli API.

Modulo responsavel por toda operacao criptografica da API:
    - Tokens de sessao (Fernet + TTL 15 min) para autenticacao
    - Tickets de PDF (Fernet SEM TTL) para download compartilhavel
    - Derivacao de session_hash (SHA-256 + SECRET_PEPPER) para cache
    - Normalizacao de CPF (remove caracteres nao-numericos)

Variaveis de ambiente obrigatorias:
    FERNET_SECRET_KEY  — Chave Fernet simetrica (32 bytes base64)
    SECRET_PEPPER      — Segredo para derivacao do session_hash

Gerar chaves:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    python -c "import secrets; print(secrets.token_urlsafe(32))"
"""

import hashlib
import os
import re

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from logger import logger

# Garante que as variáveis do .env (como FERNET_SECRET_KEY) estejam disponíveis
load_dotenv()

log = logger.bind(module=__name__)

# ---------------------------------------------------------------------------
# Configuracao via variaveis de ambiente
# ---------------------------------------------------------------------------

# Chave Fernet — em producao o lifespan do FastAPI valida presenca
_fernet_key = os.environ.get("FERNET_SECRET_KEY", "")
if not _fernet_key:
    # Gera chave efemera para desenvolvimento/testes — NAO use em producao
    _fernet_key = Fernet.generate_key().decode()
    log.warning("FERNET_SECRET_KEY nao definida — usando chave efemera (apenas dev/test)")

_fernet = Fernet(_fernet_key.encode() if isinstance(_fernet_key, str) else _fernet_key)

# Pepper para derivar session_hash — segredo distinto da chave Fernet
SECRET_PEPPER = os.environ.get("SECRET_PEPPER", "pepper_padrao_dev")

# TTL do token de sessao em segundos (15 minutos)
TOKEN_TTL_SECONDS = 15 * 60

# Tamanho maximo para tokens/tickets (protecao anti-DoS)
MAX_TOKEN_LENGTH = 500


# ===================================================================
# NORMALIZACAO
# ===================================================================


def normalizar_cpf(cpf: str) -> str:
    """Remove caracteres nao numericos de um CPF.

    Permite aceitar entradas como '123.456.789-00', '123 456 789 00',
    etc., normalizando para '12345678900' antes de criptografar.

    Args:
        cpf: String do CPF em qualquer formato.

    Returns:
        String contendo apenas digitos numericos do CPF.
    """
    return re.sub(r"\D", "", cpf)


# ===================================================================
# TOKEN DE SESSAO (Fernet + TTL)
# ===================================================================


def gerar_token_sessao(cpf: str) -> str:
    """Gera um token de sessao criptografado para o CPF.

    O CPF e normalizado, criptografado via Fernet e retornado como
    string URL-safe. O token tem TTL implicito de 15 minutos,
    validado na leitura via ler_token_sessao().

    Args:
        cpf: CPF do titular (aceita formatos com pontuacao).

    Returns:
        Token criptografado como string URL-safe.
    """
    cpf_limpo = normalizar_cpf(cpf)
    token = _fernet.encrypt(cpf_limpo.encode("utf-8"))
    log.debug(f"Token de sessao gerado para CPF normalizado ({len(cpf_limpo)} digitos)")
    return token.decode("utf-8")


def ler_token_sessao(token: str) -> str:
    """Descriptografa e valida um token de sessao.

    Verifica:
        1. Tamanho maximo (anti-DoS)
        2. Integridade criptografica (Fernet)
        3. TTL de 15 minutos (expiracao)

    Args:
        token: Token criptografado recebido do cliente.

    Returns:
        CPF descriptografado (apenas digitos).

    Raises:
        ValueError: Token excede tamanho maximo (500 chars).
        cryptography.fernet.InvalidToken: Token invalido ou expirado.
    """
    if len(token) > MAX_TOKEN_LENGTH:
        log.warning(
            f"Token rejeitado por tamanho excessivo: {len(token)} chars (max {MAX_TOKEN_LENGTH})"
        )
        raise ValueError(f"Token excede tamanho maximo de {MAX_TOKEN_LENGTH} caracteres")

    cpf_bytes = _fernet.decrypt(token.encode("utf-8"), ttl=TOKEN_TTL_SECONDS)
    cpf = cpf_bytes.decode("utf-8")
    log.debug("Token de sessao validado com sucesso")
    return cpf


# ===================================================================
# TICKET DE PDF (Fernet SEM TTL)
# ===================================================================


def gerar_ticket_pdf(url: str) -> str:
    """Gera um ticket criptografado para download de PDF.

    O ticket NAO tem TTL — e um 'encurtador eterno' para permitir
    compartilhamento de links de certificados.

    Args:
        url: URL completa do certificado no Sispubli.

    Returns:
        Ticket criptografado como string URL-safe.
    """
    ticket = _fernet.encrypt(url.encode("utf-8"))
    log.debug(f"Ticket de PDF gerado ({len(ticket)} bytes)")
    return ticket.decode("utf-8")


def ler_ticket_pdf(ticket: str) -> str:
    """Descriptografa um ticket de PDF (sem validacao de TTL).

    Verifica:
        1. Tamanho maximo (anti-DoS)
        2. Integridade criptografica (Fernet)
        NÃO verifica TTL (ticket eterno).

    Args:
        ticket: Ticket criptografado recebido do cliente.

    Returns:
        URL original do certificado no Sispubli.

    Raises:
        ValueError: Ticket excede tamanho maximo (500 chars).
        cryptography.fernet.InvalidToken: Ticket invalido/corrompido.
    """
    if len(ticket) > MAX_TOKEN_LENGTH:
        log.warning(
            f"Ticket rejeitado por tamanho excessivo: {len(ticket)} chars (max {MAX_TOKEN_LENGTH})"
        )
        raise ValueError(f"Ticket excede tamanho maximo de {MAX_TOKEN_LENGTH} caracteres")

    # Sem TTL — decrypt sem parametro ttl
    url_bytes = _fernet.decrypt(ticket.encode("utf-8"))
    url = url_bytes.decode("utf-8")
    log.debug("Ticket de PDF descriptografado com sucesso")
    return url


# ===================================================================
# SESSION HASH (SHA-256 + PEPPER)
# ===================================================================


def derivar_session_hash(token: str) -> str:
    """Deriva um hash publico do token para uso como cache key.

    Usa SHA-256 com SECRET_PEPPER para impedir correlacao de sessoes
    ou ataques de dicionario via logs/CDN.

    O hash e deterministico: mesmo token sempre gera o mesmo hash.

    Args:
        token: Token de sessao criptografado.

    Returns:
        Hash hexadecimal de 64 caracteres (SHA-256).
    """
    raw = f"{SECRET_PEPPER}{token}"
    session_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    log.debug(f"Session hash derivado: {session_hash[:16]}...")
    return session_hash
