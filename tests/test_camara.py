from datetime import date
from pathlib import Path

import pytest

from dp import coleta, config, db
from dp.fontes import camara

FIX = Path(__file__).parent / "fixtures"


def test_semana_referencia():
    assert config.semana_referencia(date(2026, 10, 24)) == (date(2026, 10, 17), date(2026, 10, 23))
    with pytest.raises(ValueError):
        config.semana_referencia(date(2026, 10, 26))
    assert config.ultimo_sabado(date(2026, 10, 26)) == date(2026, 10, 24)
    assert config.ultimo_sabado(date(2026, 10, 24)) == date(2026, 10, 24)


def test_ler_ceap():
    linhas = list(camara.ler_ceap(FIX / "camara_ceap_amostra.csv"))
    assert len(linhas) == 42
    assert len({l["chave"] for l in linhas}) == 42
    dep = [l for l in linhas if l["parlamentar_id"] == "camara:221328"]
    assert dep and all(l["partido_na_nota"] == "PL" for l in dep)
    assert any(l["parlamentar_id"] is None for l in linhas)  # lideranças
    assert any(l["valor_liquido"] < 0 for l in linhas)       # compensações/estornos
    # CPF de fornecedor pessoa física não é armazenado
    assert all(l["cnpj"] is None or len("".join(c for c in l["cnpj"] if c.isdigit())) == 14
               for l in linhas)


def test_despesas_idempotente_e_novas(tmp_path):
    conn = db.conectar(tmp_path / "t.db")
    linhas = list(camara.ler_ceap(FIX / "camara_ceap_amostra.csv"))

    r1 = coleta.salvar_despesas(conn, linhas[:30], "camara", "2026-10-17")
    assert r1 == {"linhas": 30, "novas": 30, "carga_inicial": True}

    r2 = coleta.salvar_despesas(conn, linhas, "camara", "2026-10-24")
    assert r2 == {"linhas": 42, "novas": 12, "carga_inicial": False}

    r3 = coleta.salvar_despesas(conn, linhas, "camara", "2026-10-31")
    assert r3["novas"] == 0

    q = conn.execute(
        "SELECT primeira_vez_vista, carga_inicial, COUNT(*) FROM despesa GROUP BY 1, 2 ORDER BY 1"
    ).fetchall()
    assert [tuple(x) for x in q] == [("2026-10-17", 1, 30), ("2026-10-24", 0, 12)]


def test_ler_pagina_presenca():
    html = (FIX / "camara_presenca_221328_2026.html").read_text(encoding="utf-8")
    dias, resumo = camara.ler_pagina_presenca(html)
    assert dias[0] == {"data": "2026-02-02", "status": "Presença", "categoria": "presente"}
    assert {d["status"] for d in dias} <= {"Presença", "Ausência"}
    assert sum(d["status"] == "Ausência" for d in dias) == 2
    indicadores = {r["indicador"]: r["valor"] for r in resumo}
    assert indicadores["Total de dias com ausências não justificadas em sessões deliberativas"] == 2
    assert indicadores["Total de dias com presença nas sessões deliberativas"] == 70


@pytest.mark.parametrize("status,categoria", [
    ("Presença", "presente"),
    ("Ausência", "ausencia_nao_justificada"),
    ("Missão Autorizada", "ausencia_justificada"),
    ("Licença para Tratamento de Saúde", "ausencia_justificada"),
    ("Decisão da Mesa", "ausencia_justificada"),
])
def test_classificar_frequencia(status, categoria):
    assert camara.classificar_frequencia(status) == categoria


def test_pagina_presenca_layout_mudou():
    with pytest.raises(ValueError):
        camara.ler_pagina_presenca("<html><body>nada</body></html>")
