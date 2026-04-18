import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

# Vamos importar o script. Como ele esta em scripts/, precisamos garantir que o path esteja correto
# Ou podemos rodar via subprocesso nos testes de integracao do auditor
from scripts.audit_pii import perform_audit

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("CPF_TESTE", "11122233344")
    monkeypatch.setenv("FERNET_SECRET_KEY", "chave_secreta_fernet")
    monkeypatch.setenv("HASH_SALT", "sal_do_hash")

@pytest.fixture
def temp_repo(tmp_path):
    # Simula um arquivo limpo
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("print('hello world')")
    
    # Simula arquivo com CPF real (vazamento)
    leak_cpf = tmp_path / "leak_cpf.py"
    leak_cpf.write_text("user_cpf = '11122233344'")
    
    # Simula arquivo com segredo do .env (vazamento)
    leak_key = tmp_path / "leak_key.py"
    leak_key.write_text("key = 'chave_secreta_fernet'")
    
    # Simula arquivo com CPF de mock (permitido)
    mock_file = tmp_path / "mock.py"
    mock_file.write_text("mock_cpf = '74839210055'")
    
    return tmp_path

def test_audit_pii_detects_leaks(temp_repo, mock_env):
    """Testa se o auditor detecta CPFs e segredos do .env e sinaliza erro."""
    files = [str(f) for f in temp_repo.glob("*.py")]
    
    with patch("subprocess.check_output") as mock_git, \
         patch("sys.exit") as mock_exit:
        mock_git.return_value = "\n".join(files).encode("utf-8")
        
        # Chamamos com exit_on_fail=True para testar o sys.exit(1)
        perform_audit(exit_on_fail=True)
        
        # Deve ter chamado sys.exit(1) porque criamos arquivos com vazamentos no temp_repo
        mock_exit.assert_called_once_with(1)

def test_audit_pii_allows_whitelist(temp_repo, mock_env):
    """Testa se o auditor ignora o CPF da whitelist e retorna sucesso."""
    # Criamos apenas o arquivo de mock
    mock_file = temp_repo / "only_mock.py"
    mock_file.write_text("cpf = '74839210055'")
    
    with patch("subprocess.check_output") as mock_git, \
         patch("sys.exit") as mock_exit:
        mock_git.return_value = str(mock_file).encode("utf-8")
        
        perform_audit(exit_on_fail=True)
        
        # Nao deve chamar sys.exit(1), mas sim sys.exit(0) ou nada dependendo da implementacao
        # No nosso script atual, ele chama sys.exit(0)
        mock_exit.assert_called_once_with(0)
