import re
import sys
import os
import subprocess
from dotenv import dotenv_values

def perform_audit(exit_on_fail=True):
    """
    Realiza a auditoria de PII e segredos.
    
    Args:
        exit_on_fail: Se True, chama sys.exit(1) ao encontrar problemas.
        
    Returns:
        int: Numero de problemas encontrados.
    """
    # 1. Carregar valores sensíveis do .env
    env_vars = dotenv_values(".env")
    
    # Lista de chaves cujos VALORES literais não podem aparecer no código-fonte
    sensitive_keys = ["CPF_TESTE", "CPF_TEST", "FERNET_SECRET_KEY", "HASH_SALT", "SECRET_PEPPER"]
    
    # Filtramos os valores reais presentes no .env local
    sensitive_values = []
    for key in sensitive_keys:
        val = env_vars.get(key)
        if val and len(str(val)) > 4:
            sensitive_values.append(str(val))
    
    # 2. Configurar Regex de CPF
    # (?<!\d)\d{11}(?!\d) -> Garante exatamente 11 digitos, sem numeros grudados
    cpf_pattern = re.compile(r'(?<!\d)\d{11}(?!\d)')
    # Whitelist de CPFs usados em mocks e testes unitários
    whitelist_cpfs = ["74839210055", "11111111111", "09876543211"]
    
    found_issues = 0
    
    print("=== Iniciando Auditoria PII Dinâmica (Sispubli API) ===")
    
    # 3. Obter arquivos via Git
    try:
        files_output = subprocess.check_output(["git", "ls-files"], stderr=subprocess.STDOUT)
        files = files_output.decode("utf-8").splitlines()
    except Exception as e:
        print(f"⚠️ Erro ao listar arquivos do Git: {e}")
        # Fallback para caminhada manual se nao for um repo git (ex: no CI simplificado)
        files = []
        for root, _, filenames in os.walk("."):
            if any(p in root for p in [".venv", ".git", "__pycache__", "node_modules"]):
                continue
            for f in filenames:
                files.append(os.path.join(root, f))

    # 4. Auditoria
    for fpath in files:
        # Ignorar binarios ou arquivos irrelevantes
        if any(fpath.endswith(ext) for ext in [".png", ".jpg", ".pdf", ".pyc", ".lock", ".env"]):
            continue
            
        if "test_audit_pii.py" in fpath:
            continue
            
        if not os.path.exists(fpath):
            continue

        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f, 1):
                    # A. Verificar valores literais do .env
                    for val in sensitive_values:
                        if val in line:
                            # Nao logamos o segredo real no console para nao vazar no CI
                            print(f"[ALERTA SUSTO] Segredo do .env detectado em {fpath}:{i}")
                            found_issues += 1
                    
                    # B. Verificar Regex de CPF
                    cpfs = cpf_pattern.findall(line)
                    for cpf in cpfs:
                        if cpf not in whitelist_cpfs:
                            print(f"[ALERTA LGPD] CPF detectado em {fpath}:{i} -> {cpf[:3]}********")
                            found_issues += 1
                            
        except Exception as e:
            # Ignorar erros de leitura de arquivos binários mal categorizados
            pass

    if found_issues == 0:
        print("[OK] Nenhuma PII ou Segredo detectado nos arquivos fonte.")
        if exit_on_fail:
            sys.exit(0)
    else:
        print(f"[FALHA] Auditoria: {found_issues} problemas encontrados.")
        if exit_on_fail:
            sys.exit(1)
            
    return found_issues

if __name__ == "__main__":
    perform_audit()
