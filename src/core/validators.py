import re


def validar_cpf(cpf: str) -> bool:
    """
    Valida um CPF usando o algoritmo de MÃ³dulo 11 e verifica sequÃªncias repetidas.

    Args:
        cpf: String do CPF (com ou sem pontuaÃ§Ã£o).

    Returns:
        bool: True se for vÃ¡lido, False caso contrÃ¡rio.
    """
    if not cpf:
        return False

    # 1. Limpar apenas nÃºmeros
    numbers = [int(digit) for digit in re.sub(r"\D", "", str(cpf))]

    # 2. Verificar se tem 11 dÃ­gitos
    if len(numbers) != 11:
        return False

    # 3. Eliminar CPFs com todos os nÃºmeros iguais (conhecidamente invÃ¡lidos)
    if len(set(numbers)) == 1:
        return False

    # 4. CÃ¡lculo do primeiro dÃ­gito verificador
    sum_1 = sum(numbers[i] * (10 - i) for i in range(9))
    digit_1 = (sum_1 * 10 % 11) % 10
    if digit_1 != numbers[9]:
        return False

    # 5. CÃ¡lculo do segundo dÃ­gito verificador
    sum_2 = sum(numbers[i] * (11 - i) for i in range(10))
    digit_2 = (sum_2 * 10 % 11) % 10
    return digit_2 == numbers[10]
