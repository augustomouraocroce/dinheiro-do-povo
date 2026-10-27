"""Dados de cada página do site, montados a partir do banco e das referências.

Regras de cálculo (repetidas na página de metodologia):
- Custo médio por mês de um deputado = salário bruto + média mensal da cota +
  média mensal da verba de gabinete + auxílio-moradia do ano ÷ meses decorridos.
- As médias da cota e da verba usam só os meses fora da janela de 90 dias em
  que notas ainda podem entrar (ex.: em outubro, janeiro a julho).
"""
import json
from collections import Counter, defaultdict
from datetime import date

from dp import config, metricas
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
