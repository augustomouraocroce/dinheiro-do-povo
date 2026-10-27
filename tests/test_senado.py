import json
from pathlib import Path

import pytest

from dp import coleta, db
from dp.fontes import senado

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def senadores():
    return json.loads((FIX / "senado_senadores_amostra.json").read_text(encoding="utf-8"))


def test_normalizar_nome():
    assert senado.normalizar_nome("  Eduardo  Girão ") == "EDUARDO GIRAO"


def test_resolver_senador(senadores):
    indice = senado.indice_de_nomes(senadores)
    assert senado.resolver_senador("ALAN RICK", indice) == "5672"
    assert senado.resolver_senador("WEVERTON ROCHA", indice) == "5411"  # prefixo único
    assert senado.resolver_senador("FULANO DE TAL", indice) is None


def test_indice_descarta_nomes_ambiguos():
    def s(cod, nome):
        return {"IdentificacaoParlamentar": {"CodigoParlamentar": cod, "NomeParlamentar": nome}}
    indice = senado.indice_de_nomes([s("1", "Maria"), s("2", "Maria"), s("3", "João")])
    assert "MARIA" not in indice
    assert indice["JOAO"] == "3"


def test_ler_ceaps(senadores):
    linhas = list(senado.ler_ceaps(FIX / "senado_ceaps_amostra.csv", senado.indice_de_nomes(senadores)))
    assert len(linhas) == 17  # 15 primeiras notas + 2 do 'WEVERTON ROCHA'
    primeira = linhas[0]
    assert primeira["parlamentar_id"] == "senado:5672"
    assert primeira["valor_liquido"] == 462.18
    assert primeira["data_emissao"] == "2026-01-20"
    assert primeira["chave"] == "senado:2279778"
    assert any(l["parlamentar_id"] == "senado:5411" for l in linhas)
    assert all(l["cnpj"] is None or len("".join(c for c in l["cnpj"] if c.isdigit())) == 14
               for l in linhas)


@pytest.mark.parametrize("sigla,categoria", [
    ("Sim", "votou"), ("Votou", "votou"), ("P-NRV", "presente_sem_voto"),
    ("AP", "ausencia_justificada"), ("LS", "ausencia_justificada"),
    ("NCom", "ausencia_nao_justificada"), ("XYZ", "desconhecido"),
])
def test_classificar_voto(sigla, categoria):
    assert senado.classificar_voto(sigla) == categoria


def test_salvar_votacao_senado(tmp_path):
    conn = db.conectar(tmp_path / "t.db")
    for v in json.loads((FIX / "senado_votacoes_2026-10-15.json").read_text(encoding="utf-8")):
        coleta.salvar_votacao_senado(conn, v)
        coleta.salvar_votacao_senado(conn, v)  # idempotente
    votos = dict(conn.execute("SELECT voto, COUNT(*) FROM voto GROUP BY 1").fetchall())
    assert sum(votos.values()) == 81
    assert votos["Sim"] == 78 and votos["NCom"] == 1
    v = conn.execute("SELECT * FROM votacao").fetchone()
    assert v["aprovada"] == 1 and v["descricao"].startswith("PLP 186/2026")
