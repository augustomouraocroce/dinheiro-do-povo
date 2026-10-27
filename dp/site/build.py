"""Gera o site estático em public/.

Uso:
    python -m dp.site.build                      # último sábado
    python -m dp.site.build --semana 2026-10-17
Depois: abra public/index.html, ou sirva com `python -m http.server -d public`.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from dp import config, db, relatorio
from dp.fontes import fotos, senado
from dp.site import dados, graficos

AQUI = Path(__file__).parent
TEMPLATES = AQUI / "templates"
ESTATICOS = AQUI / "static"
SAIDA = config.ROOT / "public"
URL_CEAPS = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"

ROTULO_VOTO = {
    None: "Sem registro", "Artigo 17": "Art. 17", "Votou": "Votou (secreto)",
    "P-NRV": "Presente, não votou", "NCom": "Não compareceu", "AP": "Ausente (atividade)",
    "MIS": "Ausente (missão)", "LS": "Licença saúde", "LP": "Licença particular",
    "LAP": "Licença", "LG": "Licença", "Presidente (art. 51 RISF)": "Presidente",
}


# --- Filtros de formatação ----------------------------------------------------------

def brl_partes(v):
    inteiro, centavos = relatorio.brl(v).replace("R$ ", "").split(",")
    return inteiro, centavos


def qtd(v):
    if v is None:
        return "—"
    if v >= 100:
        return relatorio.num(int(round(v)))
    if v >= 10:
        return f"{v:.0f}"
    s = f"{v:.1f}".replace(".", ",")
    return s[:-2] if s.endswith(",0") else s


def slug(sigla: str) -> str:
    return senado.normalizar_nome(sigla).lower()


def normalizar(t: str) -> str:
    return senado.normalizar_nome(t).lower()


def groupby_mes(dias):
    return [(mes, list(itens)) for mes, itens in groupby(dias, key=lambda d: int(d["data"][5:7]))]


def ambiente() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined,
                      autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)
    env.filters.update(
        brl=relatorio.brl, pct=relatorio.pct, num=relatorio.num, data=relatorio.data_br,
        dia_mes=relatorio.dia_mes, plural=relatorio.plural, brl_partes=brl_partes, qtd=qtd,
        compacto=graficos.brl_compacto, slug=slug, normalizar=normalizar, groupby_mes=groupby_mes,
        rotulo_voto=lambda v: ROTULO_VOTO.get(v, v))
    return env


# --- Gráficos de cada página -------------------------------------------------------

def _linha_minimo(refs):
    return {"rotulo": "1 salário mínimo",
            "partes": [{"chave": "referencia", "nome": "Salário mínimo", "valor": refs["salario_minimo"]["valor"]}],
            "total": refs["salario_minimo"]["valor"]}


def graficos_custo(rotulo, custo, d):
    linhas = [{"rotulo": rotulo, "partes": custo["partes"], "total": custo["total"]}]
    if custo is not d["camara"]["media_custo"]:
        linhas.append({"rotulo": f"Média da Câmara ({d['camara']['total']} deputados)",
                       "partes": d["camara"]["media_custo"]["partes"], "total": d["camara"]["media_custo"]["total"]})
    linhas.append(_linha_minimo(d["refs"]))
    return Markup(graficos.barras_custo(linhas, "Custo médio por mês, por tipo de gasto")), linhas


def grafico_partidos(d, campo, destaque=None):
    linhas = []
    for pt in d["partidos"]:
        if campo == "presenca" and pt["presenca"]["total"]:
            linhas.append({"rotulo": pt["sigla"], "valor": pt["presenca"]["pct_presente"]})
        elif campo == "ausencias" and pt["presenca"]["total"]:
            linhas.append({"rotulo": pt["sigla"], "valor": pt["presenca"]["pct_nao_justificada"]})
        elif campo == "custo" and pt["custo_medio"]:
            linhas.append({"rotulo": pt["sigla"], "valor": pt["custo_medio"]["total"]})
    todos = {"presenca": d["camara"]["presenca"]["pct_presente"],
             "ausencias": d["camara"]["presenca"]["pct_nao_justificada"],
             "custo": d["camara"]["media_custo"]["total"]}[campo]
    linhas.append({"rotulo": "Todos", "valor": todos, "todos": True})
    formato = graficos.brl_compacto if campo == "custo" else relatorio.pct
    return Markup(graficos.barras_comparacao(linhas, f"Comparação por partido: {campo}", formato, destaque))


# --- Arquivos ------------------------------------------------------------------------

def copiar_estaticos(saida: Path, d):
    destino = saida / "static"
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(ESTATICOS, destino)
    indice = [{"tipo": "pessoa", "nome": p["nome"], "partido": p["partido"],
               "partido_nome": config.PARTIDOS_MONITORADOS.get(p["partido"], ""),
               "uf": p["uf"], "cargo": p["cargo"], "url": f"p/{p['slug']}.html",
               "foto": f"fotos/mini/{p['slug']}.jpg"} for p in d["parlamentares"]]
    indice += [{"tipo": "partido", "nome": "", "partido": pt["sigla"], "partido_nome": pt["nome"],
                "uf": "", "cargo": "partido", "url": f"partido/{slug(pt['sigla'])}.html"}
               for pt in d["partidos"]]
    (destino / "busca-indice.js").write_text(
        "window.DP_INDICE = " + json.dumps(indice, ensure_ascii=False) + ";\n", encoding="utf-8")


def copiar_fotos(saida: Path, d):
    pasta, mini = saida / "fotos", saida / "fotos" / "mini"
    mini.mkdir(parents=True, exist_ok=True)
    for p in d["parlamentares"]:
        origem = fotos.baixar(p["id"])
        alvo = pasta / f"{p['slug']}.jpg"
        alvo_mini = mini / f"{p['slug']}.jpg"
        if not alvo.exists() or alvo.stat().st_mtime < origem.stat().st_mtime:
            shutil.copy2(origem, alvo)
        if not alvo_mini.exists() or alvo_mini.stat().st_mtime < origem.stat().st_mtime:
            shutil.copy2(origem, alvo_mini)
            if shutil.which("sips"):
                subprocess.run(["sips", "--resampleWidth", "120", "-s", "formatOptions", "70",
                                str(alvo_mini)], check=True, capture_output=True)
            # a origem continua gravada no JPEG reduzido
            texto = f"Miniatura da foto oficial em {origem.name}"
            alvo_mini.write_bytes(fotos.gravar_origem(alvo_mini.read_bytes(), texto))


def construir(conn, sabado: date, saida: Path = SAIDA):
    d = dados.montar(conn, sabado)
    ctx_semana, _, corpo_semana = relatorio.renderizar(conn, sabado)
    licencas = {k: v for k, v in json.loads((ESTATICOS / "partidos" / "LICENCAS.json").read_text(encoding="utf-8")).items()
                if not k.startswith("_")}
    logos = {sigla: l["arquivo"] for sigla, l in licencas.items()}
    env = ambiente()
    base = {**d, "logos": logos, "licencas": licencas, "semana": ctx_semana,
            "refs_senado_ceaps": URL_CEAPS.format(ano=d["ano"])}

    saida.mkdir(parents=True, exist_ok=True)
    copiar_estaticos(saida, d)
    copiar_fotos(saida, d)

    def escrever(caminho: str, template: str, raiz: str, ativa: str, **extra):
        alvo = saida / caminho
        alvo.parent.mkdir(parents=True, exist_ok=True)
        html = env.get_template(template).render(**base, raiz=raiz, ativa=ativa, **extra)
        alvo.write_text(html, encoding="utf-8")

    g_custo, linhas = graficos_custo("Média por deputado", d["camara"]["media_custo"], d)
    escrever("index.html", "index.html.j2", "", "inicio", grafico_custo=g_custo, linhas_custo=linhas,
             grafico_presenca=grafico_partidos(d, "presenca"),
             grafico_custo_partidos=grafico_partidos(d, "custo"))
    escrever("partidos.html", "partidos.html.j2", "", "partidos")
    escrever("metodologia.html", "metodologia.html.j2", "", "metodologia")
    escrever(f"semana/{sabado.isoformat()}.html", "semana.html.j2", "../", "semana",
             corpo=Markup(corpo_semana))

    for pt in d["partidos"]:
        extra = {}
        if pt["custo_medio"]:
            g, linhas = graficos_custo(f"Média do {pt['sigla']}", pt["custo_medio"], d)
            extra = {"grafico_custo": g, "linhas_custo": linhas,
                     "grafico_presenca": grafico_partidos(d, "presenca", destaque=pt["sigla"]),
                     "grafico_ausencias": grafico_partidos(d, "ausencias", destaque=pt["sigla"])}
        escrever(f"partido/{slug(pt['sigla'])}.html", "partido.html.j2", "../", "partidos", pt=pt, **extra)

    for p in d["parlamentares"]:
        extra = {"grafico_custo": "", "linhas_custo": [], "grafico_cota": "", "grafico_patrimonio": ""}
        if p["casa"] == "camara" and p["custo"]:
            g, linhas = graficos_custo(p["nome"], p["custo"], d)
            extra.update(grafico_custo=g, linhas_custo=linhas, grafico_cota=Markup(graficos.colunas_mensais(
                p["custo"]["cota_serie"], d["mes_corte"], d["meses"], "Cota parlamentar por mês")))
        elif p["casa"] == "senado":
            extra["grafico_cota"] = Markup(graficos.colunas_mensais(
                p["ceaps_serie"], d["mes_corte"], d["meses"], "Cota parlamentar (CEAPS) por mês"))
        if p["patrimonio"] and p["patrimonio"]["declaracoes"]:
            extra["grafico_patrimonio"] = Markup(graficos.colunas_patrimonio(
                p["patrimonio"]["declaracoes"], "Patrimônio declarado ao TSE por eleição"))
        escrever(f"p/{p['slug']}.html", "parlamentar.html.j2", "../", "", p=p, **extra)
    return saida, d


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera o site estático do Dinheiro do Povo")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--db", default=None, help="Caminho alternativo do banco")
    ap.add_argument("--saida", default=str(SAIDA), help="Pasta de saída")
    args = ap.parse_args(argv)
    saida, d = construir(db.conectar(args.db), args.semana, Path(args.saida))
    print(f"{saida}/index.html  ({len(d['parlamentares'])} parlamentares, {len(d['partidos'])} partidos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
