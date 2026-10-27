"""Gráficos em HTML + CSS: o texto fica sempre no tamanho de leitura, em qualquer tela.

Especificação comum: barras de no máximo 24px, ponta de dado arredondada em 4px
e base reta, 2px de folga entre segmentos, texto sempre em tinta (nunca na cor
da série). Cada marca leva `data-tip` (dica ao passar o dedo/mouse) e é
focável; cada gráfico tem rótulo para leitores de tela e, na página, uma
tabela equivalente.
"""
from html import escape

from dp.relatorio import brl

COR_SERIE = {
    "salario": "var(--s-salario)",
    "cota": "var(--s-cota)",
    "verba": "var(--s-verba)",
    "auxilio": "var(--s-auxilio)",
    "referencia": "var(--s-referencia)",
}


def brl_compacto(v: float) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1_000_000:
        return f"R$ {v / 1_000_000:.1f} mi".replace(".", ",")
    if abs(v) >= 10_000:
        return f"R$ {v / 1000:.0f} mil"
    return brl(v)


def _marca(classe, estilo, tip):
    t = escape(tip)
    return f'<span class="{classe}" style="{estilo}" data-tip="{t}" tabindex="0" aria-label="{t}"></span>'


def barras_custo(linhas, titulo: str) -> str:
    """Barras horizontais empilhadas numa mesma escala (régua única).

    linhas: [{"rotulo": str, "partes": [{"chave","nome","valor"}], "total": float}]
    """
    escala = max(l["total"] for l in linhas) or 1
    out = [f'<div class="g-barras" role="group" aria-label="{escape(titulo)}">']
    for l in linhas:
        segs = "".join(
            _marca("g-seg", f'flex-grow:{p["valor"]:.2f};background:{COR_SERIE.get(p["chave"], "var(--s-referencia)")}',
                   f'{p["nome"]}: {brl(p["valor"])} por mês')
            for p in l["partes"] if p["valor"] > 0)
        out.append(
            f'<div class="g-linha"><span class="g-rot">{escape(l["rotulo"])}</span>'
            f'<span class="g-trilho"><span class="g-barra" style="--f:{l["total"] / escala:.5f}">{segs}</span>'
            f'<span class="g-val">{brl_compacto(l["total"])}</span></span></div>')
    out.append("</div>")
    return "".join(out)


def barras_comparacao(linhas, titulo: str, formato, destaque=None) -> str:
    """Um valor por linha; "Todos" (a Casa inteira) em tinta como referência.

    linhas: [{"rotulo": str, "valor": float, "todos": bool}]
    destaque: rótulo na cor de ênfase; com destaque, os demais ficam em cinza.
    """
    vmax = max((l["valor"] or 0) for l in linhas) or 1
    out = [f'<div class="g-barras g-compacto" role="group" aria-label="{escape(titulo)}">']
    for l in linhas:
        if l.get("todos"):
            cor = "var(--tinta)"
        elif destaque is None or l["rotulo"] == destaque:
            cor = "var(--carimbo)"
        else:
            cor = "var(--s-referencia)"
        forte = " g-forte" if l.get("todos") or l["rotulo"] == destaque else ""
        valor = l["valor"] or 0
        barra = _marca("g-seg", f"flex-grow:1;background:{cor}", f'{l["rotulo"]}: {formato(l["valor"])}')
        out.append(
            f'<div class="g-linha g-lado"><span class="g-rot{forte}">{escape(l["rotulo"])}</span>'
            f'<span class="g-trilho"><span class="g-barra" style="--f:{valor / vmax:.5f}">{barra}</span>'
            f'<span class="g-val">{formato(l["valor"])}</span></span></div>')
    out.append("</div>")
    return "".join(out)


def colunas_mensais(serie: dict, mes_corte: int, meses: list, titulo: str, cor="var(--s-cota)") -> str:
    """Colunas por mês; meses depois de `mes_corte` ganham hachura (ainda podem aumentar)."""
    vmax = max(serie.values(), default=0) or 1
    mes_max = max(serie, key=serie.get) if serie else None
    # O maior mês vai numa legenda acima: dentro de uma coluna estreita o rótulo vaza para as vizinhas.
    out = [f'<p class="g-destaque">Maior mês: <strong>{meses[mes_max - 1]}, {brl(serie[mes_max])}</strong></p>'
           if mes_max else "",
           f'<div class="g-colunas" role="group" aria-label="{escape(titulo)}" style="--cor:{cor}">']
    for m in range(1, 13):
        v = serie.get(m)
        conteudo = ""
        if v is not None:
            recente = m > mes_corte
            tip = f"{meses[m - 1]}: {brl(v)}" + (" (ainda pode aumentar)" if recente else "")
            conteudo = _marca("g-col-barra" + (" recente" if recente else ""),
                              f"height:{max(100 * v / vmax, 1):.2f}%", tip)
        out.append(f'<div class="g-col"><div class="g-col-area">{conteudo}</div>'
                   f'<span class="g-col-mes"><span class="mes-longo">{meses[m - 1]}</span>'
                   f'<span class="mes-curto" aria-hidden="true">{meses[m - 1][0].upper()}</span></span></div>')
    out.append("</div>")
    return "".join(out)


def colunas_patrimonio(declaracoes, titulo: str) -> str:
    """Patrimônio declarado em cada eleição (2018, 2022, 2026), com o valor em cada coluna."""
    vmax = max((d["total"] for d in declaracoes), default=0) or 1
    out = [f'<div class="g-colunas g-poucas" role="group" aria-label="{escape(titulo)}" style="--cor:var(--carimbo)">']
    for d in declaracoes:
        tip = f'{d["ano_eleicao"]}: {brl(d["total"])} declarados ao TSE'
        out.append(
            f'<div class="g-col"><div class="g-col-area"><span class="g-col-val">{brl_compacto(d["total"])}</span>'
            + _marca("g-col-barra", f'height:{max(100 * d["total"] / vmax, 1):.2f}%', tip)
            + f'</div><span class="g-col-mes">{d["ano_eleicao"]}</span></div>')
    out.append("</div>")
    return "".join(out)
