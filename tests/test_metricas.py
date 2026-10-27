"""Métricas e relatório sobre um banco pequeno, montado à mão."""
from datetime import date

import pytest

from dp import db, metricas, relatorio

SABADO = date(2026, 10, 17)  # semana de 10/10 a 16/10


def _parl(conn, pid, nome, uf, partido, visto_em="2026-10-26"):
    casa = pid.split(":")[0]
    conn.execute(
        "INSERT INTO parlamentar VALUES (?, ?, ?, ?, ?, NULL, ?, '2026-10-26')",
        (pid, casa, pid.split(":")[1], nome, uf, f"https://exemplo/{pid}"))
    conn.execute("INSERT INTO filiacao VALUES (?, ?, ?)", (pid, partido, visto_em))


def _despesa(conn, chave, pid, valor, vista, carga, casa="camara", ano=2026):
    conn.execute(
        """INSERT INTO despesa (chave, casa, parlamentar_id, nome_na_nota, ano, mes, categoria,
               fornecedor, valor_liquido, data_emissao, url_documento,
               primeira_vez_vista, ultima_vez_vista, carga_inicial)
           VALUES (?, ?, ?, 'X', ?, 10, 'TELEFONIA', 'Operadora', ?, '2026-10-01', 'https://nota',
                   ?, ?, ?)""",
        (chave, casa, pid, ano, valor, vista, vista, carga))


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(tmp_path / "t.db")
    _parl(c, "camara:1", "Ana", "SP", "PL")
    _parl(c, "camara:2", "Bruno", "RJ", "PL")
    _parl(c, "camara:3", "Carla", "MG", "PT")      # não monitorado: só entra em "Todos"
    _parl(c, "senado:10", "Davi", "BA", "PL")
    _parl(c, "senado:11", "Eva", "AM", "MDB")
    _parl(c, "senado:12", "Fábio", "PR", "PSD")

    url = "https://www.camara.leg.br/deputados/{}/presenca-plenario/2026"
    presenca = [
        ("camara:1", "2026-10-13", "Presença", "presente"),
        ("camara:1", "2026-10-14", "Ausência", "ausencia_nao_justificada"),
        ("camara:2", "2026-10-13", "Missão Autorizada", "ausencia_justificada"),
        ("camara:2", "2026-10-14", "Presença", "presente"),
        ("camara:3", "2026-10-13", "Presença", "presente"),
        ("camara:3", "2026-10-14", "Presença", "presente"),
        ("camara:1", "2026-03-10", "Ausência", "ausencia_nao_justificada"),  # fora da semana
    ]
    c.executemany(
        "INSERT INTO presenca_dia VALUES (?, ?, ?, ?, ?, '2026-10-26')",
        [(p, d, s, cat, url.format(p.split(":")[1])) for p, d, s, cat in presenca])

    c.execute("INSERT INTO votacao VALUES ('camara:v1', 'camara', '2026-10-14', 'PL 1/2026', 1, NULL, 'https://v1')")
    c.executemany("INSERT INTO voto VALUES ('camara:v1', ?, ?)",
                  [("camara:1", "Sim"), ("camara:3", "Não")])  # camara:2 sem registro

    c.execute("INSERT INTO votacao VALUES ('senado:s1', 'senado', '2026-10-15', 'PLP 2/2026', 1, NULL, 'https://s1')")
    c.executemany("INSERT INTO voto VALUES ('senado:s1', ?, ?)",
                  [("senado:10", "NCom"), ("senado:11", "Sim"), ("senado:12", "AP")])

    for pid, salario, gasto, sobra in [("camara:1", 46366.19, 300000, 100000),
                                       ("camara:2", 46366.19, 100000, 300000),
                                       ("camara:3", 46366.19, 200000, 200000)]:
        c.executemany(
            "INSERT INTO recurso_oficial VALUES (?, 2026, ?, ?, ?, 'https://perfil', '26/10/2026 06:00', '2026-10-26')",
            [(pid, "salario_bruto_mensal", salario, "R$"), (pid, "cota_gasto", gasto, ""),
             (pid, "cota_nao_utilizado", sobra, ""),
             (pid, "imovel_funcional", None, "Faz uso desde 01/02/2023" if pid == "camara:1" else "Não faz uso"),
             (pid, "auxilio_moradia", 38277.0 if pid == "camara:2" else None,
              "Recebeu R$ 38.277" if pid == "camara:2" else "Não recebe o auxílio")])

    _despesa(c, "a", "senado:10", 1000.0, "2026-10-01", 1, casa="senado")
    _despesa(c, "b", "senado:11", 250.5, "2026-10-01", 1, casa="senado")
    c.commit()
    return c


def _pessoas(conn, casa):
    return metricas.pessoas_da_casa(conn, casa, metricas.partidos_na_data(conn, SABADO.isoformat()))


def test_partidos_na_data_usa_filiacao_mais_antiga_se_coleta_e_posterior(conn):
    conn.execute("INSERT INTO filiacao VALUES ('camara:1', 'NOVO', '2026-11-07')")
    assert metricas.partidos_na_data(conn, "2026-10-17")["camara:1"] == "PL"
    assert metricas.partidos_na_data(conn, "2026-11-07")["camara:1"] == "NOVO"


def test_por_partido_nao_conta_quem_nao_tem_dado(conn):
    pessoas = _pessoas(conn, "camara")
    linhas = metricas.por_partido(pessoas, ["PL"], {"camara:1": {"x": 2}, "camara:3": {"x": 5}}, ["x"])
    assert linhas == [{"partido": "PL", "parlamentares": 1, "x": 2},
                      {"partido": "Todos", "parlamentares": 2, "x": 7}]


def test_presenca_camara_semana(conn):
    pessoas = _pessoas(conn, "camara")
    r = metricas.presenca_camara(conn, pessoas, ["PL"], "2026-10-10", "2026-10-16")
    assert r["dias_com_sessao"] == ["2026-10-13", "2026-10-14"]
    pl, todos = r["por_partido"]
    assert (pl["presente"], pl["ausencia_justificada"], pl["ausencia_nao_justificada"]) == (2, 1, 1)
    assert pl["pct_presenca"] == 0.5
    assert todos["pct_presenca"] == 4 / 6
    assert [(p["nome"], p["dias"]) for p in r["ausencias_nao_justificadas"]] == [("Ana", ["2026-10-14"])]
    assert r["motivos_justificados"] == [("Missão Autorizada", 1)]


def test_votacoes_camara_bancadas(conn):
    pessoas = _pessoas(conn, "camara")
    [v] = metricas.votacoes_camara(conn, pessoas, ["PL"], "2026-10-10", "2026-10-16")
    assert v["placar"] == {"Sim": 1, "Não": 1}
    assert v["bancadas"] == [{"partido": "PL", "membros": 2, "sim": 1, "nao": 0,
                              "outros": 0, "sem_registro": 1}]


def test_custos_camara(conn):
    pessoas = _pessoas(conn, "camara")
    r = metricas.custos_camara(conn, pessoas, ["PL"], 2026)
    pl, todos = r["por_partido"]
    assert pl["cota_media"] == 200000
    assert pl["pct_cota"] == 0.5
    assert pl["imovel_funcional"] == 1
    assert (pl["auxilio_moradia"], pl["auxilio_moradia_valor"]) == (1, 38277.0)
    assert todos["parlamentares"] == 3
    # Ranking por percentual do limite, só monitorados
    assert [(p["nome"], p["pct_cota"]) for p in r["maiores_pct_cota"]] == [("Ana", 0.75), ("Bruno", 0.25)]
    assert r["atualizado_fonte"] == "26/10/2026 06:00"


def test_despesas_novas_indisponivel_antes_da_primeira_coleta(conn):
    pessoas = _pessoas(conn, "senado")
    r = metricas.despesas_novas(conn, "senado", pessoas, ["PL"], date(2026, 9, 19), date(2026, 9, 26))
    assert r == {"disponivel": False, "primeira_coleta": "2026-10-01"}


def test_despesas_novas_ignora_carga_inicial(conn):
    _despesa(conn, "c", "senado:10", 300.0, "2026-10-08", 0, casa="senado")
    _despesa(conn, "d", "senado:12", 50.0, "2026-10-08", 0, casa="senado")
    pessoas = _pessoas(conn, "senado")
    r = metricas.despesas_novas(conn, "senado", pessoas, ["PL", "MDB"], date(2026, 10, 3), date(2026, 10, 10))
    assert r["disponivel"] and r["desde"] == "2026-10-03"
    pl, mdb, todos = r["por_partido"]
    assert (pl["notas"], pl["valor"]) == (1, 300.0)
    assert mdb["parlamentares"] == 0
    assert (todos["notas"], todos["valor"]) == (2, 350.0)
    assert [d["valor"] for d in r["maiores"]] == [300.0]  # só monitorados


def test_votacoes_senado(conn):
    pessoas = _pessoas(conn, "senado")
    r = metricas.votacoes_senado(conn, pessoas, ["PL", "MDB"], "2026-10-10", "2026-10-16")
    pl, mdb, todos = r["por_partido"]
    assert pl["ausencia_nao_justificada"] == 1 and pl["pct_votou"] == 0
    assert mdb["pct_votou"] == 1
    assert todos["ausencia_justificada"] == 1
    assert [p["nome"] for p in r["nao_compareceu"]] == ["Davi"]
    assert r["votacoes"][0]["bancadas"][0]["ausencia_nao_justificada"] == 1


def test_ceaps_ano_conta_senador_sem_nota_como_zero(conn):
    pessoas = _pessoas(conn, "senado")
    r = metricas.ceaps_ano(conn, pessoas, ["PL", "MDB"], 2026)
    pl, mdb, todos = r["por_partido"]
    assert (pl["valor"], mdb["valor"]) == (1000.0, 250.5)
    assert (todos["parlamentares"], todos["valor"], todos["media"]) == (3, 1250.5, 1250.5 / 3)


@pytest.mark.parametrize("valor,esperado", [
    (1234567.891, "R$ 1.234.567,89"), (0, "R$ 0,00"), (-10.5, "R$ -10,50"), (None, "—")])
def test_brl(valor, esperado):
    assert relatorio.brl(valor) == esperado


def test_pct():
    assert relatorio.pct(0.9722) == "97,2%"
    assert relatorio.pct(None) == "—"


def test_gerar_relatorio(conn, tmp_path):
    md, html = relatorio.gerar(conn, SABADO, tmp_path / "saida")
    texto = md.read_text(encoding="utf-8")
    assert "Semana de 10/10/2026 a 16/10/2026" in texto
    assert "Ana (PL-SP): 14/10/2026" in texto           # ausência não justificada listada
    assert "Davi (PL-BA)" in texto                       # não compareceu no Senado
    assert "R$ 46.366,19" in texto
    pagina = html.read_text(encoding="utf-8")
    assert "DINHEIRO DO POVO" in pagina
    # Toda tabela do Markdown precisa virar <table> (uma linha em branco faltando quebra isso):
    # presença semana e ano, 1 votação Câmara, custos, 1 votação Senado,
    # participação no ano, CEAPS e despesas novas do Senado.
    assert texto.count("| Partido |") == pagina.count("<table>") == 8
