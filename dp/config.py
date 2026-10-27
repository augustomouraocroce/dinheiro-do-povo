"""Configuração central do Dinheiro do Povo."""
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "dinheiro.db"

# Siglas exatamente como aparecem nas APIs da Câmara/Senado.
# PSC (incorporado ao Podemos em 2023) e UDN não têm parlamentares hoje;
# ficam aqui para entrarem automaticamente se voltarem a aparecer nos dados.
PARTIDOS_MONITORADOS = {
    "PL": "Partido Liberal",
    "PP": "Progressistas",
    "REPUBLICANOS": "Republicanos",
    "MDB": "Movimento Democrático Brasileiro",
    "PODE": "Podemos",
    "NOVO": "Partido Novo",
    "MISSÃO": "Partido Missão",
    "PSC": "Partido Social Cristão",
    "UDN": "União Democrática Nacional",
}

CAMARA_API = "https://dadosabertos.camara.leg.br/api/v2"
CAMARA_CEAP_ZIP = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
CAMARA_PRESENCA = "https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}"
CAMARA_PERFIL = "https://www.camara.leg.br/deputados/{id}"
CAMARA_ORGAO_PLENARIO = 180
# 110 e 204 são os dois códigos de "Sessão Deliberativa" na API.
CAMARA_TIPOS_SESSAO_DELIBERATIVA = (110, 204)

SENADO_API = "https://legis.senado.leg.br/dadosabertos"
SENADO_CEAPS_CSV = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"

USER_AGENT = "DinheiroDoPovo/0.1 (projeto de transparencia com dados abertos)"


def semana_referencia(sabado_relatorio: date):
    """Semana coberta pelo relatório publicado em `sabado_relatorio`.

    Vai do sábado anterior até a sexta-feira véspera do relatório.
    Ex.: relatório de 24/10/2026 cobre 17/10 a 23/10.
    """
    if sabado_relatorio.weekday() != 5:
        raise ValueError(f"{sabado_relatorio} não é sábado")
    return sabado_relatorio - timedelta(days=7), sabado_relatorio - timedelta(days=1)


def ultimo_sabado(hoje: date = None) -> date:
    hoje = hoje or date.today()
    return hoje - timedelta(days=(hoje.weekday() - 5) % 7)
