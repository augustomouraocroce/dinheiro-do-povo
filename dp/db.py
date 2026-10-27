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

-- Salário, cota, verba de gabinete e benefícios como publicados na página
-- oficial de cada parlamentar (um registro por item, por ano).
CREATE TABLE IF NOT EXISTS recurso_oficial (
    parlamentar_id   TEXT NOT NULL,
    ano              INTEGER NOT NULL,
    item             TEXT NOT NULL,          -- 'salario_bruto_mensal', 'cota_gasto', 'verba_gabinete_mes_03'...
    valor            REAL,
    texto            TEXT,
    url_fonte        TEXT NOT NULL,
    atualizado_fonte TEXT,                   -- "atualizado em" informado pela própria Casa
    coletado_em      TEXT NOT NULL,
    PRIMARY KEY (parlamentar_id, ano, item)
);

-- Bens declarados ao TSE em cada candidatura (valor declarado, não de mercado).
CREATE TABLE IF NOT EXISTS patrimonio (
    parlamentar_id TEXT NOT NULL,
    ano_eleicao    INTEGER NOT NULL,
    cargo          TEXT,                     -- cargo disputado naquela eleição
    situacao       TEXT,                     -- resultado (ELEITO, SUPLENTE...)
    partido        TEXT,                     -- partido na candidatura
    total          REAL NOT NULL,
    metodo         TEXT NOT NULL,            -- como o vínculo foi feito: 'cpf' | 'nome+uf'
    url_fonte      TEXT NOT NULL,
    PRIMARY KEY (parlamentar_id, ano_eleicao)
);

CREATE TABLE IF NOT EXISTS patrimonio_tipo (
    parlamentar_id TEXT NOT NULL,
    ano_eleicao    INTEGER NOT NULL,
    tipo           TEXT NOT NULL,
    valor          REAL NOT NULL,
    PRIMARY KEY (parlamentar_id, ano_eleicao, tipo)
);

-- Temas oficiais das proposições da Câmara (cache da API; cod_tema NULL = sem tema).
CREATE TABLE IF NOT EXISTS proposicao_tema (
    proposicao_id TEXT NOT NULL,
    cod_tema      INTEGER,
    UNIQUE (proposicao_id, cod_tema)
);

-- Votações nominais do Plenário sobre trabalho e renda (regra em dp/trabalho.json).
CREATE TABLE IF NOT EXISTS pauta_trabalho (
    votacao_id     TEXT PRIMARY KEY REFERENCES votacao(id),
    casa           TEXT NOT NULL,
    proposicao     TEXT NOT NULL,
    ementa         TEXT,
    url_proposicao TEXT,
    motivo         TEXT NOT NULL
);

-- Dias com sessão deliberativa no Plenário, por ano.
CREATE TABLE IF NOT EXISTS dias_sessao (
    casa      TEXT NOT NULL,
    ano       INTEGER NOT NULL,
    dias      INTEGER NOT NULL,
    ate       TEXT NOT NULL,
    url_fonte TEXT NOT NULL,
    PRIMARY KEY (casa, ano)
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
    colunas_voto = {r[1] for r in conn.execute("PRAGMA table_info(voto)")}
    if "partido" not in colunas_voto:  # partido do parlamentar na data do voto
        conn.execute("ALTER TABLE voto ADD COLUMN partido TEXT")
    return conn
