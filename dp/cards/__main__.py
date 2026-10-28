"""Gera os cards do post de sábado.

Uso:
    python -m dp.cards                      # último sábado
    python -m dp.cards --semana 2026-10-24
Saída: cards/AAAA-MM-DD/carrossel/*.png (1080×1350), vertical/*.png (1080×1920) e legenda.txt.
"""
import sys

from dp.cards.gerar import main

if __name__ == "__main__":
    sys.exit(main())
