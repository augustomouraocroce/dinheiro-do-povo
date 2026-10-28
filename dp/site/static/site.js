// Dinheiro do Povo: busca por nome/partido, dicas dos gráficos e filtro de listas.
(function () {
  "use strict";
  var raiz = document.documentElement.getAttribute("data-raiz") || "";

  function normalizar(t) {
    return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  // ---------- Busca ----------
  var campo = document.getElementById("busca-campo");
  var caixa = document.getElementById("busca-resultados");
  var indice = (window.DP_INDICE || []).map(function (i) {
    i._chave = normalizar([i.nome, i.partido, i.partido_nome, i.uf, i.cargo].join(" "));
    return i;
  });
  var selecionado = -1;

  function desenhar(lista, termo) {
    caixa.innerHTML = "";
    if (!termo) { caixa.classList.remove("aberta"); campo.setAttribute("aria-expanded", "false"); return; }
    if (!lista.length) {
      var vazio = document.createElement("p");
      vazio.className = "busca-vazio";
      vazio.textContent = "Ninguém encontrado com “" + termo + "” entre os partidos acompanhados.";
      caixa.appendChild(vazio);
    }
    lista.slice(0, 12).forEach(function (i, n) {
      var a = document.createElement("a");
      a.href = raiz + i.url;
      a.id = "busca-op-" + n;
      a.setAttribute("role", "option");
      if (i.tipo === "partido") {
        a.innerHTML = '<span class="selo">' + i.partido + "</span><span><span class=\"r-nome\"></span><br><span class=\"r-info\">Partido</span></span><span></span>";
        a.querySelector(".r-nome").textContent = i.partido_nome;
      } else {
        a.innerHTML = (i.sprite ? '<span class="foto-s r-foto" aria-hidden="true"></span>' : '<img alt="" loading="lazy">') +
          '<span><span class="r-nome"></span><br><span class="r-info"></span></span><span class="r-partido"></span>';
        if (i.sprite) a.querySelector(".foto-s").style.backgroundPosition = i.sprite;
        else a.querySelector("img").src = raiz + i.foto;
        a.querySelector(".r-nome").textContent = i.nome;
        a.querySelector(".r-info").textContent = i.cargo + " · " + i.uf;
        a.querySelector(".r-partido").textContent = i.partido;
      }
      caixa.appendChild(a);
    });
    caixa.classList.add("aberta");
    campo.setAttribute("aria-expanded", "true");
    selecionado = -1;
  }

  function buscar() {
    var termo = campo.value;
    var t = normalizar(termo);
    if (!t) return desenhar([], "");
    var partes = t.split(/\s+/);
    var achados = indice.filter(function (i) {
      return partes.every(function (p) { return i._chave.indexOf(p) !== -1; });
    });
    achados.sort(function (a, b) {
      var pa = a.tipo === "partido" && normalizar(a.partido) === t ? 0 : 1;
      var pb = b.tipo === "partido" && normalizar(b.partido) === t ? 0 : 1;
      return pa - pb || a._chave.localeCompare(b._chave);
    });
    desenhar(achados, termo);
  }

  if (campo && caixa) {
    campo.addEventListener("input", buscar);
    campo.addEventListener("focus", function () { if (campo.value) buscar(); });
    campo.addEventListener("keydown", function (e) {
      var ops = caixa.querySelectorAll("a");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!ops.length) return;
        e.preventDefault();
        selecionado = (selecionado + (e.key === "ArrowDown" ? 1 : -1) + ops.length) % ops.length;
        ops.forEach(function (o, n) { o.setAttribute("aria-selected", n === selecionado ? "true" : "false"); });
        campo.setAttribute("aria-activedescendant", ops[selecionado].id);
        ops[selecionado].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        var alvo = ops[selecionado >= 0 ? selecionado : 0];
        if (alvo) { e.preventDefault(); window.location.href = alvo.href; }
      } else if (e.key === "Escape") {
        campo.value = ""; desenhar([], "");
      }
    });
    document.addEventListener("click", function (e) {
      if (!caixa.contains(e.target) && e.target !== campo) caixa.classList.remove("aberta");
    });
    // Atalho "/" foca a busca
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== campo && !/input|textarea/i.test(document.activeElement.tagName)) {
        e.preventDefault(); campo.focus();
      }
    });
    // O botão "Buscar" da navegação de baixo leva o foco para o campo
    document.querySelectorAll("[data-focar-busca]").forEach(function (b) {
      b.addEventListener("click", function (e) { e.preventDefault(); window.scrollTo({ top: 0 }); campo.focus(); });
    });
  }

  // ---------- Dicas dos gráficos ----------
  var dica = document.createElement("div");
  dica.className = "dica";
  dica.setAttribute("role", "status");
  document.body.appendChild(dica);
  function mostrar(alvo, x, y) {
    dica.textContent = alvo.getAttribute("data-tip");
    dica.classList.add("visivel");
    var r = dica.getBoundingClientRect();
    var left = Math.min(Math.max(8, x - r.width / 2), window.innerWidth - r.width - 8);
    var top = y - r.height - 12;
    if (top < 8) top = y + 16;
    dica.style.left = left + "px";
    dica.style.top = top + "px";
  }
  function esconder() { dica.classList.remove("visivel"); }
  document.addEventListener("pointermove", function (e) {
    var alvo = e.target.closest && e.target.closest("[data-tip]");
    if (alvo) mostrar(alvo, e.clientX, e.clientY); else esconder();
  });
  document.addEventListener("focusin", function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute("data-tip")) {
      var r = e.target.getBoundingClientRect();
      mostrar(e.target, r.left + r.width / 2, r.top);
    }
  });
  document.addEventListener("focusout", esconder);
  window.addEventListener("scroll", esconder, { passive: true });

  // ---------- Filtro de listas (página de partido) ----------
  document.querySelectorAll("[data-filtro]").forEach(function (entrada) {
    var alvo = document.getElementById(entrada.getAttribute("data-filtro"));
    var contador = document.getElementById(entrada.getAttribute("data-contador"));
    entrada.addEventListener("input", function () {
      var t = normalizar(entrada.value), n = 0;
      alvo.querySelectorAll("[data-busca]").forEach(function (el) {
        var ok = !t || el.getAttribute("data-busca").indexOf(t) !== -1;
        el.hidden = !ok; if (ok) n++;
      });
      if (contador) contador.textContent = n;
    });
  });

  function el(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto != null) e.textContent = texto;
    return e;
  }

  function linkExterno(texto, url) {
    var a = el("a", null, texto);
    a.href = url; a.target = "_blank"; a.rel = "noopener";
    return a;
  }

  // ---------- Como votou (votos.html) ----------
  // O endereço guarda os filtros: votos.html?p=fulano&voto=nao&tipo=principal&q=imposto
  var cvForm = document.getElementById("cv-form");
  if (cvForm) {
    var cvPessoa = document.getElementById("cv-pessoa");
    var cvBusca = document.getElementById("cv-busca");
    var cvCab = document.getElementById("cv-cab");
    var cvContagem = document.getElementById("cv-contagem");
    var cvLista = document.getElementById("cv-lista");
    var cvMais = document.getElementById("cv-mais");
    var POR_VEZ = 20;
    var ROTULO = { S: "Sim", N: "Não" };
    var NOME_FILTRO = { sim: " “Sim”", nao: " “Não”", outros: " de outro tipo", todos: "" };
    var indice = null, pessoa = null, cache = {}, grupos = [], mostrando = 0, espera = null;

    var json = function (url) {
      return fetch(raiz + url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    };
    var marcado = function (nome) {
      var i = cvForm.querySelector('input[name="' + nome + '"]:checked');
      return i ? i.value : "todos";
    };
    var marcar = function (nome, valor) {
      var i = cvForm.querySelector('input[name="' + nome + '"][value="' + valor + '"]');
      if (i) i.checked = true;
    };
    var classe = function (v) { return v === "S" ? "sim" : v === "N" ? "nao" : "outros"; };
    var dataBr = function (d) { return d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4); };
    var pct = function (n, t) { return t ? Math.round(100 * n / t) + "%" : "0%"; };
    var plural = function (n, um, varios) { return n.toLocaleString("pt-BR") + " " + (n === 1 ? um : varios); };

    var pedido = new URLSearchParams(window.location.search);
    if (pedido.get("voto")) marcar("voto", pedido.get("voto"));
    if (pedido.get("tipo")) marcar("tipo", pedido.get("tipo"));
    if (pedido.get("q")) cvBusca.value = pedido.get("q");
    if (pedido.get("p")) cvPessoa.value = pedido.get("p");

    var guardarEndereco = function () {
      var u = new URLSearchParams();
      if (cvPessoa.value) u.set("p", cvPessoa.value);
      if (marcado("voto") !== "todos") u.set("voto", marcado("voto"));
      if (marcado("tipo") !== "todos") u.set("tipo", marcado("tipo"));
      if (cvBusca.value.trim()) u.set("q", cvBusca.value.trim());
      var s = u.toString();
      window.history.replaceState(null, "", window.location.pathname + (s ? "?" + s : ""));
    };

    var desenharCabecalho = function () {
      var op = cvPessoa.options[cvPessoa.selectedIndex];
      var votos = pessoa.dados.votos, c = { S: 0, N: 0, O: 0 };
      votos.forEach(function (v) { c[v[1] === "S" || v[1] === "N" ? v[1] : "O"]++; });
      var t = votos.length;
      cvCab.innerHTML = "";
      var topo = el("div", "cv-pessoa");
      var foto = el("img");
      foto.src = raiz + "fotos/mini/" + pessoa.slug + ".jpg"; foto.alt = ""; foto.width = 120; foto.height = 160;
      var nome = el("a", "rk-nome", op.getAttribute("data-nome"));
      nome.href = raiz + "p/" + pessoa.slug + ".html";
      nome.appendChild(el("small", null, op.getAttribute("data-partido") + "-" + op.getAttribute("data-uf")));
      topo.appendChild(foto); topo.appendChild(nome);
      cvCab.appendChild(topo);
      cvCab.appendChild(el("p", null, plural(t, "voto nominal", "votos nominais") + " no Plenário desde 2023."));
      var partes = [["S", "Sim", "sim"], ["N", "Não", "nao"], ["O", "Outros", "outros"]];
      var barra = el("div", "cv-barra");
      barra.setAttribute("role", "img");
      barra.setAttribute("aria-label", partes.map(function (k) { return k[1] + " " + pct(c[k[0]], t); }).join(", "));
      var legenda = el("p", "cv-legenda");
      partes.forEach(function (k) {
        if (!c[k[0]]) return;
        var s = el("span", "cv-b-" + k[2]);
        s.style.flexGrow = c[k[0]];
        barra.appendChild(s);
        var item = el("span");
        item.appendChild(el("i", "cv-b-" + k[2]));
        item.appendChild(el("b", null, k[1] + " " + pct(c[k[0]], t)));
        item.appendChild(document.createTextNode(" " + c[k[0]].toLocaleString("pt-BR")));
        legenda.appendChild(item);
      });
      cvCab.appendChild(barra);
      cvCab.appendChild(legenda);
      cvCab.hidden = false;
    };

    var mostrarMais = function () {
      var V = indice.votacoes, P = indice.proposicoes, T = indice.tipos, partidos = pessoa.dados.partidos || {};
      grupos.slice(mostrando, mostrando + POR_VEZ).forEach(function (g) {
        var prop = g.chave === "x" ? null : P[g.chave];
        var art = el("article", "ladrilho proposta cv-prop");
        var cab = el("div", "proposta-cab");
        var h = el("h3");
        if (prop) h.appendChild(linkExterno(prop[0], prop[2])); else h.textContent = "Sem proposta indicada";
        cab.appendChild(h);
        cab.appendChild(el("span", "secundario", plural(g.votos.length, "voto", "votos")));
        art.appendChild(cab);
        if (prop && prop[1]) art.appendChild(el("p", "proposta-ementa", prop[1]));
        var caixa = el("div", "votos");
        g.votos.forEach(function (v) {
          var vt = V[v[0]];
          var linha = el("div", "voto");
          linha.appendChild(el("span", "v v-" + classe(v[1]), ROTULO[v[1]] || v[1]));
          var p = el("p");
          var ex = vt[8] != null ? indice.explicacoes[vt[8]] : null;
          p.appendChild(el("b", "cv-tipo", T[vt[3]][0]));
          var info = dataBr(vt[0]) + (partidos[v[0]] ? ", votou pelo " + partidos[v[0]] : "");
          if (ex) {
            p.appendChild(document.createTextNode(" "));
            p.appendChild(el("b", null, ex[0]));
            p.appendChild(document.createTextNode(" " + ex[1] + (vt[2] ? " Resultado: " + vt[2] + ", " + vt[6] + " a " + vt[7] + "." : "")));
            var oficial = el("span", "voto-oficial", "Texto oficial: " + vt[1] + " (" + info + ")");
            if (vt[5]) { oficial.appendChild(document.createTextNode(" · ")); oficial.appendChild(linkExterno("dados oficiais", vt[5])); }
            p.appendChild(oficial);
          } else {
            p.appendChild(document.createTextNode(" " + vt[1] + " "));
            p.appendChild(el("span", "secundario", "(" + info + ", placar Sim " + vt[6] + " × Não " + vt[7] + ")"));
            if (vt[5]) { p.appendChild(document.createTextNode(" · ")); p.appendChild(linkExterno("dados oficiais", vt[5])); }
          }
          linha.appendChild(p);
          caixa.appendChild(linha);
        });
        art.appendChild(caixa);
        cvLista.appendChild(art);
      });
      mostrando += POR_VEZ;
      var resta = grupos.length - mostrando;
      cvMais.hidden = resta <= 0;
      if (resta > 0) cvMais.textContent = "Mostrar mais " + plural(Math.min(POR_VEZ, resta), "proposta", "propostas") + " (faltam " + resta + ")";
    };

    var desenhar = function () {
      cvLista.innerHTML = "";
      cvMais.hidden = true;
      cvForm.querySelectorAll("[data-n-voto], [data-n-tipo]").forEach(function (b) { b.textContent = ""; });
      if (!pessoa) {
        cvCab.hidden = true;
        cvContagem.textContent = pedido.get("p") && !cvPessoa.value
          ? "Esse deputado não está entre os partidos acompanhados. Escolha outro na lista."
          : "Escolha um deputado para ver os votos.";
        return;
      }
      var fv = marcado("voto"), ft = marcado("tipo"), termo = normalizar(cvBusca.value);
      var V = indice.votacoes, P = indice.proposicoes;
      var nVoto = { todos: 0, sim: 0, nao: 0, outros: 0 }, nTipo = { todos: 0 };
      Object.keys(indice.tipos).forEach(function (k) { nTipo[k] = 0; });
      var achados = [];
      pessoa.dados.votos.forEach(function (v) {
        var vt = V[v[0]];
        if (termo) {
          if (vt._chave === undefined) {
            var prop = vt[4] != null ? P[vt[4]] : null;
            vt._chave = normalizar(vt[1] + " " + (prop ? prop[0] + " " + prop[1] : ""));
          }
          if (vt._chave.indexOf(termo) === -1) return;
        }
        var cv = classe(v[1]);
        var okVoto = fv === "todos" || cv === fv, okTipo = ft === "todos" || vt[3] === ft;
        if (okTipo) { nVoto[cv]++; nVoto.todos++; }
        if (okVoto) { nTipo[vt[3]]++; nTipo.todos++; }
        if (okVoto && okTipo) achados.push(v);
      });
      Object.keys(nVoto).forEach(function (k) {
        var b = cvForm.querySelector('[data-n-voto="' + k + '"]'); if (b) b.textContent = nVoto[k].toLocaleString("pt-BR");
      });
      Object.keys(nTipo).forEach(function (k) {
        var b = cvForm.querySelector('[data-n-tipo="' + k + '"]'); if (b) b.textContent = nTipo[k].toLocaleString("pt-BR");
      });
      // Agrupa por proposta, da votação mais recente para a mais antiga (o índice já vem nessa ordem).
      var porProposta = {}, ordem = [];
      achados.forEach(function (v) {
        var k = V[v[0]][4];
        k = k == null ? "x" : k;
        if (!porProposta[k]) { porProposta[k] = []; ordem.push(k); }
        porProposta[k].push(v);
      });
      grupos = ordem.map(function (k) { return { chave: k, votos: porProposta[k] }; });
      mostrando = 0;
      cvContagem.textContent = achados.length
        ? plural(achados.length, "voto", "votos") + NOME_FILTRO[fv] + (ft !== "todos" ? " em " + indice.tipos[ft][0].toLowerCase() : "") +
          ", sobre " + plural(grupos.length, "proposta", "propostas") + "."
        : "Nenhum voto com esses filtros.";
      mostrarMais();
    };

    var carregar = function () {
      guardarEndereco();
      var slug = cvPessoa.value;
      if (!slug) { pessoa = null; desenhar(); return; }
      cvContagem.textContent = "Carregando os votos…";
      Promise.all([indice ? indice : json("dados/votacoes.json"),
                   cache[slug] ? cache[slug] : json("dados/votos/" + slug + ".json")]).then(function (r) {
        indice = r[0]; cache[slug] = r[1];
        if (cvPessoa.value !== slug) return;
        pessoa = { slug: slug, dados: r[1] };
        desenharCabecalho();
        desenhar();
      }).catch(function () {
        cvContagem.textContent = "Não foi possível carregar os votos agora. Tente de novo em instantes.";
      });
    };

    var filtrar = function () { guardarEndereco(); if (pessoa) desenhar(); };
    cvPessoa.addEventListener("change", carregar);
    cvForm.addEventListener("change", function (e) { if (e.target.name === "voto" || e.target.name === "tipo") filtrar(); });
    cvForm.addEventListener("submit", function (e) { e.preventDefault(); filtrar(); });
    cvBusca.addEventListener("input", function () { clearTimeout(espera); espera = setTimeout(filtrar, 180); });
    cvMais.addEventListener("click", mostrarMais);
    carregar();
  }

  // ---------- Posts da semana ----------
  document.querySelectorAll("[data-copiar]").forEach(function (b) {
    var rotulo = b.textContent;
    b.addEventListener("click", function () {
      var alvo = document.getElementById(b.getAttribute("data-copiar"));
      var feito = function () { b.textContent = "Legenda copiada"; setTimeout(function () { b.textContent = rotulo; }, 2000); };
      var antigo = function () { alvo.select(); document.execCommand("copy"); feito(); };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(alvo.value).then(feito, antigo);
      else antigo();
    });
  });

  // No celular, "Compartilhar" manda todas as imagens de uma vez para o Instagram, TikTok
  // ou para a galeria. Só aparece onde o navegador sabe compartilhar arquivos.
  var compartilhaArquivos = false;
  try {
    compartilhaArquivos = !!(navigator.canShare && navigator.canShare({ files: [new File([""], "x.png", { type: "image/png" })] }));
  } catch (e) { compartilhaArquivos = false; }
  if (compartilhaArquivos) {
    document.querySelectorAll("[data-grupo]").forEach(function (grupo) {
      var b = grupo.querySelector("[data-compartilhar]");
      if (!b) return;
      var rotulo = b.textContent, arquivos = null, preparando = false;
      var compartilhar = function () {
        navigator.share({ files: arquivos }).then(function () { b.textContent = rotulo; },
          function () { b.textContent = "Tocar para compartilhar"; });
      };
      b.hidden = false;
      b.addEventListener("click", function () {
        if (arquivos) { compartilhar(); return; }
        if (preparando) return;
        preparando = true;
        b.textContent = "Preparando as imagens…";
        var links = Array.prototype.slice.call(grupo.querySelectorAll("[data-imagem]"));
        Promise.all(links.map(function (a) {
          return fetch(a.href).then(function (r) { return r.blob(); }).then(function (bl) {
            return new File([bl], a.getAttribute("download"), { type: "image/png" });
          });
        })).then(function (lista) { arquivos = lista; compartilhar(); },
          function () { b.textContent = "Não deu para preparar. Baixe uma por uma."; })
          .then(function () { preparando = false; });
      });
    });
  }
})();
