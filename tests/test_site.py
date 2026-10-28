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


def test_cada_100_soma_exatamente_100():
    custo = {"total": 233591.45, "partes": [
        {"chave": "salario", "nome": "Salário", "valor": 46366.19},
        {"chave": "cota", "nome": "Cota", "valor": 43355.0},
        {"chave": "verba", "nome": "Verba", "valor": 143651.0},
        {"chave": "auxilio", "nome": "Auxílio", "valor": 219.26}]}
    partes = dados.cada_100(custo)
    assert sum(p["reais"] for p in partes) == 100
    assert [p["chave"] for p in partes][0] == "verba"  # maior parte primeiro
    assert partes[-1]["reais"] == 0                    # auxílio pequeno vira "menos de R$ 1"


def _ctx_cards(n_ausentes, n_votos, despesas=False):
    ausentes = [{"nome": f"Dep {i}", "partido": "PL", "uf": "SP", "dias": ["2026-10-13"]} for i in range(n_ausentes)]
    return {"semana": {"camara": {"presenca_semana": {"ausencias_nao_justificadas": ausentes},
                                  "despesas_novas": {"disponivel": despesas}}},
            "votacoes_semana": [{"descricao": "x"}] * n_votos}


def test_carrossel_tem_no_maximo_10_imagens():
    from dp.cards import gerar
    cards = gerar.roteiro_carrossel(_ctx_cards(30, 6, despesas=True))
    assert len(cards) <= gerar.MAX_CARDS
    faltas = [c for c in cards if c[0].startswith("faltas-")]
    mostrados = sum(len(c[2]["nomes"]) for c in faltas)
    assert mostrados + sum(c[2].get("restantes", 0) for c in faltas) == 30  # ninguém some sem aviso
    votos = next(c for c in cards if c[0] == "votacoes")
    assert len(votos[2]["votos"]) == gerar.VOTACOES_POR_CARD and votos[2]["restantes"] == 4


def test_carrossel_semana_sem_sessao():
    from dp.cards import gerar
    nomes = [c[0] for c in gerar.roteiro_carrossel(_ctx_cards(0, 0))]
    assert nomes == ["capa", "custo", "compra", "alem", "presenca", "votacoes", "dias", "fim"]


def test_descricao_sem_placar():
    assert dados.sem_placar("Aprovado o Requerimento. Sim: 11; Não: 387; Total: 398.") == "Aprovado o Requerimento."


@pytest.mark.parametrize("descricao,tipo", [
    ("Aprovado o Projeto de Lei nº 3.292, de 2025. Sim: 265; Não: 33; Total: 298.", "principal"),
    ("Aprovado o Projeto de Lei nº 1, de 2025, ressalvados os destaques.", "principal"),
    ("Aprovada, em segundo turno, a Proposta de Emenda à Constituição nº 66, de 2023.", "principal"),
    ("Aprovada a Subemenda Substitutiva Global ao Projeto de Lei nº 2, de 2024, adotada pelo relator.", "principal"),
    ("Aprovada, em primeiro turno, a Emenda Aglutinativa Substitutiva à Proposta de Emenda à Constituição nº 3.", "principal"),
    ("Rejeitada a Emenda de Plenário nº 4. Sim: 100; Não: 300.", "trecho"),
    ("Mantido o texto. Sim: 313; Não: 119; Total: 433.", "trecho"),
    ("Aprovado o Requerimento de Urgência (Art. 155 do RICD). Sim: 376; Não: 42.", "urgencia"),
    ("Rejeitado o Requerimento. Sim: 110; Não: 159; Total: 269.", "pedido"),
    ("Rejeitada a preferência.", "pedido"),
])
def test_tipo_votacao(descricao, tipo):
    assert dados.tipo_votacao(descricao) == tipo


def test_proposicao_principal_prefere_o_codigo_da_votacao():
    from dp import rankings
    props = [{"proposicao_id": "9", "proposicao_siglaTipo": "PL"}, {"proposicao_id": "2458405", "proposicao_siglaTipo": "PL"}]
    assert rankings.proposicao_principal("2458405-38", props)["proposicao_id"] == "2458405"
    assert rankings.proposicao_principal("777-1", props)["proposicao_id"] == "9"   # código fora da lista: a 1ª ligada
    urgencia = [{"proposicao_id": "5", "proposicao_siglaTipo": "REQ"}, {"proposicao_id": "6", "proposicao_siglaTipo": "PDL"}]
    assert rankings.proposicao_principal("5-1", urgencia)["proposicao_id"] == "6"  # o projeto, não o requerimento
    assert rankings.proposicao_principal("5-1", urgencia[:1])["proposicao_id"] == "5"
    assert rankings.proposicao_principal("777-1", []) is None


def test_votos_plenario_indice_e_arquivo_por_deputado(tmp_path):
    from dp import db
    conn = db.conectar(tmp_path / "t.db")
    conn.executemany("INSERT INTO plenario_votacao VALUES (?, ?, ?, ?, ?, ?)", [
        ("camara:1-1", "2025-03-01", "Rejeitado o Requerimento. Sim: 1; Não: 2", 0, "1", "u1"),
        ("camara:1-2", "2025-05-01", "Aprovado o Projeto de Lei nº 1, de 2025.", 1, "1", "u2"),
    ])
    conn.execute("INSERT INTO plenario_proposicao VALUES ('1', 'PL 1/2025', 'Ementa')")
    conn.executemany("INSERT INTO plenario_voto VALUES (?, ?, ?, ?)", [
        ("camara:1-1", "camara:10", "Não", "PSD"), ("camara:1-2", "camara:10", "Sim", "PL"),
        ("camara:1-1", "camara:11", "Sim", "PT"), ("camara:1-1", "camara:12", "Obstrução", "PT"),
    ])
    pessoas = [{"id": "camara:10", "casa": "camara", "slug": "fulano", "partido": "PL"},
               {"id": "senado:5", "casa": "senado", "slug": "beltrano", "partido": "PL"}]
    indice, por_pessoa = dados.votos_plenario(conn, pessoas)
    assert [v[0] for v in indice["votacoes"]] == ["2025-05-01", "2025-03-01"]   # mais recente primeiro
    assert indice["votacoes"][1][1] == "Rejeitado o Requerimento."               # sem o placar
    assert indice["votacoes"][1][3] == "pedido" and indice["votacoes"][1][6:8] == [1, 1]
    assert indice["votacoes"][1][2] == "rejeitado"
    assert indice["explicacoes"][indice["votacoes"][1][8]][1] == "Sim = a favor do pedido."
    assert indice["proposicoes"][indice["votacoes"][0][4]][0] == "PL 1/2025"
    assert set(por_pessoa) == {"fulano"}                                         # só deputados
    assert por_pessoa["fulano"]["votos"] == [[0, "S"], [1, "N"]]
    assert por_pessoa["fulano"]["partidos"] == {"1": "PSD"}                      # votou por outro partido


def test_casos_json_tem_fonte_situacao_e_data_validas():
    import json
    import re
    bruto = json.loads(dados.ARQUIVO_CASOS.read_text(encoding="utf-8"))
    ids = [c["id"] for c in bruto["casos"]]
    assert len(ids) == len(set(ids))
    for c in bruto["casos"]:
        assert re.fullmatch(r"(camara|senado):\d+", c["parlamentar"]), c["id"]
        assert c["situacao"] in bruto["situacoes"] and c["assunto"] in bruto["assuntos"], c["id"]
        assert re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", c["data"]) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["conferido_em"])
        assert c["titulo"] and c["resumo"] and c["detalhe"], c["id"]
        assert c["fontes"] and all(f["url"].startswith("https://") and f["veiculo"] for f in c["fontes"]), c["id"]


def test_data_caso_aceita_mes_e_ano():
    assert build.data_caso("2022-12") == "dez/2022"
    assert build.data_caso("2026-03-17") == "17/03/2026"


@pytest.mark.parametrize("descricao,o_que,sim", [
    ("Aprovada a Emenda de Redação n° 2. Sim: 314; Não: 117; Abstenção: 1; Total: 432.", "Ajuste de redação", "aprovar o ajuste"),
    ("Rejeitados os dispositivos do Substitutivo do Senado Federal ao Projeto de Lei Complementar nº 68, de 2024, "
     "com parecer pela rejeição. Sim: 18; Não: 328.", "relator recomendou derrubar", "manter essas mudanças do Senado"),
    ("Rejeitada a Emenda nº 33 do Senado Federal.", "Mudanças que o Senado fez", "manter as mudanças do Senado"),
    ("Mantido o texto. Sim: 313; Não: 119; Total: 433.", "destaque", "manter o trecho"),
    ("Aprovado o Requerimento de Urgência (Art. 155 do RICD).", "urgência", "a favor da urgência"),
    ("Rejeitado o Requerimento.", "andamento da votação", "a favor do pedido"),
    ("Aprovado o Projeto de Lei nº 3.292, de 2025.", "texto principal do projeto", "aprovar o projeto"),
])
def test_explicar_votacao(descricao, o_que, sim):
    e = dados.explicar_votacao(descricao)
    assert o_que in e["o_que"] and sim in e["sim"]


def test_explicar_votacao_resultado_e_placar():
    e = dados.explicar_votacao("Rejeitado o Requerimento. Sim: 110; Não: 159; Total: 269.")
    assert e["resultado"] == "rejeitado" and e["placar"] == (110, 159)
    assert dados.explicar_votacao("Resultado.") is None
    assert dados.explicar_votacao("Suprimido o texto. Sim: 200; Não: 250.")["resultado"] == "o trecho saiu"
