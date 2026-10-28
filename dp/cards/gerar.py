"""Cards do post de sábado: carrossel 1080×1350 (Instagram, Kwai) e vertical 1080×1920
(Stories, TikTok, Reels), no mesmo visual do site. Cada card é uma página HTML
fotografada pelo Chrome sem interface; nenhuma imagem é gerada por IA.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from dp import config, db, metricas
from dp.site import build as site_build
from dp.site import dados

AQUI = Path(__file__).parent
TEMPLATES = AQUI / "templates"
SAIDA = config.ROOT / "cards"
SITE_URL = "dinheiro-do-povo.netlify.app"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
FORMATOS = {"carrossel": (1080, 1350), "vertical": (1080, 1920)}
NOMES_POR_CARD = 8
VOTACOES_POR_CARD = 2
MAX_CARDS = 10


def _sem_placar(descricao: str) -> str:
    """A Câmara repete o placar no fim da descrição; o card mostra o placar à parte."""
    return re.sub(r"\s*Sim:\s*\d+.*$", "", descricao or "", flags=re.I | re.S).strip()


def votacoes_da_semana(semana) -> list:
    saida = []
    for v in semana["camara"]["votacoes"]:
        sim, nao = v["placar"].get("Sim", 0), v["placar"].get("Não", 0)
        saida.append({"casa": "Câmara", "data": v["data"], "descricao": _sem_placar(v["descricao"]),
                      "aprovada": v["aprovada"], "sim": sim, "nao": nao,
                      "bancadas": [{"partido": b["partido"], "sim": b["sim"], "nao": b["nao"]} for b in v["bancadas"]]})
    for v in semana["senado"]["votacoes"]["votacoes"]:
        sim, nao = v["placar"].get("Sim", 0), v["placar"].get("Não", 0)
        saida.append({"casa": "Senado", "data": v["data"], "descricao": _sem_placar(v["descricao"]),
                      "aprovada": v["aprovada"], "sim": sim, "nao": nao,
                      "bancadas": [{"partido": b["partido"], "sim": b["sim"], "nao": b["nao"]} for b in v["bancadas"]]})
    return saida


def contexto(conn, sabado: date) -> dict:
    d = dados.montar(conn, sabado)
    semana = metricas.montar_relatorio(conn, sabado)
    return {**d, "semana": semana, "site_url": SITE_URL, "votacoes_semana": votacoes_da_semana(semana)}


def _partes(lista, tamanho):
    return [lista[i:i + tamanho] for i in range(0, len(lista), tamanho)] or [[]]


def roteiro_carrossel(ctx) -> list:
    """[(nome do arquivo, template, variáveis extras)] na ordem do carrossel."""
    ps = ctx["semana"]["camara"]["presenca_semana"]
    cards = [("capa", "capa.html.j2", {}), ("custo", "custo.html.j2", {}), ("compra", "compra.html.j2", {}),
             ("alem", "alem.html.j2", {}), ("presenca", "presenca.html.j2", {})]
    ausentes = ps["ausencias_nao_justificadas"]
    if ausentes:
        blocos = _partes(ausentes, NOMES_POR_CARD)
        for i, bloco in enumerate(blocos, 1):
            cards.append((f"faltas-{i}", "faltas.html.j2", {"nomes": bloco, "parte": i, "partes": len(blocos)}))
    votos = ctx["votacoes_semana"]
    # Uma imagem de votações; o resto fica no site.
    cards.append(("votacoes", "votacoes.html.j2",
                  {"votos": votos[:VOTACOES_POR_CARD], "restantes": max(0, len(votos) - VOTACOES_POR_CARD)}))
    cards.append(("dias", "dias.html.j2", {}))
    if ctx["semana"]["camara"]["despesas_novas"]["disponivel"]:
        cards.append(("despesas", "despesas.html.j2", {}))
    cards.append(("fim", "fim.html.j2", {}))
    # O carrossel tem no máximo 10 imagens: os nomes que não couberem ficam no site.
    while len(cards) > MAX_CARDS:
        faltas = [c for c in cards if c[0].startswith("faltas-")]
        if len(faltas) > 1:
            ultimo = faltas[-1]
            cards.remove(ultimo)
            faltas[-2][2]["restantes"] = (faltas[-2][2].get("restantes", 0) + len(ultimo[2]["nomes"])
                                          + ultimo[2].get("restantes", 0))
            for c in faltas[:-1]:
                c[2]["partes"] = len(faltas) - 1
        elif any(c[0] == "despesas" for c in cards):
            cards = [c for c in cards if c[0] != "despesas"]
        else:
            break
    return cards


def roteiro_vertical(ctx) -> list:
    ausentes = ctx["semana"]["camara"]["presenca_semana"]["ausencias_nao_justificadas"]
    return [("custo", "v-custo.html.j2", {}),
            ("presenca", "presenca.html.j2", {}),
            *([("faltas", "faltas.html.j2", {"nomes": ausentes[:NOMES_POR_CARD + 6], "parte": 1, "partes": 1,
                                             "restantes": max(0, len(ausentes) - NOMES_POR_CARD - 6)})]
              if ausentes else []),
            ("dias", "dias.html.j2", {})]


def ambiente() -> Environment:
    env = site_build.ambiente()
    env.loader = FileSystemLoader([TEMPLATES, site_build.TEMPLATES])
    env.undefined = StrictUndefined
    env.autoescape = lambda nome: not (nome or "").endswith(".txt.j2")  # legenda é texto puro
    return env


def fotografar(html: Path, png: Path, largura: int, altura: int, perfil: str):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    f"--user-data-dir={perfil}", "--force-device-scale-factor=1",
                    f"--window-size={largura},{altura}", "--virtual-time-budget=4000",
                    f"--screenshot={png}", html.as_uri()],
                   check=True, capture_output=True, timeout=120)


def gerar(conn, sabado: date, saida: Path = SAIDA) -> Path:
    ctx = contexto(conn, sabado)
    env = ambiente()
    pasta = saida / sabado.isoformat()
    html_dir = pasta / "html"
    if html_dir.exists():
        shutil.rmtree(html_dir)
    html_dir.mkdir(parents=True)
    shutil.copy2(AQUI / "static" / "cards.css", html_dir / "cards.css")
    shutil.copy2(site_build.ESTATICOS / "fontes" / "archivo-var.woff2", html_dir / "archivo-var.woff2")

    perfil = tempfile.mkdtemp(prefix="dp-chrome-")
    try:
        for formato, roteiro in (("carrossel", roteiro_carrossel(ctx)), ("vertical", roteiro_vertical(ctx))):
            largura, altura = FORMATOS[formato]
            destino = pasta / formato
            if destino.exists():
                shutil.rmtree(destino)
            destino.mkdir(parents=True)
            for n, (nome, template, extra) in enumerate(roteiro, 1):
                html = html_dir / f"{formato}-{n:02d}-{nome}.html"
                html.write_text(env.get_template(template).render(
                    **ctx, **extra, formato=formato, n=n, total=len(roteiro)), encoding="utf-8")
                fotografar(html, destino / f"{n:02d}-{nome}.png", largura, altura, perfil)
    finally:
        shutil.rmtree(perfil, ignore_errors=True)

    legenda = env.get_template("legenda.txt.j2").render(**ctx)
    (pasta / "legenda.txt").write_text(legenda.strip() + "\n", encoding="utf-8")
    return pasta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera os cards do post de sábado")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--db", default=None)
    args = ap.parse_args(argv)
    pasta = gerar(db.conectar(args.db), args.semana)
    for f in sorted(pasta.glob("*/*.png")):
        print(f.relative_to(config.ROOT))
    print(pasta / "legenda.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
