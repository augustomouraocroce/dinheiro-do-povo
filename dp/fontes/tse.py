"""Fonte: TSE (candidaturas e bens declarados, Portal de Dados Abertos).

O CPF só é usado em memória, para ligar parlamentar e candidatura; nunca é
gravado no banco nem exibido.
"""
import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

from dp import config, http

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/{tipo}/{tipo}_{ano}.zip"


def url_bens(ano: int) -> str:
    return URL.format(tipo="bem_candidato", ano=ano)


def baixar(tipo: str, ano: int) -> Path:
    return http.baixar(URL.format(tipo=tipo, ano=ano), f"tse_{tipo}_{ano}.zip")


def _linhas(zip_path: Path):
    """Lê todos os CSVs por UF dentro do .zip oficial (latin-1, separador ;)."""
    with zipfile.ZipFile(zip_path) as z:
        for nome in sorted(z.namelist()):
            if not nome.endswith(".csv") or nome.endswith("_BRASIL.csv"):
                continue
            with z.open(nome) as f:
                yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")


def _valor(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", ".")) if txt else 0.0


def ler_candidaturas(zip_path: Path):
    """Uma linha por candidatura (SQ_CANDIDATO), última situação conhecida."""
    vistos = {}
    for l in _linhas(zip_path):
        vistos[l["SQ_CANDIDATO"]] = {
            "ano": int(l["ANO_ELEICAO"]),
            "sq": l["SQ_CANDIDATO"],
            "cpf": l["NR_CPF_CANDIDATO"],
            "nome": l["NM_CANDIDATO"],
            "nome_urna": l["NM_URNA_CANDIDATO"],
            "uf": l["SG_UF"],
            "cargo": l["DS_CARGO"],
            "partido": l["SG_PARTIDO"],
            "situacao": l["DS_SIT_TOT_TURNO"],
        }
    return list(vistos.values())


def somar_bens(zip_path: Path) -> dict:
    """{SQ_CANDIDATO: {'total': x, 'por_tipo': {tipo: valor}}}."""
    bens = defaultdict(lambda: {"total": 0.0, "por_tipo": defaultdict(float)})
    for l in _linhas(zip_path):
        v = _valor(l["VR_BEM_CANDIDATO"])
        b = bens[l["SQ_CANDIDATO"]]
        b["total"] += v
        b["por_tipo"][l["DS_TIPO_BEM_CANDIDATO"]] += v
    return bens


def cpfs_dos_deputados(caminho_ceap: Path) -> dict:
    """{id do deputado na Câmara: CPF} a partir do CSV oficial da cota."""
    caminho_ceap = Path(caminho_ceap)
    with zipfile.ZipFile(caminho_ceap) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        texto = z.read(nome).decode("utf-8-sig")
    saida = {}
    for l in csv.DictReader(io.StringIO(texto), delimiter=";"):
        if l["ideCadastro"] and l["cpf"]:
            saida[l["ideCadastro"]] = l["cpf"].zfill(11)
    return saida


def escolher_candidatura(candidaturas: list):
    """Entre as candidaturas da mesma pessoa, a da eleição mais recente."""
    return max(candidaturas, key=lambda c: c["ano"]) if candidaturas else None
