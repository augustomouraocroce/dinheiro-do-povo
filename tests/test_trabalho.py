from datetime import date

from dp import calendario, trabalho
from dp.site import dados


def test_dias_uteis_sem_feriados_nacionais():
    # 2026: 261 dias de segunda a sexta; 8 feriados nacionais caem em dia útil (15/11 é domingo).
    assert calendario.dias_uteis(2026) == 253
    assert calendario.dias_uteis(2025) == 256
    assert calendario.dias_uteis(2026, date(2026, 1, 9)) == 6  # 1º/1 é feriado


def test_dias_trabalhados_descontam_ferias():
    d = calendario.dias_trabalhados(2026)
    assert (d["dias_uteis"], d["ferias_uteis"], d["trabalhados"]) == (253, 21, 232)
    parcial = calendario.dias_trabalhados(2026, date(2026, 6, 30))
    assert parcial["ferias_uteis"] == round(30 * 5 / 7 * 181 / 365)


REGRAS = {
    "temas_camara": {"58": "Trabalho e Emprego"},
    "palavras": ["cesta básica", "imposto sobre a renda", "trabalhador"],
    "incluidas": [{"titulo": "PEC 45/2019", "motivo": "Criou a cesta básica com imposto zero."}],
}


def test_motivo_segue_a_ordem_incluida_tema_palavra():
    assert trabalho.motivo("qualquer coisa", [58], "PEC 45/2019", REGRAS) == "Criou a cesta básica com imposto zero."
    assert trabalho.motivo("qualquer coisa", [58], "PL 1/2024", REGRAS) == "Tema oficial da Câmara: Trabalho e Emprego."
    assert trabalho.motivo("Altera a legislação do Imposto sobre a Renda", [], "PL 1087/2025", REGRAS) == \
        "O texto cita “imposto sobre a renda”."
    assert trabalho.motivo("Cria a Semana da Leitura", [40], "PL 2/2024", REGRAS) is None


def test_motivo_casa_palavra_inteira_no_inicio():
    # "trabalhadores" contém "trabalhador"; "extrabalhador" não deve casar pelo começo da palavra.
    assert trabalho.motivo("direitos dos trabalhadores rurais", [], "", REGRAS) == "O texto cita “trabalhador”."
    assert trabalho.motivo("extrabalhador", [], "", REGRAS) is None


def test_ausencia_no_senado_nao_conta_como_voto():
    assert dados._categoria_voto("senado", "Sim") == "sim"
    assert dados._categoria_voto("senado", "Abstenção") == "outros"
    assert dados._categoria_voto("senado", "NCom") is None
    assert dados._categoria_voto("senado", "AP") is None
    assert dados._categoria_voto("camara", "Obstrução") == "outros"
