"""Coleta semanal.

Uso:
    python -m dp.coleta                      # semana do último sábado
    python -m dp.coleta --semana 2026-10-17  # relatório do sábado 17/10 (cobre 10 a 16/10)
    python -m dp.coleta --casa senado
    python -m dp.coleta --sem-paginas-oficiais
"""
import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

from dp import config, db
from dp.fontes import camara, senado, tse


def _agora():
    return datetime.now().isoformat(timespec="seconds")


class Etapa:
    """Registra início, fim e resultado de cada etapa em coleta_log."""

    def __init__(self, conn, nome):
        self.conn, self.nome, self.detalhes = conn, nome, {}

    def __enter__(self):
        cur = self.conn.execute(
            "INSERT INTO coleta_log (etapa, iniciado_em) VALUES (?, ?)", (self.nome, _agora()))
        self.id = cur.lastrowid
        self.conn.commit()
        print(f"> {self.nome}...", flush=True)
        return self

    def __exit__(self, tipo, erro, _tb):
        status = "ok" if erro is None else f"erro: {erro}"
        self.conn.execute(
            "UPDATE coleta_log SET terminado_em=?, status=?, detalhes=? WHERE id=?",
            (_agora(), status, json.dumps(self.detalhes, ensure_ascii=False), self.id))
        self.conn.commit()
        print(f"  {status} {self.detalhes}", flush=True)
        return False


# --- Gravação ---------------------------------------------------------------

def salvar_deputados(conn, deputados, hoje: str):
    for d in deputados:
        p = camara.pid(d["id"])
        conn.execute(
            """INSERT INTO parlamentar (id, casa, id_externo, nome, uf, url_foto, url_perfil, atualizado_em)
               VALUES (?, 'camara', ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, uf=excluded.uf,
                   url_foto=excluded.url_foto, atualizado_em=excluded.atualizado_em""",
            (p, str(d["id"]), d["nome"], d["siglaUf"], d["urlFoto"],
             config.CAMARA_PERFIL.format(id=d["id"]), hoje))
        conn.execute(
            "INSERT OR REPLACE INTO filiacao (parlamentar_id, partido, visto_em) VALUES (?, ?, ?)",
            (p, d["siglaPartido"], hoje))


def salvar_despesas(conn, linhas, casa: str, hoje: str):
    """Upsert das notas. `primeira_vez_vista` nunca é sobrescrita.

    Na primeira carga de uma Casa, as notas recebem carga_inicial=1 e não
    contam como "lançadas na semana".
    """
    carga_inicial = conn.execute(
        "SELECT COUNT(*) FROM despesa WHERE casa=?", (casa,)).fetchone()[0] == 0
    novas = total = 0
    for d in linhas:
        total += 1
        cur = conn.execute(
            """INSERT INTO despesa (chave, casa, parlamentar_id, nome_na_nota, partido_na_nota, uf,
                   data_emissao, ano, mes, categoria, fornecedor, cnpj, valor_documento, valor_glosa,
                   valor_liquido, trecho, url_documento, primeira_vez_vista, ultima_vez_vista, carga_inicial)
               VALUES (:chave, :casa, :parlamentar_id, :nome_na_nota, :partido_na_nota, :uf,
                   :data_emissao, :ano, :mes, :categoria, :fornecedor, :cnpj, :valor_documento, :valor_glosa,
                   :valor_liquido, :trecho, :url_documento, :hoje, :hoje, :carga)
               ON CONFLICT(chave) DO NOTHING""",
            dict(d, hoje=hoje, carga=int(carga_inicial)))
        if cur.rowcount:
            novas += 1
        else:
            conn.execute(
                """UPDATE despesa SET ultima_vez_vista=?, valor_glosa=?, partido_na_nota=?
                   WHERE chave=?""",
                (hoje, d["valor_glosa"], d["partido_na_nota"], d["chave"]))
    return {"linhas": total, "novas": novas, "carga_inicial": carga_inicial}


def salvar_sessao_camara(conn, evento, presentes):
    sid = f"camara:{evento['id']}"
    conn.execute(
        """INSERT OR REPLACE INTO sessao (id, casa, inicio, tipo, situacao, descricao, url_fonte)
           VALUES (?, 'camara', ?, ?, ?, ?, ?)""",
        (sid, evento["dataHoraInicio"], evento["descricaoTipo"], evento["situacao"],
         evento["descricao"], evento["uri"]))
    conn.executemany(
        "INSERT OR IGNORE INTO presenca_sessao (sessao_id, parlamentar_id) VALUES (?, ?)",
        [(sid, camara.pid(p["id"])) for p in presentes])


def salvar_presenca_oficial(conn, dep_id, ano, dias, resumo, hoje):
    p = camara.pid(dep_id)
    url = config.CAMARA_PRESENCA.format(id=dep_id, ano=ano)
    conn.executemany(
        """INSERT OR REPLACE INTO presenca_dia
           (parlamentar_id, data, status, categoria, url_fonte, coletado_em)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(p, d["data"], d["status"], d["categoria"], url, hoje) for d in dias])
    conn.executemany(
        """INSERT OR REPLACE INTO presenca_resumo_oficial
           (parlamentar_id, ano, indicador, valor, percentual, url_fonte, coletado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(p, ano, r["indicador"], r["valor"], r["percentual"], url, hoje) for r in resumo])


def salvar_recursos_oficiais(conn, dep_id, ano, itens, atualizado_fonte, hoje):
    p = camara.pid(dep_id)
    url = config.CAMARA_PERFIL_ANO.format(id=dep_id, ano=ano)
    conn.executemany(
        """INSERT OR REPLACE INTO recurso_oficial
           (parlamentar_id, ano, item, valor, texto, url_fonte, atualizado_fonte, coletado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(p, ano, i["item"], i["valor"], i["texto"], url, atualizado_fonte, hoje) for i in itens])


def salvar_votacao_camara(conn, v, votos):
    vid = f"camara:{v['id']}"
    sessao = v.get("uriEvento") or ""
    conn.execute(
        """INSERT OR REPLACE INTO votacao (id, casa, data, descricao, aprovada, sessao_id, url_fonte)
           VALUES (?, 'camara', ?, ?, ?, ?, ?)""",
        (vid, v["data"], v["descricao"], v.get("aprovacao"),
         f"camara:{sessao.rsplit('/', 1)[-1]}" if sessao else None, v["uri"]))
    conn.executemany(
        "INSERT OR REPLACE INTO voto (votacao_id, parlamentar_id, voto) VALUES (?, ?, ?)",
        [(vid, camara.pid(x["deputado_"]["id"]), x["tipoVoto"]) for x in votos])


def salvar_senadores(conn, em_exercicio, da_legislatura, hoje: str):
    """Grava todos os senadores da legislatura (para atribuir despesas de quem
    já saiu) e registra a filiação apenas de quem está em exercício."""
    for s in da_legislatura + em_exercicio:  # em exercício por último: dados mais completos
        ident = s["IdentificacaoParlamentar"]
        cod = ident["CodigoParlamentar"]
        conn.execute(
            """INSERT INTO parlamentar (id, casa, id_externo, nome, uf, url_foto, url_perfil, atualizado_em)
               VALUES (?, 'senado', ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET nome=excluded.nome,
                   uf=COALESCE(excluded.uf, parlamentar.uf),
                   url_foto=COALESCE(excluded.url_foto, parlamentar.url_foto),
                   url_perfil=COALESCE(excluded.url_perfil, parlamentar.url_perfil),
                   atualizado_em=excluded.atualizado_em""",
            (senado.pid(cod), cod, ident["NomeParlamentar"], ident.get("UfParlamentar"),
             ident.get("UrlFotoParlamentar"), ident.get("UrlPaginaParlamentar"), hoje))
    for s in em_exercicio:
        ident = s["IdentificacaoParlamentar"]
        conn.execute(
            "INSERT OR REPLACE INTO filiacao (parlamentar_id, partido, visto_em) VALUES (?, ?, ?)",
            (senado.pid(ident["CodigoParlamentar"]), ident["SiglaPartidoParlamentar"], hoje))


def salvar_votacao_senado(conn, v):
    vid = f"senado:{v['codigoSessaoVotacao']}"
    sid = f"senado:{v['codigoSessao']}"
    conn.execute(
        """INSERT OR REPLACE INTO sessao (id, casa, inicio, tipo, situacao, descricao, url_fonte)
           VALUES (?, 'senado', ?, ?, NULL, ?, NULL)""",
        (sid, v["dataSessao"], v.get("siglaTipoSessao"), f"Sessão nº {v.get('numeroSessao')}"))
    url = (f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{v['codigoMateria']}"
           if v.get("codigoMateria") else None)
    conn.execute(
        """INSERT OR REPLACE INTO votacao (id, casa, data, descricao, aprovada, sessao_id, url_fonte)
           VALUES (?, 'senado', ?, ?, ?, ?, ?)""",
        (vid, v["dataSessao"], f"{v.get('identificacao') or ''} {v.get('descricaoVotacao') or ''}".strip(),
         {"A": 1, "R": 0}.get(v.get("resultadoVotacao")), sid, url))
    conn.executemany(
        "INSERT OR REPLACE INTO voto (votacao_id, parlamentar_id, voto) VALUES (?, ?, ?)",
        [(vid, senado.pid(x["codigoParlamentar"]), x["siglaVotoParlamentar"]) for x in v["votos"]])


# --- Orquestração -----------------------------------------------------------

def _em_paralelo(funcao, ids, workers=4):
    """Executa `funcao(id)` em poucas threads (para não sobrecarregar o site).

    Gera (id, (resultado, erro)); um deputado com problema não para a coleta.
    """
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futuros = {ex.submit(funcao, i): i for i in ids}
        for f in as_completed(futuros):
            try:
                yield futuros[f], (f.result(), None)
            except Exception as erro:
                yield futuros[f], (None, str(erro)[:200])


def coletar_camara(conn, inicio, fim, paginas_oficiais=True):
    hoje = date.today().isoformat()

    with Etapa(conn, "camara.deputados") as e:
        deps = camara.deputados_em_exercicio()
        salvar_deputados(conn, deps, hoje)
        monitorados = [d for d in deps if d["siglaPartido"] in config.PARTIDOS_MONITORADOS]
        e.detalhes = {"total": len(deps), "monitorados": len(monitorados)}

    anos = sorted({inicio.year, fim.year, date.today().year})
    for ano in anos:
        with Etapa(conn, f"camara.ceap.{ano}") as e:
            e.detalhes = salvar_despesas(conn, camara.ler_ceap(camara.baixar_ceap(ano)), "camara", hoje)

    with Etapa(conn, "camara.sessoes") as e:
        eventos = camara.sessoes_deliberativas(inicio, fim)
        for ev in eventos:
            salvar_sessao_camara(conn, ev, camara.presentes_na_sessao(ev["id"]))
        e.detalhes = {"sessoes": len(eventos)}

    with Etapa(conn, "camara.votacoes") as e:
        vs = camara.votacoes_plenario(inicio, fim)
        nominais = 0
        for v in vs:
            lista = camara.votos(v["id"])
            nominais += bool(lista)
            salvar_votacao_camara(conn, v, lista)
        e.detalhes = {"votacoes": len(vs), "nominais": nominais}

    if not paginas_oficiais:
        conn.commit()
        return

    # Páginas de todos os deputados em exercício (não só dos monitorados):
    # a média da Câmara usada nas comparações vem da mesma fonte.
    ids = [d["id"] for d in deps]
    for ano in sorted({inicio.year, fim.year}):
        with Etapa(conn, f"camara.presenca_oficial.{ano}") as e:
            def presenca(dep_id, ano=ano):
                return camara.ler_pagina_presenca(camara.baixar_pagina_presenca(dep_id, ano))
            falhas = []
            for dep_id, (dados, erro) in _em_paralelo(presenca, ids):
                if erro:
                    falhas.append({"id": dep_id, "erro": erro})
                else:
                    salvar_presenca_oficial(conn, dep_id, ano, *dados, hoje)
            conn.commit()
            e.detalhes = {"deputados": len(ids) - len(falhas), "falhas": falhas}

    ano = fim.year
    with Etapa(conn, f"camara.perfil_oficial.{ano}") as e:
        falhas = []
        for dep_id, (dados, erro) in _em_paralelo(
                lambda i: camara.ler_pagina_perfil(camara.baixar_pagina_perfil(i, ano)), ids):
            if erro:
                falhas.append({"id": dep_id, "erro": erro})
            else:
                salvar_recursos_oficiais(conn, dep_id, ano, *dados, hoje)
        conn.commit()
        e.detalhes = {"deputados": len(ids) - len(falhas), "falhas": falhas}


def coletar_senado(conn, inicio, fim):
    hoje = date.today().isoformat()

    with Etapa(conn, "senado.senadores") as e:
        atuais = senado.senadores_em_exercicio()
        legislatura = senado.senadores_da_legislatura(57)
        salvar_senadores(conn, atuais, legislatura, hoje)
        monitorados = [s for s in atuais
                       if s["IdentificacaoParlamentar"]["SiglaPartidoParlamentar"] in config.PARTIDOS_MONITORADOS]
        e.detalhes = {"em_exercicio": len(atuais), "legislatura": len(legislatura),
                      "monitorados": len(monitorados)}

    indice = senado.indice_de_nomes(legislatura + atuais)
    for ano in sorted({inicio.year, fim.year, date.today().year}):
        with Etapa(conn, f"senado.ceaps.{ano}") as e:
            linhas = list(senado.ler_ceaps(senado.baixar_ceaps(ano), indice))
            e.detalhes = salvar_despesas(conn, linhas, "senado", hoje)
            e.detalhes["nomes_sem_senador"] = sorted(
                {l["nome_na_nota"] for l in linhas if l["parlamentar_id"] is None})

    # Desde 1º de janeiro: o relatório também mostra a participação no ano.
    # (A API aceita até 1 ano por consulta.)
    with Etapa(conn, "senado.votacoes") as e:
        vs = senado.votacoes(date(fim.year, 1, 1), fim)
        for v in vs:
            salvar_votacao_senado(conn, v)
        e.detalhes = {"votacoes": len(vs), "codigos_desconhecidos": sorted(
            {x["siglaVotoParlamentar"] for v in vs for x in v["votos"]
             if senado.classificar_voto(x["siglaVotoParlamentar"]) == "desconhecido"})}
    conn.commit()


ANOS_TSE = (2018, 2022, 2026)


def vincular_candidaturas(deputados, senadores, cpfs, candidaturas):
    """{parlamentar_id: ([candidaturas], metodo)}.

    Deputados: pelo CPF do CSV da cota (o mais seguro). Sem CPF, e para
    senadores (o Senado não publica CPF): nome completo + UF; depois nome de
    urna + UF. Um nome que aponta para mais de uma pessoa não é vinculado.
    """
    por_cpf, por_nome, por_urna = defaultdict(list), defaultdict(list), defaultdict(list)
    for c in candidaturas:
        por_cpf[c["cpf"].zfill(11)].append(c)
        por_nome[(senado.normalizar_nome(c["nome"]), c["uf"])].append(c)
        por_urna[(senado.normalizar_nome(c["nome_urna"]), c["uf"])].append(c)

    def por_nomes(nome_completo, nome_urna, uf):
        for indice, nome in ((por_nome, nome_completo), (por_urna, nome_urna)):
            if not nome:
                continue
            achadas = indice.get((senado.normalizar_nome(nome), uf), [])
            if achadas and len({c["cpf"] for c in achadas}) == 1:
                return achadas
        return []

    vinculos = {}
    for d in deputados:
        cpf = cpfs.get(str(d["id"]))
        if cpf and por_cpf.get(cpf):
            vinculos[camara.pid(d["id"])] = (por_cpf[cpf], "cpf")
        else:
            achadas = por_nomes(None, d["nome"], d["siglaUf"])
            if achadas:
                vinculos[camara.pid(d["id"])] = (achadas, "nome+uf")
    for s in senadores:
        ident = s["IdentificacaoParlamentar"]
        achadas = por_nomes(ident.get("NomeCompletoParlamentar"), ident.get("NomeParlamentar"),
                            ident.get("UfParlamentar"))
        if achadas:
            # o mesmo CPF pode ter outras candidaturas com nome grafado de outro jeito
            cpf = achadas[0]["cpf"].zfill(11)
            vinculos[senado.pid(ident["CodigoParlamentar"])] = (por_cpf[cpf], "nome+uf")
    return vinculos


def salvar_patrimonio(conn, vinculos, bens_por_ano):
    n = 0
    for pid, (candidaturas, metodo) in vinculos.items():
        # Duas candidaturas no mesmo ano (ex.: registro substituído): vale a que tem bens.
        por_ano = {}
        for c in candidaturas:
            bens = bens_por_ano[c["ano"]].get(c["sq"])
            total = bens["total"] if bens else 0.0
            if c["ano"] not in por_ano or total > por_ano[c["ano"]][2]:
                por_ano[c["ano"]] = (c, bens, total)
        for c, bens, total in por_ano.values():
            conn.execute(
                """INSERT OR REPLACE INTO patrimonio
                   (parlamentar_id, ano_eleicao, cargo, situacao, partido, total, metodo, url_fonte)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, c["ano"], c["cargo"], c["situacao"], c["partido"], total, metodo,
                 tse.url_bens(c["ano"])))
            conn.execute("DELETE FROM patrimonio_tipo WHERE parlamentar_id=? AND ano_eleicao=?",
                         (pid, c["ano"]))
            if bens:
                conn.executemany(
                    "INSERT INTO patrimonio_tipo VALUES (?, ?, ?, ?)",
                    [(pid, c["ano"], tipo, v) for tipo, v in bens["por_tipo"].items()])
            n += 1
    return n


def coletar_patrimonio(conn):
    with Etapa(conn, "tse.patrimonio") as e:
        candidaturas, bens_por_ano = [], {}
        for ano in ANOS_TSE:
            candidaturas += tse.ler_candidaturas(tse.baixar("consulta_cand", ano))
            bens_por_ano[ano] = tse.somar_bens(tse.baixar("bem_candidato", ano))
        deputados = camara.deputados_em_exercicio()
        senadores = senado.senadores_em_exercicio()
        cpfs = tse.cpfs_dos_deputados(camara.baixar_ceap(date.today().year))
        vinculos = vincular_candidaturas(deputados, senadores, cpfs, candidaturas)
        n = salvar_patrimonio(conn, vinculos, bens_por_ano)
        conn.commit()
        e.detalhes = {
            "deputados_vinculados": sum(k.startswith("camara:") for k in vinculos),
            "senadores_vinculados": sum(k.startswith("senado:") for k in vinculos),
            "por_nome": sum(m == "nome+uf" for _, m in vinculos.values()),
            "declaracoes": n,
            "sem_vinculo": sorted(
                [d["nome"] for d in deputados if camara.pid(d["id"]) not in vinculos]
                + [s["IdentificacaoParlamentar"]["NomeParlamentar"] for s in senadores
                   if senado.pid(s["IdentificacaoParlamentar"]["CodigoParlamentar"]) not in vinculos]),
        }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Coleta semanal do Dinheiro do Povo")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--casa", choices=["camara", "senado", "tse", "todas"], default="todas")
    ap.add_argument("--sem-paginas-oficiais", action="store_true",
                    help="Pula as páginas de presença e de perfil dos deputados (≈1.000 requisições).")
    ap.add_argument("--db", default=None, help="Caminho alternativo do banco")
    args = ap.parse_args(argv)

    inicio, fim = config.semana_referencia(args.semana)
    print(f"Relatório de {args.semana:%d/%m/%Y}: semana de {inicio:%d/%m} a {fim:%d/%m/%Y}")
    conn = db.conectar(args.db)
    if args.casa in ("camara", "todas"):
        coletar_camara(conn, inicio, fim, paginas_oficiais=not args.sem_paginas_oficiais)
    if args.casa in ("senado", "todas"):
        coletar_senado(conn, inicio, fim)
    if args.casa in ("tse", "todas"):
        coletar_patrimonio(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
