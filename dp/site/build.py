"""Gera o site estático em public/.

Uso:
    python -m dp.site.build                      # último sábado
    python -m dp.site.build --semana 2026-10-17
Depois: abra public/index.html, ou sirva com `python -m http.server -d public`.
"""
import argparse
import json
import re
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


def data_caso(v: str) -> str:
    """Data de um caso: dia/mês/ano, ou mês/ano quando a fonte só dá o mês."""
    if len(v) == 7:
        ano, mes = v.split("-")
        return f"{dados.MESES[int(mes) - 1]}/{ano}"
    return relatorio.data_br(v)


def groupby_mes(dias):
    return [(mes, list(itens)) for mes, itens in groupby(dias, key=lambda d: int(d["data"][5:7]))]


def ambiente() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined,
                      autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)
    env.globals.update(artefato=False, sprite={}, foto_data="")
    env.filters.update(
        brl=relatorio.brl, pct=relatorio.pct, num=relatorio.num, data=relatorio.data_br,
        dia_mes=relatorio.dia_mes, plural=relatorio.plural, brl_partes=brl_partes, qtd=qtd,
        compacto=graficos.brl_compacto, slug=slug, normalizar=normalizar, groupby_mes=groupby_mes,
        rotulo_voto=lambda v: ROTULO_VOTO.get(v, v), cada100=dados.cada_100, data_caso=data_caso,
        explica_voto=dados.explicar_votacao, sem_placar=dados.sem_placar)
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


def escrever_votos(saida: Path, conn, d) -> str:
    """Índice das votações do Plenário e um arquivo pequeno por deputado, lidos pela
    página "Como votou". Devolve a data da votação mais recente."""
    indice, por_pessoa = dados.votos_plenario(conn, d["parlamentares"])
    pasta = saida / "dados" / "votos"
    if pasta.exists():
        shutil.rmtree(pasta)
    pasta.mkdir(parents=True)
    compacto = {"ensure_ascii": False, "separators": (",", ":")}
    (saida / "dados" / "votacoes.json").write_text(json.dumps(indice, **compacto), encoding="utf-8")
    for slug_pessoa, votos in por_pessoa.items():
        (pasta / f"{slug_pessoa}.json").write_text(json.dumps(votos, **compacto), encoding="utf-8")
    return indice["votacoes"][0][0] if indice["votacoes"] else None


def copiar_posts(saida: Path) -> list:
    """As imagens de cada sábado (cards/AAAA-MM-DD) e a legenda, da semana mais recente
    para a mais antiga."""
    from dp.cards import gerar  # importado aqui: os cards também usam este módulo
    semanas = []
    for pasta in sorted(gerar.SAIDA.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"), reverse=True):
        sabado = date.fromisoformat(pasta.name)
        inicio, fim = config.semana_referencia(sabado)
        semana = {"sabado": pasta.name, "inicio": inicio, "fim": fim, "legenda": ""}
        for formato, (largura, altura) in gerar.FORMATOS.items():
            semana[formato] = []
            for png in sorted((pasta / formato).glob("*.png")):
                alvo = saida / "posts" / pasta.name / formato / png.name
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if not alvo.exists() or alvo.stat().st_mtime < png.stat().st_mtime:
                    shutil.copy2(png, alvo)
                semana[formato].append({"url": f"posts/{pasta.name}/{formato}/{png.name}", "largura": largura,
                                        "altura": altura, "arquivo": f"dinheiro-do-povo-{pasta.name}-{formato}-{png.name}"})
        if (pasta / "legenda.txt").exists():
            semana["legenda"] = (pasta / "legenda.txt").read_text(encoding="utf-8")
        if semana["carrossel"] or semana["vertical"]:
            semanas.append(semana)
    return semanas


# --- Versão para artefato do claude.ai ------------------------------------------------
# O artefato aceita no máximo 511 arquivos: as fotos das listas viram um mosaico único,
# a foto do topo de cada parlamentar vai embutida na página e a fonte vem do Google Fonts.

MOSAICO_COLUNAS, MOSAICO_TILE = 20, (90, 120)


def montar_mosaico(saida: Path, parlamentares) -> dict:
    """Junta as fotos num JPEG único e devolve {slug: "x% y%"} para background-position."""
    from PIL import Image
    linhas = -(-len(parlamentares) // MOSAICO_COLUNAS)
    w, h = MOSAICO_TILE
    mosaico = Image.new("RGB", (MOSAICO_COLUNAS * w, linhas * h), (246, 245, 240))
    posicoes = {}
    for n, p in enumerate(parlamentares):
        col, lin = n % MOSAICO_COLUNAS, n // MOSAICO_COLUNAS
        foto = Image.open(fotos.baixar(p["id"])).convert("RGB")
        escala = max(w / foto.width, h / foto.height)  # preenche o quadro e corta o excesso
        nw, nh = round(foto.width * escala), round(foto.height * escala)
        foto = foto.resize((nw, nh)).crop(((nw - w) // 2, 0, (nw - w) // 2 + w, h))
        mosaico.paste(foto, (col * w, lin * h))
        x = 100 * col / (MOSAICO_COLUNAS - 1)
        y = 100 * lin / (linhas - 1) if linhas > 1 else 0
        posicoes[p["slug"]] = f"{x:.4f}% {y:.4f}%"
    (saida / "fotos").mkdir(parents=True, exist_ok=True)
    mosaico.save(saida / "fotos" / "mosaico.jpg", quality=72, optimize=True, progressive=True)
    return posicoes, (MOSAICO_COLUNAS, linhas)


def foto_embutida(pid: str) -> str:
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(fotos.baixar(pid).read_bytes()).decode()


def estaticos_artefato(saida: Path, d, posicoes, grade):
    destino = saida / "static"
    (destino / "partidos" / "png").mkdir(parents=True, exist_ok=True)
    css = (ESTATICOS / "site.css").read_text(encoding="utf-8")
    css = re.sub(r"@font-face\s*\{[^}]*\}\s*", "", css, count=1)  # a fonte vem do Google Fonts
    css += f"\n:root {{ --mosaico-tamanho: {grade[0] * 100}% {grade[1] * 100}%; }}\n"
    (destino / "site.css").write_text(css, encoding="utf-8")
    shutil.copy2(ESTATICOS / "site.js", destino / "site.js")
    for png in (ESTATICOS / "partidos" / "png").glob("*.png"):
        shutil.copy2(png, destino / "partidos" / "png" / png.name)
    indice = [{"tipo": "pessoa", "nome": p["nome"], "partido": p["partido"],
               "partido_nome": config.PARTIDOS_MONITORADOS.get(p["partido"], ""),
               "uf": p["uf"], "cargo": p["cargo"], "url": f"p/{p['slug']}.html",
               "sprite": posicoes[p["slug"]]} for p in d["parlamentares"]]
    indice += [{"tipo": "partido", "nome": "", "partido": pt["sigla"], "partido_nome": pt["nome"],
                "uf": "", "cargo": "partido", "url": f"partido/{slug(pt['sigla'])}.html"}
               for pt in d["partidos"]]
    (destino / "busca-indice.js").write_text(
        "window.DP_INDICE = " + json.dumps(indice, ensure_ascii=False) + ";\n", encoding="utf-8")


def pagina_principal(html: str) -> str:
    """O artefato embrulha a página principal num esqueleto próprio: tira doctype/html/head/body."""
    cabeca = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    corpo = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    cabeca = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*', "", cabeca)
    cabeca = re.sub(r"<title>.*?</title>", "<title>Dinheiro do Povo</title>", cabeca, flags=re.S)
    return ('<meta name="claude:viewport-fit-sides" content="cover">\n' + cabeca.strip()
            + "\n<script>document.documentElement.setAttribute('data-raiz', '');</script>\n" + corpo.strip() + "\n")


def construir(conn, sabado: date, saida: Path = SAIDA, artefato: bool = False):
    d = dados.montar(conn, sabado)
    ctx_semana, _, corpo_semana = relatorio.renderizar(conn, sabado)
    licencas = {k: v for k, v in json.loads((ESTATICOS / "partidos" / "LICENCAS.json").read_text(encoding="utf-8")).items()
                if not k.startswith("_")}
    logos = {sigla: l["arquivo"] for sigla, l in licencas.items()}
    env = ambiente()
    saida.mkdir(parents=True, exist_ok=True)
    if artefato:
        logos = {sigla: f"png/{sigla}.png" for sigla in logos
                 if (ESTATICOS / "partidos" / "png" / f"{sigla}.png").exists()}
        posicoes, grade = montar_mosaico(saida, d["parlamentares"])
        estaticos_artefato(saida, d, posicoes, grade)
        env.globals.update(artefato=True, sprite=posicoes)
    else:
        copiar_estaticos(saida, d)
        copiar_fotos(saida, d)
    base = {**d, "logos": logos, "licencas": licencas, "semana": ctx_semana,
            "refs_senado_ceaps": URL_CEAPS.format(ano=d["ano"])}

    def escrever(caminho: str, template: str, raiz: str, ativa: str, **extra):
        alvo = saida / caminho
        alvo.parent.mkdir(parents=True, exist_ok=True)
        html = env.get_template(template).render(**base, raiz=raiz, ativa=ativa, **extra)
        alvo.write_text(html, encoding="utf-8")

    g_custo, linhas = graficos_custo("Média por deputado", d["camara"]["media_custo"], d)
    escrever("index.html", "index.html.j2", "", "inicio", grafico_custo=g_custo, linhas_custo=linhas)
    escrever("partidos.html", "partidos.html.j2", "", "partidos")
    escrever("trabalho.html", "trabalho.html.j2", "", "trabalho")
    escrever("rankings.html", "rankings.html.j2", "", "rankings")
    votos_deputados = sorted((p for p in d["parlamentares"] if p["casa"] == "camara"),
                             key=lambda p: (p["partido"], normalizar(p["nome"])))
    escrever("votos.html", "votos.html.j2", "", "votos", votos_deputados=votos_deputados,
             tipos_votacao=dados.TIPOS_VOTACAO, votos_ate=escrever_votos(saida, conn, d) or "")
    escrever("posts.html", "posts.html.j2", "", "posts", posts=copiar_posts(saida))
    escrever("processos.html", "processos.html.j2", "", "processos")
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
        if artefato:
            extra["foto_data"] = foto_embutida(p["id"])
        escrever(f"p/{p['slug']}.html", "parlamentar.html.j2", "../", "", p=p, **extra)
    if artefato:
        principal = saida / "index.html"
        principal.write_text(pagina_principal(principal.read_text(encoding="utf-8")), encoding="utf-8")
    return saida, d


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera o site estático do Dinheiro do Povo")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--db", default=None, help="Caminho alternativo do banco")
    ap.add_argument("--saida", default=None, help="Pasta de saída (padrão: public/ ou artefato/)")
    ap.add_argument("--artefato", action="store_true",
                    help="Gera a versão para artefato do claude.ai (menos arquivos, fonte do Google Fonts)")
    args = ap.parse_args(argv)
    saida = Path(args.saida) if args.saida else (config.ROOT / "artefato" if args.artefato else SAIDA)
    saida, d = construir(db.conectar(args.db), args.semana, saida, artefato=args.artefato)
    print(f"{saida}/index.html  ({len(d['parlamentares'])} parlamentares, {len(d['partidos'])} partidos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
