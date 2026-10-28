"""Dados extras para os rankings: projetos apresentados e resumo de votos no Plenário.

- Projetos: PL, PLP, PDL e PRC em que o deputado é autor ou coautor, desde o início
  do mandato. PEC fica de fora: precisa de 171 assinaturas, e assinar não é ser autor.
- Votos: Sim, Não e outros em todas as votações nominais do Plenário desde o início
  do mandato (arquivos anuais de votações da Câmara).
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


def coletar_resumo_votos(conn, anos) -> dict:
    """Soma Sim / Não / outros por deputado nas votações nominais do Plenário."""
    atual = date.today().year
    plenario = set()
    for ano in anos:
        for r in trabalho._ler(trabalho.baixar_arquivo_ano("votacoes", ano, atual)):
            if r["siglaOrgao"] == "PLEN":
                plenario.add(r["id"])
    contagem = defaultdict(Counter)
    votacoes = set()
    for ano in anos:
        for r in trabalho._ler(trabalho.baixar_arquivo_ano("votacoesVotos", ano, atual)):
            if r["idVotacao"] in plenario:
                votacoes.add(r["idVotacao"])
                cat = "sim" if r["voto"] == "Sim" else "nao" if r["voto"] == "Não" else "outros"
                contagem[r["deputado_id"]][cat] += 1
    conn.execute("DELETE FROM resumo_votos WHERE casa = 'camara'")
    conn.executemany("INSERT INTO resumo_votos VALUES (?, 'camara', ?, ?, ?, ?, ?)",
                     [(f"camara:{dep}", INICIO_MANDATO, c["sim"], c["nao"], c["outros"], len(votacoes))
                      for dep, c in contagem.items()])
    conn.commit()
    return {"votacoes_nominais": len(votacoes), "deputados": len(contagem)}
