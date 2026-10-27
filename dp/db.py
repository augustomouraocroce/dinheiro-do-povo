"""Banco SQLite local. Todas as escritas são idempotentes (upsert)."""
import sqlite3
from pathlib import Path

from dp import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS parlamentar (
    id            TEXT PRIMARY KEY,          -- 'camara:221328' / 'senado:5672'
    casa          TEXT NOT NULL,
    id_externo    TEXT NOT NULL,
    nome          TEXT NOT NULL,
    uf            TEXT,
    url_foto      TEXT,
    url_perfil    TEXT,
    atualizado_em TEXT NOT NULL
);

-- Partido observado em cada coleta: preserva o histórico de trocas.
CREATE TABLE IF NOT EXISTS filiacao (
    parlamentar_id TEXT NOT NULL REFERENCES parlamentar(id),
    partido        TEXT NOT NULL,
    visto_em       TEXT NOT NULL,
    PRIMARY KEY (parlamentar_id, visto_em)
);

CREATE TABLE IF NOT EXISTS despesa (
    chave              TEXT PRIMARY KEY,     -- hash de campos estáveis da nota
    casa               TEXT NOT NULL,
    parlamentar_id     TEXT,                 -- NULL para lideranças/órgãos
    nome_na_nota       TEXT,
    partido_na_nota    TEXT,
    uf                 TEXT,
    data_emissao       TEXT,
    ano                INTEGER,
    mes                INTEGER,
    categoria          TEXT,
    fornecedor         TEXT,
    cnpj               TEXT,                 -- só CNPJ; CPF de pessoa física não é guardado
    valor_documento    REAL,
    valor_glosa        REAL,
    valor_liquido      REAL NOT NULL,
    trecho             TEXT,
    url_documento      TEXT,
    primeira_vez_vista TEXT NOT NULL,        -- data da coleta em que a nota apareceu
    ultima_vez_vista   TEXT NOT NULL,
    carga_inicial      INTEGER NOT NULL      -- 1 = já existia na 1ª coleta (não é "nova")
);
CREATE INDEX IF NOT EXISTS ix_despesa_parl ON despesa(parlamentar_id, primeira_vez_vista);

CREATE TABLE IF NOT EXISTS sessao (
    id          TEXT PRIMARY KEY,            -- 'camara:83066'
    casa        TEXT NOT NULL,
    inicio      TEXT NOT NULL,
    tipo        TEXT,
    situacao    TEXT,
    descricao   TEXT,
    url_fonte   TEXT
);

-- Registro de presença da API de eventos (somente presentes).
CREATE TABLE IF NOT EXISTS presenca_sessao (
    sessao_id      TEXT NOT NULL REFERENCES sessao(id),
    parlamentar_id TEXT NOT NULL,
    PRIMARY KEY (sessao_id, parlamentar_id)
);

-- Frequência oficial por dia (página "Presença em Plenário").
CREATE TABLE IF NOT EXISTS presenca_dia (
    parlamentar_id TEXT NOT NULL,
    data           TEXT NOT NULL,
    status         TEXT NOT NULL,            -- texto oficial: 'Presença', 'Ausência', 'Missão Autorizada'...
    categoria      TEXT NOT NULL,            -- presente | ausencia_justificada | ausencia_nao_justificada
    url_fonte      TEXT NOT NULL,
    coletado_em    TEXT NOT NULL,
    PRIMARY KEY (parlamentar_id, data)
);

CREATE TABLE IF NOT EXISTS presenca_resumo_oficial (
    parlamentar_id TEXT NOT NULL,
    ano            INTEGER NOT NULL,
    indicador      TEXT NOT NULL,
    valor          INTEGER NOT NULL,
    percentual     TEXT,
    url_fonte      TEXT NOT NULL,
    coletado_em    TEXT NOT NULL,
    PRIMARY KEY (parlamentar_id, ano, indicador)
);

CREATE TABLE IF NOT EXISTS votacao (
    id          TEXT PRIMARY KEY,            -- 'camara:2487836-52'
    casa        TEXT NOT NULL,
    data        TEXT NOT NULL,
    descricao   TEXT,
    aprovada    INTEGER,
    sessao_id   TEXT,
    url_fonte   TEXT
);

CREATE TABLE IF NOT EXISTS voto (
    votacao_id     TEXT NOT NULL REFERENCES votacao(id),
    parlamentar_id TEXT NOT NULL,
    voto           TEXT NOT NULL,
    PRIMARY KEY (votacao_id, parlamentar_id)
);

-- Salário, verba de gabinete etc. Sempre com vigência e fonte oficial.
CREATE TABLE IF NOT EXISTS custo_fixo (
    casa        TEXT NOT NULL,
    item        TEXT NOT NULL,
    valor_mensal REAL NOT NULL,
    vigente_de  TEXT NOT NULL,
    vigente_ate TEXT,
    url_fonte   TEXT NOT NULL,
    PRIMARY KEY (casa, item, vigente_de)
);

CREATE TABLE IF NOT EXISTS coleta_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    etapa       TEXT NOT NULL,
    iniciado_em TEXT NOT NULL,
    terminado_em TEXT,
    status      TEXT,
    detalhes    TEXT
);
"""


def conectar(path: Path = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
