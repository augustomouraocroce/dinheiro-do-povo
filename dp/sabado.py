"""Rotina de sábado: coleta, relatório, cards, site e publicação no Netlify.

Uso:
    python -m dp.sabado                   # último sábado (hoje, se for sábado)
    python -m dp.sabado --sem-publicar    # gera tudo, mas não publica
    python -m dp.sabado --semana 2026-10-31

Se alguma coleta falhar, o site não é publicado: os números da semana ficariam
incompletos. O patrimônio do TSE não entra aqui (só muda em ano de eleição); rode
`python -m dp.coleta --casa tse` quando sair uma declaração nova.
"""
import argparse
import subprocess
import sys
import traceback
from datetime import date, datetime

from dp import coleta, config, relatorio
from dp.cards import gerar as cards
from dp.site import build

COLETAS = ("camara", "senado", "trabalho", "rankings")
NETLIFY = ["npx", "-y", "netlify-cli@27.14.3", "deploy", "--prod", "--no-build", "--dir", "public"]


def passo(nome, funcao, falhas):
    print(f"\n=== {nome} ({datetime.now():%H:%M}) ===", flush=True)
    try:
        funcao()
        return True
    except Exception:
        traceback.print_exc()
        falhas.append(nome)
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rotina de sábado do Dinheiro do Povo")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--sem-publicar", action="store_true", help="Gera tudo, mas não publica no Netlify.")
    args = ap.parse_args(argv)
    semana = ["--semana", args.semana.isoformat()]
    falhas = []

    for casa in COLETAS:
        passo(f"coleta {casa}", lambda: coleta.main(semana + ["--casa", casa]), falhas)
    coleta_ok = not falhas
    passo("relatório", lambda: relatorio.main(semana), falhas)
    passo("cards", lambda: cards.main(semana), falhas)
    passo("site", lambda: build.main(semana), falhas)

    if args.sem_publicar:
        print("\nNão publicado (--sem-publicar).")
    elif not coleta_ok or falhas:
        print(f"\nNÃO PUBLICADO: falhou {', '.join(falhas)}. Confira e rode de novo.")
    else:
        passo("publicação no Netlify",
              lambda: subprocess.run(NETLIFY, cwd=config.ROOT, check=True, timeout=900), falhas)

    print(f"\nCards: cards/{args.semana.isoformat()}/  ·  Site: https://dinheiro-do-povo.netlify.app/posts.html")
    print("Tudo certo." if not falhas else f"Com problemas: {', '.join(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
