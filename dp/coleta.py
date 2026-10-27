"""Coleta semanal.

Uso:
    python -m dp.coleta                      # semana do último sábado
    python -m dp.coleta --semana 2026-10-17  # relatório do sábado 17/10 (cobre 10 a 16/10)
    python -m dp.coleta --casa senado
    python -m dp.coleta --sem-presenca-oficial
"""
import argparse
import json
import sys
from datetime import date, datetime

from dp import config, db
from dp.fontes import camara, senado


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

def coletar_camara(conn, inicio, fim, presenca_oficial=True):
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

    if presenca_oficial:
        for ano in sorted({inicio.year, fim.year}):
            with Etapa(conn, f"camara.presenca_oficial.{ano}") as e:
                falhas = []
                for d in monitorados:
                    try:
                        dias, resumo = camara.ler_pagina_presenca(camara.baixar_pagina_presenca(d["id"], ano))
                        salvar_presenca_oficial(conn, d["id"], ano, dias, resumo, hoje)
                    except Exception as erro:  # um deputado com problema não para a coleta
                        falhas.append({"id": d["id"], "erro": str(erro)[:200]})
                conn.commit()
                e.detalhes = {"deputados": len(monitorados) - len(falhas), "falhas": falhas}
    conn.commit()


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

    with Etapa(conn, "senado.votacoes") as e:
        vs = senado.votacoes(inicio, fim)
        for v in vs:
            salvar_votacao_senado(conn, v)
        e.detalhes = {"votacoes": len(vs), "codigos_desconhecidos": sorted(
            {x["siglaVotoParlamentar"] for v in vs for x in v["votos"]
             if senado.classificar_voto(x["siglaVotoParlamentar"]) == "desconhecido"})}
    conn.commit()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Coleta semanal do Dinheiro do Povo")
    ap.add_argument("--semana", type=date.fromisoformat, default=config.ultimo_sabado(),
                    help="Sábado do relatório (AAAA-MM-DD). Padrão: último sábado.")
    ap.add_argument("--casa", choices=["camara", "senado", "todas"], default="todas")
    ap.add_argument("--sem-presenca-oficial", action="store_true",
                    help="Pula as páginas de presença (≈260 requisições).")
    ap.add_argument("--db", default=None, help="Caminho alternativo do banco")
    args = ap.parse_args(argv)

    inicio, fim = config.semana_referencia(args.semana)
    print(f"Relatório de {args.semana:%d/%m/%Y}: semana de {inicio:%d/%m} a {fim:%d/%m/%Y}")
    conn = db.conectar(args.db)
    if args.casa in ("camara", "todas"):
        coletar_camara(conn, inicio, fim, presenca_oficial=not args.sem_presenca_oficial)
    if args.casa in ("senado", "todas"):
        coletar_senado(conn, inicio, fim)
    return 0


if __name__ == "__main__":
    sys.exit(main())
