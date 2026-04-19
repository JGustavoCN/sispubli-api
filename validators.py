import re


def validar_cpf(cpf: str) -> bool:
    """
    Valida um CPF usando o algoritmo de Módulo 11 e verifica sequências repetidas.

    Args:
        cpf: String do CPF (com ou sem pontuação).

    Returns:
        bool: True se for válido, False caso contrário.
    """
    if not cpf:
        return False

    # 1. Limpar apenas números
    numbers = [int(digit) for digit in re.sub(r"\D", "", str(cpf))]

    # 2. Verificar se tem 11 dígitos
    if len(numbers) != 11:
        return False

    # 3. Eliminar CPFs com todos os números iguais (conhecidamente inválidos)
    if len(set(numbers)) == 1:
        return False

    # 4. Cálculo do primeiro dígito verificador
    sum_1 = sum(numbers[i] * (10 - i) for i in range(9))
    digit_1 = (sum_1 * 10 % 11) % 10
    if digit_1 != numbers[9]:
        return False

    # 5. Cálculo do segundo dígito verificador
    sum_2 = sum(numbers[i] * (11 - i) for i in range(10))
    digit_2 = (sum_2 * 10 % 11) % 10
    return digit_2 == numbers[10]
