from validators import validar_cpf


def test_cpf_valido_mock():
    """Testa o CPF de mock oficial do projeto."""
    assert validar_cpf("74839210055") is True


def test_cpf_valido_com_pontuacao():
    """Testa CPF válido com pontos e traço."""
    assert validar_cpf("748.392.100-55") is True


def test_cpf_invalido_repetido():
    """Testa CPFs com todos os números iguais (devem ser inválidos)."""
    assert validar_cpf("00000000000") is False
    assert validar_cpf("11111111111") is False


def test_cpf_invalido_curto():
    """Testa CPF com menos de 11 dígitos."""
    assert validar_cpf("1234567890") is False


def test_cpf_invalido_matematica():
    """Testa CPF com dígitos verificadores incorretos."""
    # 12345678901 é inválido (o correto seria 12345678909)
    assert validar_cpf("12345678901") is False


def test_cpf_vazio():
    """Testa entrada vazia."""
    assert validar_cpf("") is False
    assert validar_cpf(None) is False
