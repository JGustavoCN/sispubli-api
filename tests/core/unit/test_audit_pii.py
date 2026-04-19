from scripts.audit_pii import perform_audit


def test_audit_detects_leak_in_cassette(tmp_path, monkeypatch):
    """
    PROVA DE FALHA: Verifica se o auditor detecta um CPF real formatado
    dentro de um arquivo simulando um cassette.
    """
    # 1. Configurar um CPF 'real' para o teste
    real_cpf = "12345678909"  # CPF matematicamente válido
    monkeypatch.setenv("CPF_TESTE", real_cpf)

    # 2. Criar um arquivo na pasta de cassettes simulada com o CPF formatado
    cassette_dir = tmp_path / "tests" / "cassettes"
    cassette_dir.mkdir(parents=True)
    cassette_file = cassette_dir / "leak.yaml"

    # O vazamento ocorre com o CPF formatado
    formatted_cpf = "123.456.789-09"
    cassette_file.write_text(f"referer: http://link.com?cpf={formatted_cpf}", encoding="utf-8")

    # 3. Mudar o diretório de trabalho para o tmp_path para o script achar o arquivo
    monkeypatch.chdir(tmp_path)

    # 4. Executar auditoria (não deve sair do processo, apenas retornar o número de problemas)
    issues = perform_audit(exit_on_fail=False)

    assert issues > 0, "O auditor deveria ter detectado o vazamento do CPF REAL formatado"


def test_audit_allows_mock_cpf(tmp_path, monkeypatch):
    """Verifica se o auditor ignora o CPF de mock oficial."""
    mock_cpf = "74839210055"

    test_file = tmp_path / "safe.py"
    test_file.write_text(f"cpf = '{mock_cpf}'", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    issues = perform_audit(exit_on_fail=False)
    assert issues == 0, "O auditor não deveria reclamar do CPF de mock oficial"


def test_audit_detects_generic_cpf(tmp_path, monkeypatch):
    """Verifica se o auditor detecta CPFs genéricos de 11 dígitos que não estão na whitelist."""
    # CPF genérico que não está no .env nem na whitelist
    random_cpf = "98765432109"

    test_file = tmp_path / "leak_generic.txt"
    test_file.write_text(f"vazamento: {random_cpf}", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    # Precisamos garantir que não haja CPF_TESTE no env para este teste disparar a regex genérica
    monkeypatch.delenv("CPF_TESTE", raising=False)

    issues = perform_audit(exit_on_fail=False)
    assert issues > 0, "O auditor deveria ter detectado o CPF genérico via regex"
