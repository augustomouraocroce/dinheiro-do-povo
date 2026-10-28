"""Dados extras para os rankings: projetos apresentados e resumo de votos no Plenário.

- Projetos: PL, PLP, PDL e PRC em que o deputado é autor ou coautor, desde o início
  do mandato. PEC fica de fora: precisa de 171 assinaturas, e assinar não é ser autor.
- Votos: cada voto nominal do Plenário desde o início do mandato, com o projeto votado,
  e o total de Sim, Não e outros (arquivos anuais de votações da Câmara).
"""
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from dp import config, http, trabalho

TIPOS_PROJETO = ("PL", "PLP", "PDL", "PRC")
INICIO_MANDATO = "2023-02-01"


def contar_projetos(dep_id) -> int:
    """Total de projetos (autor ou coautor) pela API, sem baixar todos: lê a última página."""
    params = {"idDeputadoAutor": dep_id, "siglaTipo": list(TIPOS_PROJETO),
              "dataApresentacaoInicio": INICIO_MANDATO, "itens": 100}
    dados = http.get_json(f"{config.CAMARA_API}/proposicoes", params)
    ultimo = next((l["href"] for l in dados.get("links", []) if l["rel"] == "last"), None)
    paginas = int(re.search(r"pagina=(\d+)", ultimo).group(1)) if ultimo and "pagina=" in ultimo else 1
    if paginas == 1:
        return len(dados["dados"])
    return (paginas - 1) * 100 + len(http.get_json(ultimo)["dados"])


def coletar_projetos(conn, deputados) -> dict:
    hoje = date.today().isoformat()
    falhas = []

    def um(dep):
        try:
            return dep["id"], contar_projetos(dep["id"]), None
        except Exception as erro:
            return dep["id"], None, str(erro)[:120]

    with ThreadPoolExecutor(max_workers=4) as ex:
        for dep_id, n, erro in ex.map(um, deputados):
            if erro:
                falhas.append({"id": dep_id, "erro": erro})
                continue
            conn.execute("INSERT OR REPLACE INTO producao VALUES (?, ?, ?, ?)",
                         (f"camara:{dep_id}", INICIO_MANDATO, n, hoje))
    conn.commit()
    return {"deputados": len(deputados) - len(falhas), "falhas": falhas}


def proposicao_principal(vid: str, props: list):
    """O projeto em votação. O código da votação começa pelo id da proposição votada, mas
    nos pedidos de urgência esse id é o do requerimento: aí vale o projeto ligado a ele."""
    prefixo = vid.split("-")[0]
    ordem = sorted(props, key=lambda p: p["proposicao_id"] != prefixo)
    return next((p for p in ordem if p.get("proposicao_siglaTipo") != "REQ"), ordem[0] if ordem else None)


def coletar_votos_plenario(conn, anos) -> dict:
    """Guarda cada voto nominal do Plenário com o projeto votado e soma Sim / Não / outros
    por deputado."""
    atual = date.today().year
    plenario, props, votos = {}, defaultdict(list), []
    for ano in anos:
        for r in trabalho._ler(trabalho.baixar_arquivo_ano("votacoes", ano, atual)):
            if r["siglaOrgao"] == "PLEN":
                plenario[r["id"]] = r
        for r in trabalho._ler(trabalho.baixar_arquivo_ano("votacoesVotos", ano, atual)):
            if r["idVotacao"] in plenario:
                votos.append((f"camara:{r['idVotacao']}", f"camara:{r['deputado_id']}", r["voto"],
                              r["deputado_siglaPartido"] or None))
        for r in trabalho._ler(trabalho.baixar_arquivo_ano("votacoesProposicoes", ano, atual)):
            if r["idVotacao"] in plenario:
                props[r["idVotacao"]].append(r)

    nominais = {v[0].split(":", 1)[1] for v in votos}
    votacoes, proposicoes = [], {}
    for vid in nominais:
        v, p = plenario[vid], proposicao_principal(vid, props[vid])
        if p:
            proposicoes[p["proposicao_id"]] = (p["proposicao_id"], p["proposicao_titulo"], p["proposicao_ementa"])
        documento = v.get("ultimaApresentacaoProposicao_idProposicao") or ""
        votacoes.append((f"camara:{vid}", v["data"], v["descricao"],
                         int(v["aprovacao"]) if v["aprovacao"] not in ("", None) else None,
                         p["proposicao_id"] if p else None, v["uri"], documento if documento not in ("", "0") else None,
                         (v.get("ultimaAberturaVotacao_descricao") or "").strip() or None))

    contagem = defaultdict(Counter)
    for _, dep, voto, _ in votos:
        contagem[dep]["sim" if voto == "Sim" else "nao" if voto == "Não" else "outros"] += 1

    for tabela in ("plenario_voto", "plenario_votacao", "plenario_proposicao"):
        conn.execute(f"DELETE FROM {tabela}")
    conn.executemany("""INSERT INTO plenario_votacao
                        (id, data, descricao, aprovada, proposicao_id, url_fonte, documento_id, abertura)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", votacoes)
    conn.executemany("INSERT INTO plenario_proposicao VALUES (?, ?, ?)", proposicoes.values())
    conn.executemany("INSERT OR REPLACE INTO plenario_voto VALUES (?, ?, ?, ?)", votos)
    conn.execute("DELETE FROM resumo_votos WHERE casa = 'camara'")
    conn.executemany("INSERT INTO resumo_votos VALUES (?, 'camara', ?, ?, ?, ?, ?)",
                     [(dep, INICIO_MANDATO, c["sim"], c["nao"], c["outros"], len(nominais))
                      for dep, c in contagem.items()])
    conn.commit()
    return {"votacoes_nominais": len(nominais), "votos": len(votos), "proposicoes": len(proposicoes),
            "deputados": len(contagem)}
