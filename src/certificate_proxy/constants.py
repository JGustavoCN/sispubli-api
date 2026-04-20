"""
Constantes e Recursos do Tunel de PDF — Sispubli API.
"""

import asyncio

# Limite maximo de tamanho do PDF para evitar estouro de memoria (10 MB)
MAX_PDF_SIZE = 10_000_000

# User-Agent para identificacao do proxy nos logs do Sispubli
TUNNEL_USER_AGENT = "Mozilla/5.0 (compatible; SispubliProxy/1.0)"

# Semaforo global para controlar a concorrencia no tunel.
# Limita a 10 downloads simultaneos para preservar recursos do servidor.
_tunnel_semaphore = asyncio.Semaphore(10)
