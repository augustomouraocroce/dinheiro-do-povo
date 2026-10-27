"""Métricas do relatório semanal.

Só agrega o que já está no banco (não acessa a internet). Cada bloco devolve
números prontos e a URL da fonte oficial de onde vieram. Toda tabela por
partido termina com a linha da Casa inteira ("Todos"), usada como comparação.
"""
from collections import Counter, defaultdict
from datetime import date, datetime

from dp import config
from dp.fontes import senado

TODOS = "Todos"
CATEGORIAS_CAMARA = ("presente", "ausencia_justificada", "ausencia_nao_justificada")
CATEGORIAS_SENADO = ("votou", "presente_sem_voto", "ausencia_justificada",
                     "ausencia_nao_justificada")
CAMPOS_CUSTO = ("salario", "cota_gasto", "cota_disponivel", "verba_gasto", "verba_disponivel",
                "imovel_funcional", "auxilio_moradia", "auxilio_moradia_valor")


# --- Quem é quem -----------------------------------------------------------------

def partidos_na_data(conn, ref: str) -> dict:
    """Partido de cada parlamentar na data `ref` (AAAA-MM-DD).

    Usa a última filiação vista até `ref`; se a primeira coleta é posterior a
    `ref`, usa a filiação mais antiga disponível.
    """
    linhas = conn.execute(
        """SELECT f.parlamentar_id, f.partido FROM filiacao f
           JOIN (SELECT parlamentar_id,
                        COALESCE(MAX(CASE WHEN visto_em <= ? THEN visto_em END), MIN(visto_em)) AS v
                 FROM filiacao GROUP BY parlamentar_id) x
             ON x.parlamentar_id = f.parlamentar_id AND x.v = f.visto_em""",
        (ref,))
    return {pid: partido for pid, partido in linhas}


def pessoas_da_casa(conn, casa: str, partidos: dict) -> dict:
    """{id: {id, nome, uf, url, partido}} dos parlamentares com filiação conhecida."""
    linhas = conn.execute(
        "SELECT id, nome, uf, url_perfil FROM parlamentar WHERE casa = ?", (casa,))
    return {
        r["id"]: {"id": r["id"], "nome": r["nome"], "uf": r["uf"],
                  "url": r["url_perfil"], "partido": partidos[r["id"]]}
        for r in linhas if r["id"] in partidos
    }


def partidos_presentes(pessoas: dict) -> list:
    """Partidos monitorados que têm parlamentares na Casa, na ordem da configuração."""
    existentes = {p["partido"] for p in pessoas.values()}
    return [p for p in config.PARTIDOS_MONITORADOS if p in existentes]


def _monitorado(pessoa) -> bool:
    return pessoa["partido"] in config.PARTIDOS_MONITORADOS


def por_partido(pessoas, partidos, valores: dict, campos) -> list:
    """Soma `campos` de `valores` ({id: {campo: número}}) por partido + linha "Todos".

    Só entra quem está em `valores`: quem não tem dado não conta como zero.
    """
    grupos = defaultdict(list)
    for pid, v in valores.items():
        if pid in pessoas:
            grupos[pessoas[pid]["partido"]].append(v)
            grupos[TODOS].append(v)
    linhas = []
    for partido in list(partidos) + [TODOS]:
        vs = grupos.get(partido, [])
        linha = {"partido": partido, "parlamentares": len(vs)}
        for c in campos:
            linha[c] = sum(v.get(c) or 0 for v in vs)
        linhas.append(linha)
    return linhas


def _razao(a, b):
    return a / b if b else None


# --- Câmara: presença (página oficial "Presença em Plenário") ----------------------

def presenca_camara(conn, pessoas, partidos, de: str, ate: str) -> dict:
    linhas = conn.execute(
        """SELECT parlamentar_id, data, status, categoria, url_fonte FROM presenca_dia
           WHERE parlamentar_id LIKE 'camara:%' AND data BETWEEN ? AND ?""", (de, ate))
    contagem = defaultdict(Counter)
    dias, fontes, ausencias, motivos = set(), {}, defaultdict(list), Counter()
    for r in linhas:
        pid = r["parlamentar_id"]
        if pid not in pessoas:
            continue
        contagem[pid][r["categoria"]] += 1
        dias.add(r["data"])
        fontes[pid] = r["url_fonte"]
        if not _monitorado(pessoas[pid]):
            continue
        if r["categoria"] == "ausencia_nao_justificada":
            ausencias[pid].append(r["data"])
        elif r["categoria"] == "ausencia_justificada":
            motivos[r["status"]] += 1

    tabela = por_partido(pessoas, partidos, contagem, CATEGORIAS_CAMARA)
    for linha in tabela:
        linha["registros"] = sum(linha[c] for c in CATEGORIAS_CAMARA)
        linha["pct_presenca"] = _razao(linha["presente"], linha["registros"])
        linha["pct_nao_justificada"] = _razao(linha["ausencia_nao_justificada"], linha["registros"])

    lista = sorted(
        ({**pessoas[pid], "dias": sorted(ds), "url_fonte": fontes[pid],
          "dias_com_sessao": sum(contagem[pid].values())}
         for pid, ds in ausencias.items()),
        key=lambda p: (-len(p["dias"]), p["nome"]))
    return {
        "dias_com_sessao": sorted(dias),
        "por_partido": tabela,
        "ausencias_nao_justificadas": lista,
        "motivos_justificados": motivos.most_common(),
    }


# --- Câmara: votações nominais ------------------------------------------------------

def _membros(pessoas, partido):
    return [pid for pid, p in pessoas.items() if p["partido"] == partido]


def votacoes_camara(conn, pessoas, partidos, de: str, ate: str) -> list:
    votacoes = conn.execute(
        """SELECT * FROM votacao WHERE casa = 'camara' AND data BETWEEN ? AND ?
             AND id IN (SELECT votacao_id FROM voto) ORDER BY data, id""", (de, ate)).fetchall()
    saida = []
    for v in votacoes:
        votos = dict(conn.execute(
            "SELECT parlamentar_id, voto FROM voto WHERE votacao_id = ?", (v["id"],)).fetchall())
        bancadas = []
        for partido in partidos:
            membros = _membros(pessoas, partido)
            c = Counter(votos[m] for m in membros if m in votos)
            bancadas.append({"partido": partido, "membros": len(membros),
                             "sim": c["Sim"], "nao": c["Não"],
                             "outros": sum(c.values()) - c["Sim"] - c["Não"],
                             "sem_registro": sum(1 for m in membros if m not in votos)})
        sessao = v["sessao_id"].split(":", 1)[1] if v["sessao_id"] else None
        saida.append({
            "data": v["data"], "descricao": v["descricao"], "aprovada": v["aprovada"],
            "url": v["url_fonte"],
            "url_sessao": config.CAMARA_EVENTO.format(id=sessao) if sessao else None,
            "placar": dict(Counter(votos.values())), "bancadas": bancadas,
        })
    return saida


# --- Câmara: custos (página oficial de cada deputado) --------------------------------

def custos_camara(conn, pessoas, partidos, ano: int) -> dict:
    linhas = conn.execute(
        """SELECT parlamentar_id, item, valor, texto, url_fonte, atualizado_fonte
           FROM recurso_oficial WHERE ano = ? AND parlamentar_id LIKE 'camara:%'""", (ano,))
    itens, fontes, atualizacoes = defaultdict(dict), {}, Counter()
    for r in linhas:
        itens[r["parlamentar_id"]][r["item"]] = r
        fontes[r["parlamentar_id"]] = r["url_fonte"]
        if r["atualizado_fonte"]:
            atualizacoes[r["atualizado_fonte"]] += 1

    def num(d, item):
        return d[item]["valor"] if item in d and d[item]["valor"] is not None else 0.0

    def txt(d, item):
        return d[item]["texto"] if item in d else ""

    valores = {}
    for pid, d in itens.items():
        valores[pid] = {
            "salario": num(d, "salario_bruto_mensal"),
            "cota_gasto": num(d, "cota_gasto"),
            "cota_disponivel": num(d, "cota_gasto") + num(d, "cota_nao_utilizado"),
            "verba_gasto": num(d, "verba_gabinete_gasto"),
            "verba_disponivel": num(d, "verba_gabinete_gasto") + num(d, "verba_gabinete_nao_utilizado"),
            # "Faz uso" = usa hoje; "Fez uso" = usou no ano e já devolveu.
            "imovel_funcional": int(txt(d, "imovel_funcional").startswith("Faz uso")),
            "auxilio_moradia": int(num(d, "auxilio_moradia") > 0),
            "auxilio_moradia_valor": num(d, "auxilio_moradia"),
        }

    tabela = por_partido(pessoas, partidos, valores, CAMPOS_CUSTO)
    for linha in tabela:
        n = linha["parlamentares"]
        linha["salario_medio"] = _razao(linha.get("salario", 0), n)
        linha["cota_media"] = _razao(linha.get("cota_gasto", 0), n)
        linha["pct_cota"] = _razao(linha.get("cota_gasto", 0), linha.get("cota_disponivel", 0))
        linha["verba_media"] = _razao(linha.get("verba_gasto", 0), n)
        linha["pct_verba"] = _razao(linha.get("verba_gasto", 0), linha.get("verba_disponivel", 0))

    maiores_pct_cota = sorted(
        ({**pessoas[pid], "cota_gasto": v["cota_gasto"],
          "pct_cota": _razao(v["cota_gasto"], v["cota_disponivel"]), "url_fonte": fontes[pid]}
         for pid, v in valores.items()
         if pid in pessoas and _monitorado(pessoas[pid]) and v["cota_disponivel"]),
        key=lambda p: (-p["pct_cota"], p["nome"]))
    # Diferença entre o total oficial de cota usada (páginas dos deputados) e a
    # soma das notas do arquivo anual: o arquivo não traz todas as despesas
    # (ex.: passagens aéreas emitidas pelo sistema da Câmara).
    soma_notas = dict(conn.execute(
        """SELECT parlamentar_id, SUM(valor_liquido) FROM despesa
           WHERE casa = 'camara' AND ano = ? AND parlamentar_id IS NOT NULL
           GROUP BY parlamentar_id""", (ano,)).fetchall())
    com_perfil = [pid for pid in valores if pid in pessoas]
    return {
        "ano": ano,
        "atualizado_fonte": atualizacoes.most_common(1)[0][0] if atualizacoes else None,
        "por_partido": tabela,
        "maiores_pct_cota": maiores_pct_cota,
        "conferencia_notas": {
            "total_paginas": sum(valores[p]["cota_gasto"] for p in com_perfil),
            "total_notas": sum(soma_notas.get(p, 0.0) for p in com_perfil),
        },
    }


# --- Despesas lançadas na semana (as duas Casas) ------------------------------------

def despesas_novas(conn, casa, pessoas, partidos, inicio: date, sabado: date) -> dict:
    """Notas que apareceram nas coletas feitas depois de `inicio` e até `sabado`.

    Notas da carga inicial nunca contam como novas. Se a primeira coleta foi
    depois do sábado do relatório, não há como saber o que é novo.
    """
    primeira = conn.execute(
        "SELECT MIN(primeira_vez_vista) FROM despesa WHERE casa = ?", (casa,)).fetchone()[0]
    if primeira is None or primeira >= sabado.isoformat():
        return {"disponivel": False, "primeira_coleta": primeira}

    desde = max(inicio.isoformat(), primeira)
    linhas = conn.execute(
        """SELECT * FROM despesa WHERE casa = ? AND carga_inicial = 0
             AND primeira_vez_vista > ? AND primeira_vez_vista <= ?""",
        (casa, desde, sabado.isoformat())).fetchall()
    do_partido = [r for r in linhas if r["parlamentar_id"] in pessoas]
    valores = defaultdict(lambda: {"notas": 0, "valor": 0.0})
    for r in do_partido:
        valores[r["parlamentar_id"]]["notas"] += 1
        valores[r["parlamentar_id"]]["valor"] += r["valor_liquido"]

    monitoradas = [r for r in do_partido if _monitorado(pessoas[r["parlamentar_id"]])]
    categorias = Counter()
    for r in monitoradas:
        categorias[r["categoria"]] += r["valor_liquido"]
    maiores = sorted(monitoradas, key=lambda r: -r["valor_liquido"])[:10]
    return {
        "disponivel": True,
        "primeira_coleta": primeira,
        "desde": desde,
        "por_partido": por_partido(pessoas, partidos, valores, ("notas", "valor")),
        "por_categoria": categorias.most_common(8),
        "maiores": [{**pessoas[r["parlamentar_id"]], "valor": r["valor_liquido"],
                     "categoria": r["categoria"], "fornecedor": r["fornecedor"],
                     "data_emissao": r["data_emissao"], "url_documento": r["url_documento"]}
                    for r in maiores],
    }


# --- Senado: votações nominais e participação ---------------------------------------

def votacoes_senado(conn, pessoas, partidos, de: str, ate: str) -> dict:
    votacoes = conn.execute(
        "SELECT * FROM votacao WHERE casa = 'senado' AND data BETWEEN ? AND ? ORDER BY data, id",
        (de, ate)).fetchall()
    participacao = defaultdict(Counter)
    nao_compareceu = defaultdict(list)
    lista = []
    for v in votacoes:
        votos = dict(conn.execute(
            "SELECT parlamentar_id, voto FROM voto WHERE votacao_id = ?", (v["id"],)).fetchall())
        for pid, sigla in votos.items():
            categoria = senado.classificar_voto(sigla)
            participacao[pid][categoria] += 1
            if categoria == "ausencia_nao_justificada" and pid in pessoas and _monitorado(pessoas[pid]):
                nao_compareceu[pid].append({"data": v["data"], "descricao": v["descricao"],
                                            "url": v["url_fonte"]})
        bancadas = []
        for partido in partidos:
            membros = _membros(pessoas, partido)
            siglas = Counter(votos[m] for m in membros if m in votos)
            cats = Counter()
            for sigla, n in siglas.items():
                cats[senado.classificar_voto(sigla)] += n
            bancadas.append({"partido": partido, "membros": len(membros),
                             "sim": siglas["Sim"], "nao": siglas["Não"],
                             "outros": cats["votou"] - siglas["Sim"] - siglas["Não"],
                             **{c: cats[c] for c in CATEGORIAS_SENADO if c != "votou"}})
        lista.append({"data": v["data"], "descricao": v["descricao"], "aprovada": v["aprovada"],
                      "url": v["url_fonte"], "placar": dict(Counter(votos.values())),
                      "bancadas": bancadas})

    tabela = por_partido(pessoas, partidos, participacao, CATEGORIAS_SENADO)
    for linha in tabela:
        linha["registros"] = sum(linha[c] for c in CATEGORIAS_SENADO)
        linha["pct_votou"] = _razao(linha["votou"], linha["registros"])
    return {
        "votacoes": lista,
        "por_partido": tabela,
        "nao_compareceu": sorted(
            ({**pessoas[pid], "votacoes": vs} for pid, vs in nao_compareceu.items()),
            key=lambda p: (-len(p["votacoes"]), p["nome"])),
    }


# --- Senado: cota (CEAPS) acumulada no ano -------------------------------------------

def ceaps_ano(conn, pessoas, partidos, ano: int) -> dict:
    somas = dict(conn.execute(
        """SELECT parlamentar_id, SUM(valor_liquido) FROM despesa
           WHERE casa = 'senado' AND ano = ? AND parlamentar_id IS NOT NULL
           GROUP BY parlamentar_id""", (ano,)).fetchall())
    # Senador em exercício sem nenhuma nota no ano conta como R$ 0,00.
    valores = {pid: {"valor": somas.get(pid, 0.0)} for pid in pessoas}
    tabela = por_partido(pessoas, partidos, valores, ("valor",))
    for linha in tabela:
        linha["media"] = _razao(linha["valor"], linha["parlamentares"])
    maiores = sorted(
        ({**p, "valor": valores[pid]["valor"]} for pid, p in pessoas.items() if _monitorado(p)),
        key=lambda p: (-p["valor"], p["nome"]))
    return {"ano": ano, "por_partido": tabela, "maiores": maiores}


# --- Relatório completo ------------------------------------------------------------------

def montar_relatorio(conn, sabado: date) -> dict:
    inicio, fim = config.semana_referencia(sabado)
    de, ate = inicio.isoformat(), fim.isoformat()
    inicio_ano = date(fim.year, 1, 1).isoformat()
    partidos = partidos_na_data(conn, sabado.isoformat())

    dep = pessoas_da_casa(conn, "camara", partidos)
    sen = pessoas_da_casa(conn, "senado", partidos)
    p_dep, p_sen = partidos_presentes(dep), partidos_presentes(sen)

    return {
        "sabado": sabado, "inicio": inicio, "fim": fim,
        "gerado_em": datetime.now(),
        "partidos_nomes": config.PARTIDOS_MONITORADOS,
        "camara": {
            "partidos": p_dep,
            "monitorados": sum(1 for p in dep.values() if _monitorado(p)),
            "total": len(dep),
            "presenca_semana": presenca_camara(conn, dep, p_dep, de, ate),
            "presenca_ano": presenca_camara(conn, dep, p_dep, inicio_ano, ate),
            "votacoes": votacoes_camara(conn, dep, p_dep, de, ate),
            "custos": custos_camara(conn, dep, p_dep, fim.year),
            "despesas_novas": despesas_novas(conn, "camara", dep, p_dep, inicio, sabado),
        },
        "senado": {
            "partidos": p_sen,
            "monitorados": sum(1 for p in sen.values() if _monitorado(p)),
            "total": len(sen),
            "votacoes": votacoes_senado(conn, sen, p_sen, de, ate),
            "votacoes_ano": votacoes_senado(conn, sen, p_sen, inicio_ano, ate),
            "ceaps": ceaps_ano(conn, sen, p_sen, fim.year),
            "despesas_novas": despesas_novas(conn, "senado", sen, p_sen, inicio, sabado),
        },
    }
