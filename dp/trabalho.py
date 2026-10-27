"""Votações sobre trabalho e renda (Câmara e Senado, mandato atual).

A regra de seleção está em dp/trabalho.json e é publicada no site. Não
classificamos votos como a favor ou contra ninguém: mostramos a pergunta
votada, o resultado e o voto de cada parlamentar.
"""
import csv
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from dp import config, http

REGRAS = config.ROOT / "dp" / "trabalho.json"
URL_ARQUIVO = "https://dadosabertos.camara.leg.br/arquivos/{tipo}/csv/{tipo}-{ano}.csv"
URL_PROPOSICAO_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id}"


def carregar_regras() -> dict:
    return json.loads(REGRAS.read_text(encoding="utf-8"))


def motivo(texto: str, temas: list, titulo: str, regras: dict):
    """Por que a proposição entra na lista; None se não entra."""
    for inc in regras["incluidas"]:
        if inc["titulo"] == titulo:
            return inc["motivo"]
    for cod in temas or []:
        if str(cod) in regras["temas_camara"]:
            return f"Tema oficial da Câmara: {regras['temas_camara'][str(cod)]}."
    baixo = texto.lower()
    for palavra in regras["palavras"]:
        if re.search(r"(?<!\w)" + re.escape(palavra.lower()), baixo):
            return f"O texto cita “{palavra}”."
    return None


# --- Câmara -------------------------------------------------------------------------

def baixar_arquivo_ano(tipo: str, ano: int, atual: int):
    """Arquivo anual de votações. Anos fechados reaproveitam a cópia local mais recente."""
    copias = sorted(config.RAW_DIR.glob(f"*/camara_{tipo}_{ano}.csv"))
    if copias and ano < atual:
        return copias[-1]
    return http.baixar(URL_ARQUIVO.format(tipo=tipo, ano=ano), f"camara_{tipo}_{ano}.csv")


def _ler(caminho):
    with open(caminho, encoding="utf-8-sig") as f:
        yield from csv.DictReader(f, delimiter=";")


def temas_camara(conn, ids):
    """{id da proposição: [códigos de tema]}, consultando a API só para os que faltam no banco."""
    conhecidos = defaultdict(list)
    vistos = set()
    for pid, cod in conn.execute("SELECT proposicao_id, cod_tema FROM proposicao_tema"):
        vistos.add(pid)
        if cod is not None:
            conhecidos[pid].append(cod)
    faltam = sorted(set(ids) - vistos)

    def buscar(i):
        dados = http.get_json(f"{config.CAMARA_API}/proposicoes/{i}/temas")["dados"]
        return i, [int(t["codTema"]) for t in dados]

    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, cods in ex.map(buscar, faltam):
            linhas = [(i, c) for c in cods] or [(i, None)]
            conn.executemany("INSERT OR IGNORE INTO proposicao_tema VALUES (?, ?)", linhas)
            conhecidos[i].extend(cods)
    conn.commit()
    return conhecidos, len(faltam)


def coletar_camara(conn, anos, regras, atual):
    votacoes, nominais, props = {}, defaultdict(dict), defaultdict(list)
    for ano in anos:
        for r in _ler(baixar_arquivo_ano("votacoes", ano, atual)):
            if r["siglaOrgao"] == "PLEN":
                votacoes[r["id"]] = r
        for r in _ler(baixar_arquivo_ano("votacoesVotos", ano, atual)):
            if r["idVotacao"] in votacoes:
                nominais[r["idVotacao"]][r["deputado_id"]] = (r["voto"], r["deputado_siglaPartido"])
        for r in _ler(baixar_arquivo_ano("votacoesProposicoes", ano, atual)):
            if r["idVotacao"] in votacoes:
                props[r["idVotacao"]].append(r)

    # A proposição principal de cada votação: o prefixo do código da votação.
    titulos = {}
    for lista in props.values():
        for p in lista:
            titulos[p["proposicao_id"]] = (p["proposicao_titulo"], p["proposicao_ementa"])
    ids = {v.split("-")[0] for v in nominais} | {p["proposicao_id"] for v in nominais for p in props.get(v, [])}
    temas, consultados = temas_camara(conn, ids)

    escolhidas = 0
    for vid, votos in nominais.items():
        v = votacoes[vid]
        candidatos = [vid.split("-")[0]] + [p["proposicao_id"] for p in props.get(vid, [])]
        for pid in dict.fromkeys(candidatos):
            titulo, ementa = titulos.get(pid, ("", ""))
            m = motivo(f"{v['descricao']} {titulo} {ementa}", temas.get(pid), titulo, regras)
            if m:
                break
        if not m:
            continue
        escolhidas += 1
        id_db = f"camara:{vid}"
        conn.execute(
            """INSERT OR REPLACE INTO votacao (id, casa, data, descricao, aprovada, sessao_id, url_fonte)
               VALUES (?, 'camara', ?, ?, ?, ?, ?)""",
            (id_db, v["data"], v["descricao"], int(v["aprovacao"]) if v["aprovacao"] not in ("", None) else None,
             f"camara:{v['idEvento']}" if v["idEvento"] not in ("", "0") else None, v["uri"]))
        conn.executemany("INSERT OR REPLACE INTO voto (votacao_id, parlamentar_id, voto, partido) VALUES (?, ?, ?, ?)",
                         [(id_db, f"camara:{dep}", voto, partido) for dep, (voto, partido) in votos.items()])
        conn.execute(
            """INSERT OR REPLACE INTO pauta_trabalho (votacao_id, casa, proposicao, ementa, url_proposicao, motivo)
               VALUES (?, 'camara', ?, ?, ?, ?)""",
            (id_db, titulo or f"Proposição {pid}", ementa, URL_PROPOSICAO_CAMARA.format(id=pid), m))
    conn.commit()
    return {"votacoes_nominais_plenario": len(nominais), "escolhidas": escolhidas,
            "temas_consultados": consultados}


# --- Senado -------------------------------------------------------------------------

def coletar_senado(conn, anos, regras):
    from datetime import date, timedelta
    from dp.fontes import senado
    escolhidas = total = 0
    # Uma consulta por mês: períodos maiores passam do limite de 10 s do servidor (HTTP 503).
    meses = [(date(a, m, 1), min(date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1), date.today()))
             for a in anos for m in range(1, 13) if date(a, m, 1) <= date.today()]
    votacoes = [v for de, ate in meses for v in senado.votacoes(de, ate)]
    for v in votacoes:
        total += 1
        titulo = v.get("identificacao") or ""
        texto = f"{v.get('descricaoVotacao') or ''} {titulo} {v.get('ementa') or ''}"
        m = motivo(texto, None, titulo, regras)
        if not m:
            continue
        escolhidas += 1
        vid = f"senado:{v['codigoSessaoVotacao']}"
        url = (f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{v['codigoMateria']}"
               if v.get("codigoMateria") else None)
        conn.execute(
            """INSERT OR REPLACE INTO votacao (id, casa, data, descricao, aprovada, sessao_id, url_fonte)
               VALUES (?, 'senado', ?, ?, ?, ?, ?)""",
            (vid, v["dataSessao"], f"{titulo} {v.get('descricaoVotacao') or ''}".strip(),
             {"A": 1, "R": 0}.get(v.get("resultadoVotacao")), f"senado:{v['codigoSessao']}", url))
        conn.executemany("INSERT OR REPLACE INTO voto (votacao_id, parlamentar_id, voto, partido) VALUES (?, ?, ?, ?)",
                         [(vid, senado.pid(x["codigoParlamentar"]), x["siglaVotoParlamentar"], x.get("siglaPartidoParlamentar"))
                          for x in v["votos"]])
        conn.execute(
            """INSERT OR REPLACE INTO pauta_trabalho (votacao_id, casa, proposicao, ementa, url_proposicao, motivo)
               VALUES (?, 'senado', ?, ?, ?, ?)""",
            (vid, titulo, v.get("ementa") or "", url, m))
    conn.commit()
    return {"votacoes_nominais_plenario": total, "escolhidas": escolhidas}
