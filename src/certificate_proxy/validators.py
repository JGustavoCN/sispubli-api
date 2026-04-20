"""
Validadores de Seguranca para o Tunel de PDF — Sispubli API.
"""

import ipaddress
import socket

from src.core.logger import logger

log = logger.bind(module=__name__)


def is_safe_host(hostname: str) -> bool:
    """Valida hostname contra ataques SSRF (DNS rebinding, IP privado).

    Camada de defesa que garante que o host e o IP resolvido sao seguros:
        1. Hostname deve ser exatamente 'intranet.ifs.edu.br'
        2. IP resolvido nao pode ser privado, loopback ou link-local

    Args:
        hostname: Nome do host extraido da URL decriptada do ticket.

    Returns:
        True se seguro, False se bloqueado por politica de seguranca.
    """
    if hostname != "intranet.ifs.edu.br":
        log.warning(f"SSRF: hostname rejeitado: {hostname}")
        return False

    try:
        ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip)

        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            log.warning(f"SSRF: DNS rebinding detectado — {hostname} resolve para {ip}")
            return False
    except Exception:
        log.warning(f"SSRF: falha ao resolver DNS de {hostname}")
        return False

    return True
