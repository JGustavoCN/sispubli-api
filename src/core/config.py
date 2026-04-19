import os

from dotenv import load_dotenv

# Garantir que o .env seja carregado o mais cedo possível
load_dotenv()


class Config:
    """Configurações centralizadas da API."""

    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development").lower()

    # Segredos criptográficos
    FERNET_SECRET_KEY: str = os.environ.get("FERNET_SECRET_KEY", "")
    SECRET_PEPPER: str = os.environ.get("SECRET_PEPPER", "pepper_padrao_dev")
    HASH_SALT: str = os.environ.get("HASH_SALT", "")

    # Constantes
    TOKEN_TTL_SECONDS: int = 15 * 60
    MAX_TOKEN_LENGTH: int = 2048

    @classmethod
    def validate_production(cls):
        """Valida se todas as variáveis obrigatórias estão presentes em produção."""
        if cls.ENVIRONMENT == "production":
            required = ["HASH_SALT", "FERNET_SECRET_KEY", "SECRET_PEPPER"]
            missing = [var for var in required if not getattr(cls, var)]
            if missing:
                msg = ", ".join(missing)
                raise RuntimeError(
                    f"FALHA CRITICA: ENVIRONMENT=production mas variáveis ausentes: {msg}"
                )


config = Config()
