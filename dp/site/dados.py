"""Dados de cada página do site, montados a partir do banco e das referências.

Regras de cálculo (repetidas na página de metodologia):
- Custo médio por mês de um deputado = salário bruto + média mensal da cota +
  média mensal da verba de gabinete + auxílio-moradia do ano ÷ meses decorridos.
- As médias da cota e da verba usam só os meses fora da janela de 90 dias em
  que notas ainda podem entrar (ex.: em outubro, janeiro a julho).
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date

from dp import calendario, config, metricas, trabalho
from dp.fontes import senado

ARQUIVO_REFERENCIAS = config.ROOT / "dp" / "referencias.json"
ARQUIVO_ERRATA = config.ROOT / "dp" / "errata.json"
JANELA_MESES = 3  # a Câmara aceita notas até 90 dias depois do gasto

PARTES_CUSTO = (
    ("salario", "Salário bruto"),
    ("cota", "Cota parlamentar"),
    ("verba", "Verba de gabinete"),
    ("auxilio", "Auxílio-moradia"),
)
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# --- Referências do dia a dia ------------------------------------------------------

def carregar_referencias() -> dict:
    refs = {k: v for k, v in json.loads(ARQUIVO_REFERENCIAS.read_text(encoding="utf-8")).items()
            if not k.startswith("_")}
    apto = refs["apartamento_50m2"]
    apto["valor"] = round(apto["metros"] * refs["m2_apartamento"]["valor"], 2)
    for chave, r in refs.items():
        r["chave"] = chave
    return refs


def carregar_beneficios() -> dict:
    caminho = config.ROOT / "dp" / "beneficios.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def carregar_errata() -> list:
    if not ARQUIVO_ERRATA.exists():
        return []
    return json.loads(ARQUIVO_ERRATA.read_text(encoding="utf-8"))


def equivale(valor: float, ref: dict) -> dict:
    qtd = valor / ref["valor"] if ref["valor"] else 0
    return {"ref": ref, "qtd": qtd}


# --- Câmara: custo médio por mês ------------------------------------------------------

def recursos_por_deputado(conn, ano: int) -> dict:
    linhas = conn.execute(
        """SELECT parlamentar_id, item, valor, texto, url_fonte, atualizado_fonte
           FROM recurso_oficial WHERE ano = ?""", (ano,))
    saida = defaultdict(dict)
    for r in linhas:
        saida[r["parlamentar_id"]][r["item"]] = dict(r)
    return saida


def _serie_mensal(itens: dict, prefixo: str) -> dict:
    """{mês: valor} a partir de itens 'prefixo_01'..'prefixo_12'."""
    serie = {}
    for item, r in itens.items():
        if item.startswith(prefixo) and r["valor"] is not None:
            serie[int(item[len(prefixo):])] = r["valor"]
    return serie


def _media_consolidada(serie: dict, mes_corte: int):
    meses = [v for m, v in serie.items() if m <= mes_corte]
    return (sum(meses) / len(meses), len(meses)) if meses else (None, 0)


def custo_mensal_deputado(itens: dict, mes_atual: int) -> dict:
    mes_corte = max(1, mes_atual - JANELA_MESES)
    cota_serie = _serie_mensal(itens, "cota_mes_")
    verba_serie = _serie_mensal(itens, "verba_gabinete_mes_")
    cota, n_cota = _media_consolidada(cota_serie, mes_corte)
    verba, n_verba = _media_consolidada(verba_serie, mes_corte)
    salario = (itens.get("salario_bruto_mensal") or {}).get("valor") or 0.0
    auxilio_ano = (itens.get("auxilio_moradia") or {}).get("valor") or 0.0
    valores = {"salario": salario, "cota": cota or 0.0, "verba": verba or 0.0,
               "auxilio": auxilio_ano / mes_atual}
    return {
        "partes": [{"chave": k, "nome": n, "valor": valores[k]} for k, n in PARTES_CUSTO],
        "total": sum(valores.values()),
        "mes_corte": mes_corte,
        "meses_cota": n_cota,
        "meses_verba": n_verba,
        "cota_serie": cota_serie,
        "auxilio_ano": auxilio_ano,
    }


NOMES_POPULARES = {
    "salario": ("Salário do deputado", "o salário bruto, antes dos descontos"),
    "cota": ("Cota para gastos do mandato", "combustível, passagens, divulgação, escritório"),
    "verba": ("Salários da equipe do gabinete", "até 25 funcionários escolhidos pelo deputado"),
    "auxilio": ("Auxílio-moradia", "para quem não usa imóvel funcional"),
}


def cada_100(custo: dict) -> list:
    """Divide R$ 100 entre as partes do custo (maiores restos), para a soma dar exatamente 100."""
    total = custo["total"] or 1
    partes = [p for p in custo["partes"] if p["valor"] > 0]
    brutos = [100 * p["valor"] / total for p in partes]
    inteiros = [int(b) for b in brutos]
    for i in sorted(range(len(partes)), key=lambda i: brutos[i] - inteiros[i], reverse=True)[:100 - sum(inteiros)]:
        inteiros[i] += 1
    return [{"chave": p["chave"], "nome": NOMES_POPULARES[p["chave"]][0], "explica": NOMES_POPULARES[p["chave"]][1],
             "reais": n, "pct": p["valor"] / total, "valor": p["valor"]}
            for p, n in sorted(zip(partes, inteiros), key=lambda x: -x[0]["valor"])]


def media_partes(custos: list) -> dict:
    """Média de cada parte entre vários custos mensais."""
    n = len(custos) or 1
    medias = {k: sum(next(p["valor"] for p in c["partes"] if p["chave"] == k) for c in custos) / n
              for k, _ in PARTES_CUSTO}
    return {"partes": [{"chave": k, "nome": nome, "valor": medias[k]} for k, nome in PARTES_CUSTO],
            "total": sum(medias.values()), "n": len(custos)}


# --- Presença, votos e patrimônio -------------------------------------------------

def presenca_por_parlamentar(conn, ano: int) -> dict:
    linhas = conn.execute(
        """SELECT parlamentar_id, data, status, categoria, url_fonte FROM presenca_dia
           WHERE data LIKE ? ORDER BY data""", (f"{ano}-%",))
    saida = defaultdict(lambda: {"dias": [], "contagem": Counter(), "url": None})
    for r in linhas:
        p = saida[r["parlamentar_id"]]
        p["dias"].append({"data": r["data"], "status": r["status"], "categoria": r["categoria"]})
        p["contagem"][r["categoria"]] += 1
        p["url"] = r["url_fonte"]
    for p in saida.values():
        total = sum(p["contagem"].values())
        p["total"] = total
        p["pct_presente"] = p["contagem"]["presente"] / total if total else None
    return saida


def participacao_senado(conn, ano: int) -> dict:
    linhas = conn.execute(
        """SELECT vt.parlamentar_id, vt.voto FROM voto vt JOIN votacao v ON v.id = vt.votacao_id
           WHERE v.casa = 'senado' AND v.data LIKE ?""", (f"{ano}-%",))
    saida = defaultdict(Counter)
    for pid, sigla in linhas:
        saida[pid][senado.classificar_voto(sigla)] += 1
    resultado = {}
    for pid, c in saida.items():
        registros = sum(c[k] for k in metricas.CATEGORIAS_SENADO)
        resultado[pid] = {"contagem": c, "registros": registros,
                          "pct_votou": c["votou"] / registros if registros else None}
    return resultado


def votos_da_semana(conn, casa: str, de: str, ate: str) -> list:
    votacoes = conn.execute(
        """SELECT * FROM votacao WHERE casa = ? AND data BETWEEN ? AND ?
             AND id IN (SELECT votacao_id FROM voto) ORDER BY data, id""", (casa, de, ate)).fetchall()
    saida = []
    for v in votacoes:
        votos = dict(conn.execute("SELECT parlamentar_id, voto FROM voto WHERE votacao_id = ?",
                                  (v["id"],)).fetchall())
        saida.append({"data": v["data"], "descricao": v["descricao"], "aprovada": v["aprovada"],
                      "url": v["url_fonte"], "votos": votos})
    return saida


def patrimonio_por_parlamentar(conn) -> dict:
    saida = defaultdict(lambda: {"declaracoes": [], "tipos": {}})
    for r in conn.execute("SELECT * FROM patrimonio ORDER BY ano_eleicao"):
        saida[r["parlamentar_id"]]["declaracoes"].append(dict(r))
    for r in conn.execute("SELECT * FROM patrimonio_tipo ORDER BY valor DESC"):
        saida[r["parlamentar_id"]]["tipos"].setdefault(r["ano_eleicao"], []).append(
            {"tipo": r["tipo"], "valor": r["valor"]})
    for p in saida.values():
        p["ultima"] = p["declaracoes"][-1] if p["declaracoes"] else None
        p["tipos_ultima"] = p["tipos"].get(p["ultima"]["ano_eleicao"], []) if p["ultima"] else []
    return saida


def ceaps_mensal(conn, ano: int) -> dict:
    saida = defaultdict(dict)
    for pid, mes, v in conn.execute(
            """SELECT parlamentar_id, mes, SUM(valor_liquido) FROM despesa
               WHERE casa = 'senado' AND ano = ? AND parlamentar_id IS NOT NULL
               GROUP BY 1, 2""", (ano,)):
        saida[pid][mes] = v
    return saida


# --- Trabalho e renda: votações e dias de trabalho ----------------------------------

def _categoria_voto(casa: str, sigla: str):
    """sim / nao / outros (abstenção, obstrução, voto secreto...) ou None quando não é voto
    (no Senado, códigos de ausência como "NCom" e "AP" vêm junto com os votos)."""
    if sigla == "Sim":
        return "sim"
    if sigla == "Não":
        return "nao"
    if casa == "senado" and senado.classificar_voto(sigla) != "votou":
        return None
    return "outros"


def pauta_trabalho(conn, partidos_monitorados) -> dict:
    """Votações sobre trabalho e renda agrupadas por proposição, com o voto de cada um."""
    regras = trabalho.carregar_regras()
    incluidas = {i["titulo"] for i in regras["incluidas"]}
    linhas = conn.execute(
        """SELECT p.votacao_id, p.casa, p.proposicao, p.ementa, p.url_proposicao, p.motivo,
                  v.data, v.descricao, v.aprovada, v.url_fonte, v.sessao_id
           FROM pauta_trabalho p JOIN votacao v ON v.id = p.votacao_id
           ORDER BY v.data DESC, v.id DESC""").fetchall()
    votos = defaultdict(list)
    for vid, pid, voto, partido in conn.execute(
            """SELECT votacao_id, parlamentar_id, voto, partido FROM voto
               WHERE votacao_id IN (SELECT votacao_id FROM pauta_trabalho)"""):
        votos[vid].append((pid, voto, partido))

    grupos, por_parlamentar = {}, defaultdict(list)
    for r in linhas:
        chave = (r["casa"], r["proposicao"])
        g = grupos.setdefault(chave, {
            "casa": r["casa"], "proposicao": r["proposicao"], "ementa": (r["ementa"] or "").split("\n")[0].strip(),
            "motivo": r["motivo"], "url": r["url_proposicao"], "destaque": r["proposicao"] in incluidas,
            "votacoes": [], "ultima": r["data"], "slug": slug_proposicao(r["casa"], r["proposicao"])})
        sessao = r["sessao_id"].split(":", 1)[1] if r["sessao_id"] and r["casa"] == "camara" else None
        placar = Counter(c for c in (_categoria_voto(r["casa"], v) for _, v, _ in votos[r["votacao_id"]]) if c)
        por_partido = []
        for sigla in partidos_monitorados:
            c = Counter(x for x in (_categoria_voto(r["casa"], v) for _, v, pt in votos[r["votacao_id"]] if pt == sigla) if x)
            if sum(c.values()):
                por_partido.append({"partido": sigla, **{k: c[k] for k in ("sim", "nao", "outros")}})
        votacao = {"id": r["votacao_id"], "data": r["data"], "descricao": r["descricao"], "aprovada": r["aprovada"],
                   "url": r["url_fonte"], "url_sessao": config.CAMARA_EVENTO.format(id=sessao) if sessao else None,
                   "placar": placar, "por_partido": por_partido}
        g["votacoes"].append(votacao)
        for pid, voto, partido in votos[r["votacao_id"]]:
            if _categoria_voto(r["casa"], voto):
                por_parlamentar[pid].append({"grupo": chave, "votacao": votacao, "voto": voto, "partido_epoca": partido})

    ordem = sorted(grupos.values(), key=lambda g: (not g["destaque"], g["ultima"] and -int(g["ultima"].replace("-", ""))))
    return {"grupos": ordem, "por_parlamentar": por_parlamentar, "regras": regras,
            "total": len(linhas), "camara": sum(1 for r in linhas if r["casa"] == "camara"),
            "senado": sum(1 for r in linhas if r["casa"] == "senado")}


def slug_proposicao(casa: str, titulo: str) -> str:
    return casa + "-" + "".join(ch if ch.isalnum() else "-" for ch in senado.normalizar_nome(titulo).lower()).strip("-")


def votos_trabalho_da_pessoa(pauta, pid):
    """Votos da pessoa agrupados por proposição, na ordem da página de trabalho."""
    meus = defaultdict(list)
    for item in pauta["por_parlamentar"].get(pid, []):
        meus[item["grupo"]].append(item)
    grupos = []
    for g in pauta["grupos"]:
        chave = (g["casa"], g["proposicao"])
        if chave in meus:
            grupos.append({"grupo": g, "votos": meus[chave]})
    contagem = Counter(_categoria_voto(i["grupo"][0], i["voto"]) for itens in meus.values() for i in itens)
    return {"grupos": grupos, "contagem": contagem, "registrados": sum(contagem.values())}


def dias_de_trabalho(conn, ano: int, fim: date) -> dict:
    sessoes = {r["ano"]: dict(r) for r in conn.execute("SELECT * FROM dias_sessao WHERE casa = 'camara'")}
    return {
        "anterior": {"ano": ano - 1, "trabalhador": calendario.dias_trabalhados(ano - 1),
                     "camara": sessoes.get(ano - 1)},
        "atual": {"ano": ano, "trabalhador": calendario.dias_trabalhados(ano, fim), "camara": sessoes.get(ano)},
        "fontes": calendario.FONTES,
    }


# --- Rankings ----------------------------------------------------------------------
MINIMO_VOTOS = 100  # só entra nos rankings de votos Sim e Não quem votou ao menos isso


def montar_rankings(conn, dep, custos, parlamentares, top=10) -> dict:
    """Mesmo critério para todos; os deputados listados são dos partidos acompanhados."""
    deputados = [p for p in parlamentares if p["casa"] == "camara"]
    senadores = [p for p in parlamentares if p["casa"] == "senado"]
    nome = lambda p: senado.normalizar_nome(p["nome"])

    grupos = defaultdict(list)
    for pid, c in custos.items():
        if pid in dep:
            grupos[dep[pid]["partido"]].append(c["total"])
    partidos = sorted(({"sigla": s, "nome": config.PARTIDOS_MONITORADOS.get(s, s), "media": sum(v) / len(v),
                        "n": len(v), "acompanhado": s in config.PARTIDOS_MONITORADOS} for s, v in grupos.items()),
                      key=lambda x: -x["media"])

    com_custo = [p for p in deputados if p.get("custo")]
    mais_custo = sorted(com_custo, key=lambda p: -p["custo"]["total"])[:top]

    def ausencias(categoria):
        lista = [p for p in deputados if p.get("presenca") and p["presenca"]["contagem"][categoria] > 0]
        lista.sort(key=lambda p: (-p["presenca"]["contagem"][categoria], nome(p)))
        saida = []
        for p in lista[:top]:
            motivos = Counter(d["status"] for d in p["presenca"]["dias"] if d["categoria"] == categoria)
            saida.append({"p": p, "dias": p["presenca"]["contagem"][categoria], "sessoes": p["presenca"]["total"],
                          "motivos": motivos.most_common()})
        return saida

    producao = dict(conn.execute("SELECT parlamentar_id, projetos FROM producao"))
    com_producao = [p for p in deputados if p["id"] in producao]
    menos_projetos = sorted(com_producao, key=lambda p: (producao[p["id"]], nome(p)))[:top]
    todos_proj = [v for k, v in producao.items() if k in dep]

    resumo = {r[0]: r for r in conn.execute(
        "SELECT parlamentar_id, sim, nao, outros, votacoes_total FROM resumo_votos WHERE casa = 'camara'")}
    elegiveis = [p for p in deputados if p["id"] in resumo and resumo[p["id"]][1] + resumo[p["id"]][2] >= MINIMO_VOTOS]
    pct_nao = lambda pid: resumo[pid][2] / (resumo[pid][1] + resumo[pid][2])
    mais_nao = sorted(elegiveis, key=lambda p: (-pct_nao(p["id"]), nome(p)))[:top]
    mais_sim = sorted(elegiveis, key=lambda p: (pct_nao(p["id"]), nome(p)))[:top]
    sim_total = sum(r[1] for k, r in resumo.items() if k in dep)
    nao_total = sum(r[2] for k, r in resumo.items() if k in dep)

    return {
        "partidos": partidos,
        "mais_custo": mais_custo,
        "senado_cota": sorted(senadores, key=lambda p: -(p.get("ceaps_media") or 0))[:top],
        "sem_justificativa": ausencias("ausencia_nao_justificada"),
        "justificadas": ausencias("ausencia_justificada"),
        "menos_projetos": [{"p": p, "projetos": producao[p["id"]]} for p in menos_projetos],
        "sem_projeto": sum(1 for p in com_producao if producao[p["id"]] == 0),
        "media_projetos": sum(todos_proj) / len(todos_proj) if todos_proj else None,
        "mais_nao": [{"p": p, "pct": pct_nao(p["id"]), "nao": resumo[p["id"]][2],
                      "votos": resumo[p["id"]][1] + resumo[p["id"]][2]} for p in mais_nao],
        "mais_sim": [{"p": p, "pct": 1 - pct_nao(p["id"]), "sim": resumo[p["id"]][1],
                      "votos": resumo[p["id"]][1] + resumo[p["id"]][2]} for p in mais_sim],
        "media_nao": nao_total / (sim_total + nao_total) if sim_total + nao_total else None,
        "media_sim": sim_total / (sim_total + nao_total) if sim_total + nao_total else None,
        "minimo_votos": MINIMO_VOTOS,
        "tipos_projeto": "PL, PLP, PDL e PRC",
    }


# --- Votos no Plenário (página "Como votou") ----------------------------------------

TIPOS_VOTACAO = {
    "principal": ("Texto principal", "o projeto, a medida provisória ou a PEC"),
    "trecho": ("Mudança no texto", "emenda, destaque ou parte separada do texto"),
    "urgencia": ("Urgência", "pedido para votar o projeto mais rápido"),
    "pedido": ("Pedido de andamento", "adiar, retirar de pauta ou mudar a ordem da votação"),
}


def sem_placar(descricao: str) -> str:
    """A Câmara repete o placar no fim da descrição; o site mostra o placar à parte."""
    return re.sub(r"\s*Sim:\s*\d+.*$", "", descricao or "", flags=re.I | re.S).strip()


def tipo_votacao(descricao: str) -> str:
    """O que foi votado, pela descrição oficial: texto principal, mudança no texto,
    urgência ou pedido de andamento."""
    d = sem_placar(descricao).lower()
    d = re.sub(r"proposta de emenda à constituição|(sub)?emenda (aglutinativa )?substitutiva( global)?|ressalvad[oa]s? (os |o |as |a )?destaques?",
               "", d)
    if "urgência" in d:
        return "urgencia"
    if re.search(r"requerimento|preferência|recurso", d):
        return "pedido"
    if re.search(r"emenda|destaque|texto|dispositivo", d):
        return "trecho"
    return "principal"


def votos_plenario(conn, pessoas) -> tuple:
    """(índice das votações, {slug: votos}) para a página "Como votou".

    O índice traz cada votação nominal do Plenário desde 2023 uma vez só; o arquivo de
    cada deputado guarda só a posição da votação no índice e o voto.
    """
    placar = defaultdict(Counter)
    for vid, voto, n in conn.execute("SELECT votacao_id, voto, COUNT(*) FROM plenario_voto GROUP BY 1, 2"):
        placar[vid][voto] = n
    proposicoes, pos_prop = [], {}
    for pid, titulo, ementa in conn.execute("SELECT id, titulo, ementa FROM plenario_proposicao"):
        pos_prop[pid] = len(proposicoes)
        proposicoes.append([titulo or f"Proposição {pid}", ementa or "", trabalho.URL_PROPOSICAO_CAMARA.format(id=pid)])
    votacoes, pos = [], {}
    for v in conn.execute("SELECT * FROM plenario_votacao ORDER BY data DESC, id DESC"):
        pos[v["id"]] = len(votacoes)
        votacoes.append([v["data"], sem_placar(v["descricao"]), v["aprovada"], tipo_votacao(v["descricao"]),
                         pos_prop.get(v["proposicao_id"]), v["url_fonte"],
                         placar[v["id"]]["Sim"], placar[v["id"]]["Não"]])
    indice = {"tipos": {k: list(t) for k, t in TIPOS_VOTACAO.items()},
              "proposicoes": proposicoes, "votacoes": votacoes}

    por_pessoa = {}
    deputados = {p["id"]: p for p in pessoas if p["casa"] == "camara"}
    linhas = defaultdict(list)
    for vid, pid, voto, partido in conn.execute("SELECT * FROM plenario_voto"):
        if pid in deputados:
            linhas[pid].append((pos[vid], voto, partido))
    for pid, p in deputados.items():
        votos = sorted(linhas.get(pid, []))
        por_pessoa[p["slug"]] = {
            "votos": [[i, "S" if voto == "Sim" else "N" if voto == "Não" else voto] for i, voto, _ in votos],
            # partido na data do voto, só quando era outro
            "partidos": {str(i): partido for i, _, partido in votos if partido and partido != p["partido"]},
        }
    return indice, por_pessoa


# --- Montagem do site ------------------------------------------------------------

def montar(conn, sabado: date) -> dict:
    inicio, fim = config.semana_referencia(sabado)
    ano, mes_atual = fim.year, fim.month
    refs = carregar_referencias()
    partidos = metricas.partidos_na_data(conn, sabado.isoformat())
    dep = metricas.pessoas_da_casa(conn, "camara", partidos)
    sen = metricas.pessoas_da_casa(conn, "senado", partidos)

    recursos = recursos_por_deputado(conn, ano)
    presenca = presenca_por_parlamentar(conn, ano)
    patrimonio = patrimonio_por_parlamentar(conn)
    part_sen = participacao_senado(conn, ano)
    ceaps = ceaps_mensal(conn, ano)
    votos_cam = votos_da_semana(conn, "camara", inicio.isoformat(), fim.isoformat())
    votos_sen = votos_da_semana(conn, "senado", inicio.isoformat(), fim.isoformat())

    custos = {pid: custo_mensal_deputado(recursos[pid], mes_atual) for pid in dep if pid in recursos}
    media_camara = media_partes(list(custos.values()))
    atualizado_camara = Counter(
        r["atualizado_fonte"] for itens in recursos.values() for r in itens.values()
        if r["atualizado_fonte"]).most_common(1)
    mes_corte = max(1, mes_atual - JANELA_MESES)

    def pct_presenca_grupo(pids):
        c = Counter()
        for pid in pids:
            c.update(presenca.get(pid, {}).get("contagem", {}))
        total = sum(c.values())
        return {"contagem": c, "total": total,
                "pct_presente": c["presente"] / total if total else None,
                "pct_nao_justificada": c["ausencia_nao_justificada"] / total if total else None}

    def pct_votou_grupo(pids):
        c = Counter()
        for pid in pids:
            c.update(part_sen.get(pid, {}).get("contagem", {}))
        reg = sum(c[k] for k in metricas.CATEGORIAS_SENADO)
        return {"contagem": c, "registros": reg, "pct_votou": c["votou"] / reg if reg else None}

    def ceaps_media_mensal(pid):
        meses = [v for m, v in ceaps.get(pid, {}).items() if m <= mes_corte]
        return sum(meses) / mes_corte if mes_corte else 0.0

    def patrimonio_medio(pids):
        vals = [patrimonio[p]["ultima"]["total"] for p in pids if patrimonio.get(p, {}).get("ultima")]
        return {"media": sum(vals) / len(vals) if vals else None, "n": len(vals),
                "mediana": sorted(vals)[len(vals) // 2] if vals else None}

    # Parlamentares acompanhados
    parlamentares = []
    for casa, pessoas in (("camara", dep), ("senado", sen)):
        for pid, p in pessoas.items():
            if p["partido"] not in config.PARTIDOS_MONITORADOS:
                continue
            item = dict(p)
            item["casa"] = casa
            item["cargo"] = "Deputado(a) federal" if casa == "camara" else "Senador(a)"
            item["slug"] = pid.replace(":", "-")
            item["patrimonio"] = patrimonio.get(pid)
            if casa == "camara":
                item["custo"] = custos.get(pid)
                item["presenca"] = presenca.get(pid)
                item["recursos"] = recursos.get(pid, {})
                item["votos"] = [{**v, "voto": v["votos"].get(pid)} for v in votos_cam]
            else:
                serie = ceaps.get(pid, {})
                item["ceaps_serie"] = serie
                item["ceaps_ano"] = sum(serie.values())
                item["ceaps_media"] = ceaps_media_mensal(pid)
                item["participacao"] = part_sen.get(pid)
                item["votos"] = [{**v, "voto": v["votos"].get(pid)} for v in votos_sen]
            parlamentares.append(item)
    parlamentares.sort(key=lambda x: senado.normalizar_nome(x["nome"]))
    pauta = pauta_trabalho(conn, [s for s in config.PARTIDOS_MONITORADOS])
    for item in parlamentares:
        item["trabalho"] = votos_trabalho_da_pessoa(pauta, item["id"])

    # Partidos
    partidos_info = []
    for sigla, nome in config.PARTIDOS_MONITORADOS.items():
        deps = [pid for pid, p in dep.items() if p["partido"] == sigla]
        sens = [pid for pid, p in sen.items() if p["partido"] == sigla]
        if not deps and not sens:
            continue
        custos_partido = [custos[p] for p in deps if p in custos]
        partidos_info.append({
            "sigla": sigla, "nome": nome,
            "deputados": len(deps), "senadores": len(sens),
            "custo_medio": media_partes(custos_partido) if custos_partido else None,
            "presenca": pct_presenca_grupo(deps),
            "votacao_senado": pct_votou_grupo(sens),
            "ceaps_media": (sum(ceaps_media_mensal(p) for p in sens) / len(sens)) if sens else None,
            "patrimonio": patrimonio_medio(deps + sens),
            "membros": [x for x in parlamentares if x["partido"] == sigla],
        })

    return {
        "sabado": sabado, "inicio": inicio, "fim": fim, "ano": ano, "mes_atual": mes_atual,
        "mes_corte": mes_corte, "meses": MESES,
        "refs": refs,
        "errata": carregar_errata(),
        "beneficios": carregar_beneficios(),
        "pauta": pauta,
        "rankings": montar_rankings(conn, dep, custos, parlamentares),
        "dias": dias_de_trabalho(conn, ano, fim),
        "partes_custo": PARTES_CUSTO,
        "parlamentares": parlamentares,
        "partidos": partidos_info,
        "camara": {
            "media_custo": media_camara,
            "presenca": pct_presenca_grupo(list(dep)),
            "total": len(dep),
            "atualizado": atualizado_camara[0][0] if atualizado_camara else None,
            "patrimonio": patrimonio_medio(list(dep)),
        },
        "senado": {
            "votacao": pct_votou_grupo(list(sen)),
            "ceaps_media": sum(ceaps_media_mensal(p) for p in sen) / len(sen) if sen else None,
            "total": len(sen),
            "patrimonio": patrimonio_medio(list(sen)),
        },
    }
