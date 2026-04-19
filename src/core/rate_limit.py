"""
Rate Limiter — Sispubli API.

Controle de taxa de requisicoes em memoria com sliding window.
Implementa protecao contra abuso de IP e viralização de tickets.

Componentes:
    - extrair_ip_real(request): Resolve IP real via headers Vercel
    - RateLimiter: Classe de sliding window com asyncio.Lock

Instancias pre-configuradas:
    - ip_limiter: 20 req/min por IP (anti-bot no tunnel PDF)
    - ticket_limiter: 100 req/h por ticket (anti-viral)
    - auth_limiter: 5 req/min por IP (anti-enumeracao CPF)

Limitacoes conhecidas (aceitas para MVP):
    - Rate limit em memoria: nao persiste entre cold starts da Vercel
    - Nao e globalmente consistente entre multiplas instancias
    - Evolucao futura: Upstash Redis (Serverless Free Tier)
"""

import asyncio
import time

from src.core.logger import logger

log = logger.bind(module=__name__)


# ===================================================================
# EXTRACAO DE IP REAL
# ===================================================================


def extrair_ip_real(request) -> str:
    """Resolve o IP real do cliente a partir dos headers HTTP.

    Ordem de prioridade (compativel com Vercel/Cloudflare):
        1. x-forwarded-for (primeiro IP da lista)
        2. x-real-ip
        3. request.client.host (fallback direto)
        4. '0.0.0.0' (ultimo recurso se client for None)

    Args:
        request: Objeto Request do FastAPI/Starlette.

    Returns:
        String com o IP do cliente.
    """
    headers = request.headers

    # x-forwarded-for: pode conter lista separada por virgula
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        log.debug(f"IP extraido de x-forwarded-for: {ip}")
        return ip

    # x-real-ip: header single-value
    real_ip = headers.get("x-real-ip")
    if real_ip:
        log.debug(f"IP extraido de x-real-ip: {real_ip}")
        return real_ip

    # Fallback: conexao TCP direta
    if request.client is not None:
        ip = request.client.host
        log.debug(f"IP extraido de client.host: {ip}")
        return ip

    fallback_ip = "0.0.0.0"  # noqa: S104
    log.warning(f"Nenhuma fonte de IP disponivel — usando {fallback_ip}")
    return fallback_ip


# ===================================================================
# RATE LIMITER — SLIDING WINDOW
# ===================================================================


class RateLimiter:
    """Rate limiter com sliding window em memoria e asyncio.Lock.

    Cada chave (IP ou ticket) tem uma lista de timestamps.
    A janela desliza removendo entradas antigas antes de contar.

    O asyncio.Lock previne race conditions em alta concorrencia,
    garantindo que leituras e escritas no contador sejam atomicas.

    Atributos:
        max_requests: Numero maximo de requisicoes na janela.
        window_seconds: Tamanho da janela em segundos.

    Uso:
        limiter = RateLimiter(max_requests=20, window_seconds=60)
        if not await limiter.check("192.168.1.1"):
            raise HTTPException(429, "Too Many Requests")
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def check(self, key: str) -> bool:
        """Verifica se a chave esta dentro do limite de requisicoes.

        Remove entradas fora da janela, conta as restantes e adiciona
        uma nova entrada se dentro do limite.

        Args:
            key: Identificador (IP ou ticket hash).

        Returns:
            True se permitido, False se bloqueado.
        """
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock

        async with lock:
            now = time.time()
            cutoff = now - self.window_seconds

            # Obter ou criar lista de timestamps
            if key not in self._requests:
                self._requests[key] = []

            # Remover entradas fora da janela (sliding window)
            self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]

            # Verificar limite
            if len(self._requests[key]) >= self.max_requests:
                log.warning(
                    "Rate limit atingido (429)",
                    key_prefix=f"{key[:20]}...",
                    current=len(self._requests[key]),
                    max=self.max_requests,
                )
                return False

            # Registrar requisicao
            self._requests[key].append(now)
            return True


# ===================================================================
# INSTANCIAS PRE-CONFIGURADAS
# ===================================================================

# Anti-bot: 20 req/min por IP no tunnel de PDF
ip_limiter = RateLimiter(max_requests=20, window_seconds=60)

# Anti-viral: 100 req/h por ticket
ticket_limiter = RateLimiter(max_requests=100, window_seconds=3600)

# Anti-enumeracao: 5 req/min por IP no endpoint de auth
auth_limiter = RateLimiter(max_requests=5, window_seconds=60)
