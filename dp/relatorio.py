"""Gera o relatório semanal em Markdown e HTML.

Uso:
    python -m dp.relatorio                      # último sábado
    python -m dp.relatorio --semana 2026-10-17
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from dp import config, db, metricas

TEMPLATES = Path(__file__).parent / "templates"
SAIDA = config.ROOT / "relatorios"


def brl(v):
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def pct(v):
    return "—" if v is None else f"{v * 100:.1f}%".replace(".", ",")


def num(v):
    return f"{v:,}".replace(",", ".") if isinstance(v, int) else str(v)


def plural(n, singular, plural_):
    return singular if n == 1 else plural_


def data_br(v):
    if isinstance(v, (date, datetime)):
        return v.strftime("%d/%m/%Y")
    return datetime.strptime(v[:10], "%Y-%m-%d").strftime("%d/%m/%Y") if v else "—"


def dia_mes(v):
    return data_br(v)[:5]


def ambiente() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters.update(brl=brl, pct=pct, num=num, data=data_br, dia_mes=dia_mes, plural=plural)
    return env


def gerar(conn, sabado: date, saida: Path = SAIDA):
    ctx = metricas.montar_relatorio(conn, sabado)
    env = ambiente()
    texto_md = env.get_template("relatorio.md.j2").render(**ctx)
    corpo = markdown.markdown(texto_md, extensions=["tables", "sane_lists"])
    html = env.get_template("relatorio.html.j2").render(corpo=corpo, **ctx)

    saida.mkdir(parents=True, exist_ok=True)
    caminho_md = saida / f"{sabado.isoformat()}.md"
    caminho_html = saida / f"{sabado.isoformat()}.html"
    caminho_md.write_text(texto_md, encoding="utf-8")
    caminho_html.write_text(html, encoding="utf-8")
    return caminho_md, caminho_html


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera o relatório semanal do Dinheiro do Povo")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--db", default=None, help="Caminho alternativo do banco")
    args = ap.parse_args(argv)
    for caminho in gerar(db.conectar(args.db), args.semana):
        print(caminho)
    return 0


if __name__ == "__main__":
    sys.exit(main())
