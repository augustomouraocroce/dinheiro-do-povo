"""Fonte: Senado Federal (Dados Abertos e CSV da CEAPS)."""
import csv
import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from dp import config, http

CASA = "senado"

# Códigos oficiais de voto/frequência do Senado e a categoria usada nos relatórios.
# Códigos não listados viram 'desconhecido' e aparecem no log da coleta para revisão.
CATEGORIA_VOTO = {
    "Sim": "votou",
    "Não": "votou",
    "Abstenção": "votou",
    "Votou": "votou",                      # votação secreta
    "Obstrução": "votou",
    "Presidente (art. 51 RISF)": "votou",
    "P-NRV": "presente_sem_voto",          # Presente – Não registrou voto
    "AP": "ausencia_justificada",          # Atividade parlamentar
    "MIS": "ausencia_justificada",         # Missão da Casa no País/exterior
    "LS": "ausencia_justificada",          # Licença saúde
    "LP": "ausencia_justificada",          # Licença particular
    "LAP": "ausencia_justificada",         # Licença paternidade ou ao adotante
    "LG": "ausencia_justificada",          # Licença gestante
    "NCom": "ausencia_nao_justificada",    # Não compareceu
    "NA": "nao_se_aplica",                 # Dispositivo não citado
}


def pid(id_externo) -> str:
    return f"{CASA}:{id_externo}"


def classificar_voto(sigla: str) -> str:
    return CATEGORIA_VOTO.get(sigla, "desconhecido")


def normalizar_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).upper().strip()


# --- Senadores ---------------------------------------------------------------

def _lista(valor):
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def senadores_em_exercicio():
    dados = http.get_json(f"{config.SENADO_API}/senador/lista/atual")
    return _lista(dados["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])


def senadores_da_legislatura(numero: int):
    dados = http.get_json(f"{config.SENADO_API}/senador/lista/legislatura/{numero}")
    return _lista(dados["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"])


def indice_de_nomes(senadores):
    """{nome normalizado: código} usando nome parlamentar e nome completo.

    Nomes que apontam para mais de um senador são descartados (ambíguos).
    """
    indice, ambiguos = {}, set()
    for s in senadores:
        ident = s["IdentificacaoParlamentar"]
        cod = ident["CodigoParlamentar"]
        for campo in ("NomeParlamentar", "NomeCompletoParlamentar"):
            nome = ident.get(campo)
            if not nome:
                continue
            chave = normalizar_nome(nome)
            if indice.get(chave, cod) != cod:
                ambiguos.add(chave)
            indice[chave] = cod
    for chave in ambiguos:
        del indice[chave]
    return indice


def resolver_senador(nome_csv: str, indice: dict):
    """Acha o código do senador a partir do nome usado no CSV da CEAPS.

    1) nome exato; 2) um único nome do índice que seja prefixo do nome do CSV
    (ex.: CSV 'WEVERTON ROCHA' -> parlamentar 'WEVERTON').
    """
    alvo = normalizar_nome(nome_csv)
    if alvo in indice:
        return indice[alvo]
    candidatos = {cod for nome, cod in indice.items() if alvo.startswith(nome + " ")}
    return candidatos.pop() if len(candidatos) == 1 else None


# --- CEAPS ---------------------------------------------------------------------

def baixar_ceaps(ano: int) -> Path:
    return http.baixar(config.SENADO_CEAPS_CSV.format(ano=ano), f"senado_ceaps_{ano}.csv")


def _valor_br(txt):
    return float(txt.replace(".", "").replace(",", ".")) if txt else 0.0


def _so_cnpj(txt):
    return txt if len(re.sub(r"\D", "", txt or "")) == 14 else None


def ler_ceaps(caminho: Path, indice: dict):
    """Lê o CSV oficial (latin-1, 1ª linha = data de atualização)."""
    texto = Path(caminho).read_bytes().decode("latin-1")
    _atualizacao, _, corpo = texto.partition("\n")
    for linha in csv.DictReader(io.StringIO(corpo), delimiter=";"):
        cod = resolver_senador(linha["SENADOR"], indice)
        data = linha["DATA"]
        yield {
            "chave": f"senado:{linha['COD_DOCUMENTO']}",
            "casa": CASA,
            "parlamentar_id": pid(cod) if cod else None,
            "nome_na_nota": linha["SENADOR"],
            "partido_na_nota": None,  # a CEAPS não informa partido
            "uf": None,
            "data_emissao": datetime.strptime(data, "%d/%m/%Y").date().isoformat() if data else None,
            "ano": int(linha["ANO"]),
            "mes": int(linha["MES"]),
            "categoria": linha["TIPO_DESPESA"],
            "fornecedor": linha["FORNECEDOR"],
            "cnpj": _so_cnpj(linha["CNPJ_CPF"]),
            "valor_documento": None,
            "valor_glosa": None,
            "valor_liquido": _valor_br(linha["VALOR_REEMBOLSADO"]),
            "trecho": linha["DETALHAMENTO"] or None,
            "url_documento": None,
        }


# --- Votações nominais -----------------------------------------------------------

def votacoes(inicio, fim):
    """Votações nominais do Plenário com os votos de cada senador (período ≤ 1 ano)."""
    return http.get_json(f"{config.SENADO_API}/votacao",
                         {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat()})
