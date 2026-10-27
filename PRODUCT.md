# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.9 + SQLite + Jinja2 gerando HTML estático (sem framework de front-end). Coleta em `dp/coleta.py`, métricas em `dp/metricas.py`, relatório em `dp/relatorio.py`. Roda só localmente por enquanto; hospedagem ainda não decidida.

## Users

Pessoas comuns, inclusive jovens e quem não acompanha política, que chegam ao site pelo link de um post semanal no Instagram, TikTok ou Kwai, quase sempre no celular. Querem entender rápido quanto um parlamentar custa, se ele comparece e como vota, sem precisar saber o que é "cota parlamentar". A equipe do projeto também usa o site para montar os posts de sábado.

## Product Purpose

"Dinheiro do Povo" mostra, com dados oficiais, quanto custam e como trabalham os deputados e senadores de PL, PP, Republicanos, MDB, Podemos, Novo e Missão: salário, cota parlamentar, verba de gabinete, benefícios, presença, votações e patrimônio declarado. Sucesso é uma pessoa leiga entender o tamanho do gasto e conseguir conferir cada número na fonte oficial.

## Positioning

Cada número vem de fonte oficial (Câmara, Senado, TSE) com link para conferência, é comparado com a média da Casa inteira e é traduzido em referências do dia a dia (salário mínimo, cesta básica etc.) com a fonte da referência. Sem opinião, sem adjetivos: o dado fala.

## Operating Context

- Relatório semanal publicado aos sábados, cobrindo sábado a sexta anteriores.
- Coleta local: `python -m dp.coleta`, depois `python -m dp.relatorio`.
- Posts nas redes apontam para páginas do site.
- Dados mudam com atraso oficial (cota até 90 dias; verba de gabinete mais).

## Capabilities and Constraints

- Fontes: API Dados Abertos da Câmara, páginas oficiais dos deputados (presença e "recursos e benefícios"), CSV da cota (CEAP), Dados Abertos do Senado, CSV da CEAPS, TSE (bens declarados).
- O arquivo de notas da Câmara não traz passagens do SIGEPA; totais anuais vêm da página do deputado.
- Senado ainda sem subsídio, verba de gabinete e benefícios.
- Partido é o da data da coleta; trocas de partido preservadas no histórico.
- CPF não é exibido nem armazenado para exibição.

## Brand Commitments

- Nome: Dinheiro do Povo.
- Tom: igual a um portal de transparência pública. Sem sensacionalismo, sem fake news, sem adjetivos sobre pessoas. "O poder emana do povo" é a motivação, não o tom do texto.
- Logos de partidos: apenas os disponíveis no Wikimedia Commons com licença livre, com licença registrada; sem logo livre, selo com a sigla.
- Fotos: fotos oficiais publicadas pela Câmara e pelo Senado.

## Evidence on Hand

- Banco local `data/dinheiro.db` com 513 deputados, 81 senadores, CEAP/CEAPS 2026, presença e votações.
- Relatório real gerado: `relatorios/2026-10-17.md` / `.html`.
- Não existem depoimentos, parcerias, selos ou números de audiência; não inventar.

## Product Principles

1. Fonte em cada número. Se não há fonte oficial, o número não entra.
2. Comparar antes de julgar: todo valor aparece ao lado da média da Casa ou de uma referência do dia a dia.
3. Entendível por um adolescente no celular em poucos segundos; o detalhe técnico fica um toque abaixo.
4. Neutralidade: o mesmo tratamento para todo parlamentar e partido.
5. Limites ditos em voz alta: atrasos, lacunas e métodos aparecem junto do dado.

## Accessibility & Inclusion

Público leigo e jovem, majoritariamente em celular: linguagem simples, números grandes e legíveis, contraste alto, gráficos com texto equivalente, nada que dependa só de cor.
