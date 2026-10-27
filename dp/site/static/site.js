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
})();
