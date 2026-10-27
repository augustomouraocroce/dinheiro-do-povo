import csv
import io
import zipfile

import pytest

from dp import coleta
from dp.fontes import fotos, tse
from dp.site import build, dados, graficos


def _itens(**valores):
    return {k: {"valor": v, "texto": "", "url_fonte": "u", "atualizado_fonte": None} for k, v in valores.items()}


def test_custo_mensal_usa_so_meses_fora_da_janela_de_90_dias():
    itens = _itens(salario_bruto_mensal=46366.19, auxilio_moradia=10000.0,
                   cota_mes_01=30000.0, cota_mes_02=50000.0, cota_mes_09=1000.0,
                   verba_gabinete_mes_01=100000.0, verba_gabinete_mes_02=120000.0)
    c = dados.custo_mensal_deputado(itens, mes_atual=5)  # maio: consolidado até fevereiro
    partes = {p["chave"]: p["valor"] for p in c["partes"]}
    assert c["mes_corte"] == 2
    assert partes["cota"] == 40000.0          # setembro (ainda aberto) fica fora
    assert partes["verba"] == 110000.0
    assert partes["auxilio"] == 2000.0        # 10.000 ÷ 5 meses
    assert c["total"] == pytest.approx(46366.19 + 40000 + 110000 + 2000)


def test_media_partes():
    a = {"partes": [{"chave": k, "nome": n, "valor": 10.0} for k, n in dados.PARTES_CUSTO], "total": 40.0}
    b = {"partes": [{"chave": k, "nome": n, "valor": 30.0} for k, n in dados.PARTES_CUSTO], "total": 120.0}
    m = dados.media_partes([a, b])
    assert m["total"] == 80.0 and m["n"] == 2


def test_referencias_tem_fonte_e_apartamento_calculado():
    refs = dados.carregar_referencias()
    for r in refs.values():
        assert r["valor"] > 0 and r["url"].startswith("https://") and r["fonte"]
    assert refs["apartamento_50m2"]["valor"] == pytest.approx(50 * refs["m2_apartamento"]["valor"], abs=0.01)


@pytest.mark.parametrize("v,esperado", [(144.1, "144"), (1234.4, "1.234"), (28.6, "29"), (5.62, "5,6"), (1.0, "1"), (None, "—")])
def test_qtd(v, esperado):
    assert build.qtd(v) == esperado


def test_brl_partes_e_slug():
    assert build.brl_partes(233591.45) == ("233.591", "45")
    assert build.slug("MISSÃO") == "missao"


def _cand(ano, sq, cpf, nome, urna, uf, cargo="DEPUTADO FEDERAL"):
    return {"ano": ano, "sq": sq, "cpf": cpf, "nome": nome, "nome_urna": urna, "uf": uf,
            "cargo": cargo, "partido": "PL", "situacao": "ELEITO"}


def test_vincular_candidaturas():
    candidaturas = [
        _cand(2022, "1", "00000000001", "FULANO DE TAL", "FULANO", "SP"),
        _cand(2026, "2", "00000000001", "FULANO DE TAL", "FULANO", "SP"),
        _cand(2018, "3", "00000000002", "MARIA DA SILVA SOUZA", "MARIA SOUZA", "BA", "SENADOR"),
        _cand(2022, "4", "00000000003", "JOSE A", "ZE", "RJ"),
        _cand(2022, "5", "00000000004", "JOSE B", "ZE", "RJ"),   # mesmo nome de urna: ambíguo
    ]
    deputados = [{"id": 10, "nome": "Fulano", "siglaUf": "SP"}, {"id": 11, "nome": "Zé", "siglaUf": "RJ"}]
    senadores = [{"IdentificacaoParlamentar": {"CodigoParlamentar": "99", "NomeParlamentar": "Maria Souza",
                                              "NomeCompletoParlamentar": "Maria da Silva Souza", "UfParlamentar": "BA"}}]
    v = coleta.vincular_candidaturas(deputados, senadores, {"10": "00000000001"}, candidaturas)
    assert sorted(c["ano"] for c in v["camara:10"][0]) == [2022, 2026] and v["camara:10"][1] == "cpf"
    assert v["senado:99"][1] == "nome+uf" and v["senado:99"][0][0]["sq"] == "3"
    assert "camara:11" not in v


def test_somar_bens(tmp_path):
    caminho = tmp_path / "bem_candidato_2026.zip"
    campos = ["ANO_ELEICAO", "SQ_CANDIDATO", "DS_TIPO_BEM_CANDIDATO", "VR_BEM_CANDIDATO"]
    texto = io.StringIO()
    w = csv.DictWriter(texto, fieldnames=campos, delimiter=";")
    w.writeheader()
    w.writerow({"ANO_ELEICAO": "2026", "SQ_CANDIDATO": "1", "DS_TIPO_BEM_CANDIDATO": "Apartamento", "VR_BEM_CANDIDATO": "1.200.000,50"})
    w.writerow({"ANO_ELEICAO": "2026", "SQ_CANDIDATO": "1", "DS_TIPO_BEM_CANDIDATO": "Veículo", "VR_BEM_CANDIDATO": "80000,00"})
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("bem_candidato_2026_SP.csv", texto.getvalue().encode("latin-1"))
    bens = tse.somar_bens(caminho)
    assert bens["1"]["total"] == pytest.approx(1280000.50)
    assert bens["1"]["por_tipo"]["Veículo"] == 80000.0


def test_gravar_origem_em_jpeg():
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00rest"
    saida = fotos.gravar_origem(jpeg, "Foto oficial: https://exemplo")
    assert saida.startswith(b"\xff\xd8\xff\xfe")
    assert b"impeccable:prompt\x00Foto oficial: https://exemplo" in saida
    with pytest.raises(ValueError):
        fotos.gravar_origem(b"PNG", "x")


def test_barras_custo_escala_unica():
    linhas = [{"rotulo": "A", "partes": [{"chave": "salario", "nome": "Salário", "valor": 100.0}], "total": 100.0},
              {"rotulo": "B", "partes": [{"chave": "salario", "nome": "Salário", "valor": 25.0}], "total": 25.0}]
    html = graficos.barras_custo(linhas, "teste")
    assert "--f:1.00000" in html and "--f:0.25000" in html
    assert 'data-tip="Salário: R$ 100,00 por mês"' in html
