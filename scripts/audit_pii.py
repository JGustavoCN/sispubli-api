#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys

# Adiciona a raiz do projeto ao sys.path para importar logger e validators
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import dotenv_values

from src.core.logger import logger

logger = logger.bind(module=__name__)

try:
    from src.core.validators import validar_cpf
except ImportError:
    # Fallback caso ocorra erro no path
    def validar_cpf(cpf):
        return len(re.sub(r"\D", "", str(cpf))) == 11


def perform_audit(exit_on_fail=True):
    """
    Realiza a auditoria de PII e segredos seguindo a política Zero Trust.
    """
    env_vars = dotenv_values(".env")

    sensitive_keys = ["CPF_TESTE", "FERNET_SECRET_KEY", "HASH_SALT", "SECRET_PEPPER"]
    sensitive_values = []

    logger.info("=== Iniciando Auditoria PII Dinâmica (Sispubli API) ===")

    # 1. Carregar valores e suas variações
    for key in sensitive_keys:
        val = os.getenv(key) or env_vars.get(key)
        if not val or len(str(val)) < 4:
            continue

        val_str = str(val)
        sensitive_values.append(val_str)

        # Se for CPF, adicionar variação formatada e validar
        if key == "CPF_TESTE":
            if not validar_cpf(val_str):
                logger.warning(f"AVISO: {key} no .env não é um CPF válido.")

            clean_cpf = re.sub(r"\D", "", val_str)
            if clean_cpf != val_str:
                sensitive_values.append(clean_cpf)

            # Formato XXX.XXX.XXX-XX
            if len(clean_cpf) == 11:
                formatted = f"{clean_cpf[:3]}.{clean_cpf[3:6]}.{clean_cpf[6:9]}-{clean_cpf[9:]}"
                sensitive_values.append(formatted)

    # Remover duplicatas
    sensitive_values = list(set(sensitive_values))

    # 2. Configurar Regex de CPF Genérico
    cpf_pattern = re.compile(r"(?<!\d)\d{11}(?!\d)")
    whitelist_cpfs = ["74839210055", "11111111111", "09876543211", "748.392.100-55"]

    found_issues = 0

    # 3. Obter arquivos (Git + Cassettes Pendentes)
    files = set()
    git_bin = shutil.which("git")
    try:
        if git_bin:
            # Arquivos rastreados pelo Git
            files_output = subprocess.check_output([git_bin, "ls-files"], stderr=subprocess.STDOUT)  # noqa: S603
            files.update(files_output.decode("utf-8").splitlines())

            # Arquivos em STAGE (ainda não commitados)
            files_output_stage = subprocess.check_output(  # noqa: S603
                [git_bin, "diff", "--name-only", "--cached"],
                stderr=subprocess.STDOUT,
            )
            files.update(files_output_stage.decode("utf-8").splitlines())
    except Exception as e:
        logger.debug(f"Git não detectado, usando busca manual: {e}")
        # Fallback para caminhada manual
        for root, _, filenames in os.walk("."):
            if any(p in root for p in [".venv", ".git", "__pycache__", "node_modules"]):
                continue
            for f in filenames:
                # Armazena path relativo limpo
                fpath = os.path.relpath(os.path.join(root, f), ".")
                files.add(fpath)

    # Forçar inclusão de cassettes (caso não estejam no git ainda)
    if os.path.exists("tests/cassettes"):
        for root, _, filenames in os.walk("tests/cassettes"):
            for f in filenames:
                if f.endswith((".yaml", ".json")):
                    # Garante que o path seja relativo à raiz
                    rel_root = os.path.relpath(root, ".")
                    files.add(os.path.join(rel_root, f))

    # 4. Auditoria
    for fpath in sorted(files):
        # Normalizar paths
        fpath = fpath.replace("/", os.sep)

        # Ignorar binários ou arquivos irrelevantes
        if any(fpath.endswith(ext) for ext in [".png", ".jpg", ".pdf", ".pyc", ".lock", ".env"]):
            continue

        # Ignorar os próprios testes de auditoria para evitar falsos positivos
        if "test_audit_pii.py" in fpath or "test_validators.py" in fpath:
            continue

        if not os.path.exists(fpath):
            continue

        try:
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.splitlines()

                for i, line in enumerate(lines, 1):
                    # A. Verificar valores literais do .env (incluindo variações)
                    for val in sensitive_values:
                        if val in line:
                            # Não logamos o segredo real no console para não vazar no CI
                            logger.error(f"[ALERTA LGPD] Valor sensível detectado em {fpath}:{i}")
                            found_issues += 1

                    # B. Verificar Regex de CPF genérico
                    cpfs = cpf_pattern.findall(line)
                    for cpf in cpfs:
                        if cpf not in whitelist_cpfs:
                            logger.warning(f"[ALERTA LGPD] CPF genérico detectado em {fpath}:{i}")
                            found_issues += 1

        except Exception:  # noqa: S110
            # Ignorar erros de leitura de arquivos binários mal categorizados
            pass

    if found_issues == 0:
        logger.info("[OK] Nenhuma PII ou Segredo detectado.")
        if exit_on_fail:
            sys.exit(0)
    else:
        logger.error(f"\n[FALHA] Auditoria: {found_issues} problemas encontrados.")
        if exit_on_fail:
            sys.exit(1)

    return found_issues


if __name__ == "__main__":
    perform_audit()
