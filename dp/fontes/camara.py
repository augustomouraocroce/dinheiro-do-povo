"""Fonte: Câmara dos Deputados (API Dados Abertos, CSV da CEAP e página de presença)."""
import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from dp import config, http

CASA = "camara"

# Campos que identificam uma nota da CEAP e não mudam depois de publicada.
# (ideDocumento sozinho se repete; esta combinação é única no arquivo de 2026.)
CAMPOS_CHAVE_CEAP = (
    "nuDeputadoId", "ideDocumento", "numParcela", "txtNumero", "txtCNPJCPF",
    "datEmissao", "vlrDocumento", "vlrLiquido", "txtPassageiro", "txtTrecho",
    "numSubCota", "numMes", "numAno",
)


def pid(id_externo) -> str:
    return f"{CASA}:{id_externo}"


def _paginar(caminho, params):
    url = f"{config.CAMARA_API}{caminho}"
    params = dict(params, itens=100)
    while url:
        dados = http.get_json(url, params)
        yield from dados["dados"]
        url = next((l["href"] for l in dados.get("links", []) if l["rel"] == "next"), None)
        params = None  # o link "next" já traz os parâmetros


# --- Deputados -------------------------------------------------------------

def deputados_em_exercicio():
    return list(_paginar("/deputados", {}))


# --- Cota parlamentar (CEAP) -----------------------------------------------

def baixar_ceap(ano: int) -> Path:
    return http.baixar(config.CAMARA_CEAP_ZIP.format(ano=ano), f"camara_ceap_{ano}.csv.zip")


def _num(txt):
    return float(txt) if txt not in ("", None) else None


def _so_cnpj(txt):
    digitos = re.sub(r"\D", "", txt or "")
    return txt if len(digitos) == 14 else None


def chave_ceap(linha: dict) -> str:
    bruto = "|".join(linha.get(c, "") for c in CAMPOS_CHAVE_CEAP)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def ler_ceap(caminho: Path):
    """Lê o CSV (ou o .zip oficial) e devolve dicts normalizados."""
    caminho = Path(caminho)
    if caminho.suffix == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nome = next(n for n in z.namelist() if n.endswith(".csv"))
            texto = z.read(nome).decode("utf-8-sig")
    else:
        texto = caminho.read_text(encoding="utf-8-sig")
    for linha in csv.DictReader(io.StringIO(texto), delimiter=";"):
        dep = linha["ideCadastro"]
        yield {
            "chave": chave_ceap(linha),
            "casa": CASA,
            "parlamentar_id": pid(dep) if dep else None,
            "nome_na_nota": linha["txNomeParlamentar"],
            "partido_na_nota": linha["sgPartido"] or None,
            "uf": linha["sgUF"],
            "data_emissao": linha["datEmissao"][:10] or None,
            "ano": int(linha["numAno"]),
            "mes": int(linha["numMes"]),
            "categoria": linha["txtDescricao"],
            "fornecedor": linha["txtFornecedor"],
            "cnpj": _so_cnpj(linha["txtCNPJCPF"]),
            "valor_documento": _num(linha["vlrDocumento"]),
            "valor_glosa": _num(linha["vlrGlosa"]),
            "valor_liquido": _num(linha["vlrLiquido"]) or 0.0,
            "trecho": linha["txtTrecho"] or None,
            "url_documento": linha["urlDocumento"] or None,
        }


# --- Sessões, presença e votações -------------------------------------------

def sessoes_deliberativas(inicio, fim):
    params = {
        "dataInicio": inicio.isoformat(),
        "dataFim": fim.isoformat(),
        "codTipoEvento": list(config.CAMARA_TIPOS_SESSAO_DELIBERATIVA),
    }
    return list(_paginar("/eventos", params))


def presentes_na_sessao(evento_id):
    # Este endpoint não aceita paginação (`itens` devolve 400).
    return http.get_json(f"{config.CAMARA_API}/eventos/{evento_id}/deputados")["dados"]


def votacoes_plenario(inicio, fim):
    params = {
        "dataInicio": inicio.isoformat(),
        "dataFim": fim.isoformat(),
        "idOrgao": config.CAMARA_ORGAO_PLENARIO,
    }
    return list(_paginar("/votacoes", params))


def votos(votacao_id):
    return http.get_json(f"{config.CAMARA_API}/votacoes/{votacao_id}/votos")["dados"]


# --- Página oficial "Presença em Plenário" -----------------------------------

def baixar_pagina_presenca(dep_id, ano) -> str:
    url = config.CAMARA_PRESENCA.format(id=dep_id, ano=ano)
    return http.get(url, accept="text/html", pausa=0.3).text


def classificar_frequencia(status: str) -> str:
    """Traduz o status oficial do dia em uma de três categorias.

    A Câmara publica o motivo da justificativa no próprio status
    ('Missão Autorizada', 'Licença para Tratamento de Saúde', ...).
    Só 'Ausência' é falta não justificada.
    """
    if status == "Presença":
        return "presente"
    if status == "Ausência":
        return "ausencia_nao_justificada"
    return "ausencia_justificada"


def ler_pagina_presenca(html: str):
    """Devolve (dias, resumo).

    dias:   [{'data': 'AAAA-MM-DD', 'status': 'Missão Autorizada',
              'categoria': 'ausencia_justificada'}, ...]
    resumo: [{'indicador': '...', 'valor': 75, 'percentual': '100,00%'}, ...]
    O texto de status é mantido exatamente como publicado pela Câmara.
    """
    soup = BeautifulSoup(html, "html.parser")
    tabelas = soup.find_all("table", class_="table-bordered")
    if len(tabelas) < 2:
        raise ValueError("Layout da página de presença mudou: tabelas não encontradas")

    dias = []
    for tr in tabelas[0].find_all("tr", class_="info-data"):
        tds = tr.find_all("td")
        data_txt = tds[0].get_text(" ", strip=True).split(" ")[0]
        status = tds[2].get_text(" ", strip=True)
        dias.append({
            "data": datetime.strptime(data_txt, "%d/%m/%Y").date().isoformat(),
            "status": status,
            "categoria": classificar_frequencia(status),
        })

    resumo = []
    for tr in tabelas[1].find_all("tr"):
        cels = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cels) == 3 and cels[1].isdigit():
            resumo.append({
                "indicador": cels[0].rstrip("*").strip(),
                "valor": int(cels[1]),
                "percentual": cels[2] or None,
            })
    return dias, resumo


# --- Página oficial do deputado (salário, cota, verba de gabinete, benefícios) ---

# Rótulo na página -> nome do item no banco. Itens numéricos ficam em `valor`.
_BENEFICIOS = {
    "Salário mensal bruto": ("salario_bruto_mensal", True),
    "Pessoal de gabinete": ("pessoal_gabinete", False),
    "Imóvel funcional": ("imovel_funcional", False),
    "Auxílio-moradia": ("auxilio_moradia", True),       # "Recebeu R$ 38.277" ou "Não recebe"
    "Viagens em missão oficial": ("viagens_missao_oficial", True),
    "Passaporte diplomático": ("passaporte_diplomatico", False),
}
_TABELAS_TOTAL = {
    "percentualgastocotaparlamentar": "cota",
    "percentualgastoverbagabinete": "verba_gabinete",
}
_TABELAS_MENSAL = {
    "gastomensalcotaparlamentar": "cota_mes",
    "gastomensalverbagabinete": "verba_gabinete_mes",
}
_MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def valor_br(txt: str):
    """'R$ 1.050.138,62' -> 1050138.62; texto sem número -> None."""
    m = re.search(r"-?[\d.]+(,\d+)?", txt or "")
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def baixar_pagina_perfil(dep_id, ano) -> str:
    url = config.CAMARA_PERFIL_ANO.format(id=dep_id, ano=ano)
    return http.get(url, accept="text/html", pausa=0.3).text


def ler_pagina_perfil(html: str):
    """Devolve (itens, atualizado_em).

    itens: [{'item': 'cota_gasto', 'valor': 362538.41, 'texto': '362.538,41'}, ...]
    atualizado_em: data/hora informada pela Câmara ('26/10/2026 06:00') ou None.
    """
    soup = BeautifulSoup(html, "html.parser")
    itens = []

    for bloco in soup.select("div.beneficio"):
        partes = [p for p in bloco.stripped_strings if p != "?"]
        if not partes or partes[0] not in _BENEFICIOS:
            continue
        nome, numerico = _BENEFICIOS[partes[0]]
        texto = " ".join(" ".join(partes[1:]).split())
        itens.append({"item": nome, "valor": valor_br(texto) if numerico else None, "texto": texto})

    for tabela_id, prefixo in _TABELAS_TOTAL.items():
        tabela = soup.find("table", id=tabela_id)
        for tr in tabela.find_all("tr") if tabela else []:
            cels = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cels) >= 2 and cels[0] in ("Gasto", "Não utilizado"):
                sufixo = "gasto" if cels[0] == "Gasto" else "nao_utilizado"
                itens.append({"item": f"{prefixo}_{sufixo}", "valor": valor_br(cels[1]), "texto": cels[1]})

    for tabela_id, prefixo in _TABELAS_MENSAL.items():
        tabela = soup.find("table", id=tabela_id)
        for tr in tabela.find_all("tr") if tabela else []:
            cels = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cels) >= 2 and cels[0] in _MESES:
                mes = _MESES.index(cels[0]) + 1
                itens.append({"item": f"{prefixo}_{mes:02d}", "valor": valor_br(cels[1]), "texto": cels[1]})

    if not any(i["item"] == "salario_bruto_mensal" for i in itens):
        raise ValueError("Layout da página do deputado mudou: salário não encontrado")

    atualizado = soup.find(string=re.compile(r"Informações de recursos atualizadas em"))
    m = re.search(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2})", atualizado or "")
    return itens, (m.group(1) if m else None)
