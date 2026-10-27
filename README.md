# Dinheiro do Povo

Quanto custam, como comparecem e como votam os deputados e senadores de **PL, PP, Republicanos, MDB, Podemos, Novo e Missão**, só com dados oficiais e o link da fonte de cada número. O projeto gera, toda semana, um relatório e um site que traduz os valores em coisas do dia a dia (salários mínimos, cestas básicas, passagens de avião, metros quadrados de apartamento) para que qualquer pessoa entenda o tamanho do gasto.

Tom de portal de transparência: sem opinião, sem adjetivos sobre pessoas. Todo valor aparece ao lado da média da Casa inteira, e toda conta feita por nós é explicada.

## O que o site mostra

- **Custo médio do mandato por mês** de cada deputado: salário bruto, cota parlamentar, verba de gabinete e auxílio-moradia, comparado com a média da Câmara e com um salário mínimo.
- **Equivalências do dia a dia** com fonte e data: salário mínimo, cesta básica, passagem aérea, m² de apartamento, carro 0 km e apartamento de 50 m².
- **Presença no Plenário**, dia a dia, com marcas ✓ (presente), J (ausência justificada) e ✕ (sem justificativa).
- **Votações nominais** da semana e o voto de cada parlamentar.
- **Patrimônio declarado ao TSE** em 2018, 2022 e 2026, por tipo de bem.
- **Partidos lado a lado** e uma página por partido.
- **Busca** por nome ou sigla, com foto oficial e logo do partido.
- **Relatório semanal** (sábado a sexta) em Markdown e HTML.

## Fontes

| Dado | Fonte oficial |
|---|---|
| Deputados, sessões, votações | API Dados Abertos da Câmara |
| Presença por dia (com motivo da ausência) | Página "Presença em Plenário" de cada deputado |
| Salário, cota, verba de gabinete, benefícios | Página "Recursos e benefícios" de cada deputado |
| Notas da cota parlamentar (CEAP) | Arquivo anual da Câmara |
| Senadores, votações nominais | Dados Abertos do Senado |
| Cota dos senadores (CEAPS) | Arquivo anual do Senado |
| Candidaturas e bens declarados | Portal de Dados Abertos do TSE (2018, 2022, 2026) |
| Referências do dia a dia | Planalto (salário mínimo), DIEESE/Conab (cesta básica), ANAC (tarifa aérea), FipeZAP (m²), Renault (carro 0 km) |

Os valores de referência, com data e link, ficam em [`dp/referencias.json`](dp/referencias.json) e devem ser revistos todo mês.

## Como rodar

Requer Python 3.9+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Rotina semanal (o sábado é a data do relatório; a semana coberta vai do sábado anterior até sexta):

```bash
.venv/bin/python -m dp.coleta --semana 2026-10-24      # coleta tudo (~5 min)
.venv/bin/python -m dp.relatorio --semana 2026-10-24   # relatorios/2026-10-24.md e .html
.venv/bin/python -m dp.site.build --semana 2026-10-24  # site em public/
.venv/bin/python -m dp.site.build --semana 2026-10-24 --artefato  # versão para artefato do claude.ai
```

Para ver o site localmente:

```bash
cd public && python3 -m http.server 8765
```

Testes:

```bash
.venv/bin/python -m pytest
```

## Método e cuidados

- **Despesas novas** são as que entraram nos dados oficiais desde a coleta anterior, não as gastas na semana (o parlamentar tem até 90 dias para apresentar a nota).
- **Custo médio por mês** = salário bruto + média mensal da cota e da verba de gabinete nos meses fora da janela de 90 dias + auxílio-moradia do ano ÷ meses decorridos.
- **Totais da cota** vêm da página de cada deputado. O arquivo de notas da Câmara não traz as passagens aéreas emitidas pelo sistema da Câmara (SIGEPA); em 2026 a diferença passa de R$ 36 milhões, e o relatório mostra esse número toda semana.
- **Presença na Câmara**: a Câmara publica o motivo da ausência (missão autorizada, licença etc.); só a ausência sem motivo conta como "sem justificativa". A contagem dia a dia bate 100% com os totais oficiais.
- **Presença no Senado** é a participação nas votações nominais, com o código oficial de cada senador.
- **Patrimônio**: deputados são ligados à candidatura pelo CPF do arquivo da cota; o CPF é usado só na ligação e nunca é gravado nem exibido. Senadores são ligados por nome completo e estado, conferindo que cada um foi candidato ao Senado no próprio estado. O site mostra totais por tipo de bem, nunca a descrição de cada bem.
- **Partido** é o da data da coleta; o histórico de trocas fica guardado.
- **Correções** são publicadas com data em [`dp/errata.json`](dp/errata.json) e nunca apagadas.

## Estrutura

```
dp/
  config.py            partidos acompanhados, fontes, semana de referência
  db.py                banco SQLite (data/dinheiro.db)
  coleta.py            coleta semanal (Câmara, Senado, TSE)
  fontes/              leitura de cada fonte (camara, senado, tse, fotos)
  metricas.py          números do relatório semanal
  relatorio.py         relatório em Markdown e HTML
  referencias.json     valores do dia a dia com fonte e data
  errata.json          correções publicadas
  site/                gerador do site (dados, gráficos, templates, CSS, JS)
tests/                 testes com amostras reais das fontes
PRODUCT.md             para quem é e para que serve
DESIGN.md              sistema visual ("Encarte do Povo")
```

Ficam fora do repositório: `data/` (banco e downloads), `public/`, `artefato/` e `relatorios/`, que são gerados pela coleta e pelo build.

## Limitações conhecidas

- Senado: ainda sem subsídio, verba de gabinete e benefícios (não publicados num formato coletável); o custo do Senado é só a cota.
- Republicanos, Novo e Missão não têm logo com licença livre no Wikimedia Commons e aparecem com o selo da sigla.
- O site ainda não tem hospedagem; roda localmente ou como artefato privado do claude.ai.

## Próximos passos

- Senado completo (subsídio, gabinete, benefícios) quando houver fonte coletável.
- Emendas parlamentares (Portal da Transparência).
- Monitor de redes sociais dos parlamentares (contas públicas, APIs oficiais).
- Cards prontos para Instagram, TikTok e Kwai a partir do relatório de sábado.
- Hospedagem e coleta automática semanal.
- Nova legislatura em fevereiro de 2027: a filiação com data já preserva o histórico.

## Créditos e licenças

- Dados: Câmara dos Deputados, Senado Federal, TSE e as fontes de referência citadas.
- Fotos: oficiais da Câmara e do Senado.
- Logos de PL, Progressistas, MDB e Podemos: Wikimedia Commons, domínio público ([`dp/site/static/partidos/LICENCAS.json`](dp/site/static/partidos/LICENCAS.json)).
- Fonte tipográfica: Archivo, SIL Open Font License.
- Licença do código: a definir.
