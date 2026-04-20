"""
Configuracoes e Mapeamentos do Dominio de Certificados.

Define as URLs do sistema legado Sispubli/IFS e os mapeamentos necessarios
para identificar tipos de certificados e construir URLs de download.
"""

from src.core.config import config

# URLs do Sispubli IFS
URL = "http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp"
BASE_URL = "http://intranet.ifs.edu.br/publicacoes/relat"

# Limite de seguranca para evitar loops infinitos na paginacao
MAX_PAGES = 50

# SALT para hashing LGPD-compliant
HASH_SALT = config.HASH_SALT

# ---------------------------------------------------------------------------
# Mapeamento de codigo de tipo para descricao legivel
# ---------------------------------------------------------------------------

TIPO_DESCRICAO_MAP: dict[str, str] = {
    "1": "Participacao",
    "2": "Autor",
    "3": "Mini-Curso",
    "4": "Avaliacao",
    "5": "Avaliacao de Programa",
    "6": "Certificado Interno",
    "7": "Orientacao",
    "8": "Aluno Voluntario",
    "9": "Aluno Bolsista",
    "10": "Ministrante de Sub-Evento",
    "11": "Coorientacao",
}

# Mapeamento de tipos de certificado para endpoints upstream
# ---------------------------------------------------------------------------

# Cada entrada define o endpoint e a função geradora de query parameters.
# Os parâmetros posicionais recebidos do scraper são:
# [cpf, tipo, programa, edicao, sub_evento, ano, id_artigo]
#  [0]   [1]   [2]       [3]     [4]         [5]  [6]

URL_TYPE_MAP = {
    "1": {
        "endpoint": "certificado_participacao_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "2": {
        "endpoint": "certificado_autor_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "3": {
        "endpoint": "certificado_participacao_sub_evento_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}"
            f"&tmp.id_edicao={p[3]}&tmp.id_sub_evento={p[4]}"
        ),
    },
    "4": {
        "endpoint": "certificado_avaliacao_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "5": {
        "endpoint": "certificado_avaliacao_programa_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "6": {
        "endpoint": "certificado_process.wsp",
        "params_fn": lambda p: f"tmp.id={p[6]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "7": {
        "endpoint": "certificado_orientador_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}&tmp.id_artigo={p[6]}"
        ),
    },
    "8": {
        "endpoint": "certificado_aluno_voluntario_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_artigo={p[6]}",
    },
    "9": {
        "endpoint": "certificado_aluno_bolsista_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_artigo={p[6]}",
    },
    "10": {
        "endpoint": "certificado_ministrante_sub_evento_process.wsp",
        "params_fn": lambda p: f"tmp.id_sub_evento={p[4]}",
    },
    "11": {
        "endpoint": "certificado_coorientador_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}&tmp.id_artigo={p[6]}"
        ),
    },
}
