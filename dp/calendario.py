"""Dias úteis de um trabalhador com carteira assinada, para comparar com os dias de sessão.

Feriados nacionais por lei federal (datas fixas):
- Lei 662/1949: 1º/1, 21/4, 1º/5, 7/9, 2/11, 15/11, 25/12
- Lei 6.802/1980: 12/10
- Lei 14.759/2023: 20/11
Carnaval, Sexta-feira Santa e Corpus Christi não são feriados nacionais por lei federal
(dependem de lei local ou são ponto facultativo) e por isso não entram na conta.
Férias: 30 dias corridos por ano (CLT, art. 130), o que dá em média 30 × 5/7 dias úteis.
"""
from datetime import date, timedelta

FERIADOS_NACIONAIS = ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25))
FONTES = [
    ("Lei 662/1949 (feriados nacionais)", "https://www.planalto.gov.br/ccivil_03/leis/l0662.htm"),
    ("Lei 6.802/1980 (12 de outubro)", "https://www.planalto.gov.br/ccivil_03/leis/l6802.htm"),
    ("Lei 14.759/2023 (20 de novembro)", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14759.htm"),
    ("CLT, art. 130 (30 dias de férias)", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm"),
]
DIAS_FERIAS = 30


def dias_uteis(ano: int, ate: date = None) -> int:
    """Dias de segunda a sexta no ano (até `ate`, inclusive), sem os feriados nacionais."""
    inicio, fim = date(ano, 1, 1), ate or date(ano, 12, 31)
    feriados = {date(ano, m, d) for m, d in FERIADOS_NACIONAIS}
    n, dia = 0, inicio
    while dia <= fim:
        if dia.weekday() < 5 and dia not in feriados:
            n += 1
        dia += timedelta(days=1)
    return n


def dias_trabalhados(ano: int, ate: date = None) -> dict:
    """Dias úteis menos as férias (proporcionais ao período, quando `ate` é informado)."""
    uteis = dias_uteis(ano, ate)
    fim = ate or date(ano, 12, 31)
    fracao_ano = ((fim - date(ano, 1, 1)).days + 1) / ((date(ano, 12, 31) - date(ano, 1, 1)).days + 1)
    ferias = round(DIAS_FERIAS * 5 / 7 * fracao_ano)
    return {"ano": ano, "ate": fim, "dias_uteis": uteis, "ferias_uteis": ferias, "trabalhados": uteis - ferias}
