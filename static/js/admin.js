/* ==========================================================================
   Verllog Logística — seleção de pedidos no painel (exportar e apagar)

   A seleção é por PEDIDO: cada linha da tabela é marcada sozinha, mesmo que
   o mesmo cliente tenha outros pedidos.

   "Exportar PDF" envia direto para /admin/exportar (formaction no botão) e
   só fica ativo com algum pedido marcado.

   O botão "Apagar" não envia nada: ele abre um aviso na própria página com os
   pedidos marcados. Só o "Confirmar exclusão" envia o formulário para
   /admin/apagar.
   ========================================================================== */

document.querySelectorAll("form[data-apagar]").forEach((form) => {
  const abrir = form.querySelector("[data-apagar-abrir]");
  const painel = form.querySelector("[data-apagar-painel]");
  const resumo = form.querySelector("[data-apagar-resumo]");
  const lista = form.querySelector("[data-apagar-lista]");
  const cancelar = form.querySelector("[data-apagar-cancelar]");
  const contagem = form.querySelector("[data-apagar-contagem]");
  const todos = form.querySelector("[data-apagar-todos]");
  const marcadores = [...form.querySelectorAll('input[type="checkbox"][name="pedidos"]')];
  const exigemSelecao = form.querySelectorAll("[data-exige-selecao]");

  // Na página do pedido ele vem num campo escondido, sempre "marcado".
  function selecionados() {
    const campos = marcadores.length
      ? marcadores.filter((campo) => campo.checked)
      : [...form.querySelectorAll('input[name="pedidos"]')];

    return campos.map((campo) => ({
      nome: campo.dataset.nome,
      codigo: campo.dataset.codigo,
    }));
  }

  function plural(numero, singular, varios) {
    return numero + " " + (numero === 1 ? singular : varios);
  }

  function fecharPainel() {
    painel.hidden = true;
  }

  function atualizar() {
    const pedidos = selecionados();
    if (marcadores.length) {
      abrir.disabled = pedidos.length === 0;
      exigemSelecao.forEach((botao) => { botao.disabled = pedidos.length === 0; });
      contagem.textContent = pedidos.length
        ? plural(pedidos.length, "pedido selecionado", "pedidos selecionados")
        : "";
      if (todos) {
        todos.checked = pedidos.length > 0 && pedidos.length === marcadores.length;
        todos.indeterminate = pedidos.length > 0 && pedidos.length < marcadores.length;
      }
    }
    // Mudou a seleção com o aviso aberto: fecha para não confirmar outra lista.
    fecharPainel();
  }

  marcadores.forEach((campo) => campo.addEventListener("change", atualizar));

  if (todos) {
    todos.addEventListener("change", () => {
      marcadores.forEach((campo) => { campo.checked = todos.checked; });
      atualizar();
    });
  }

  abrir.addEventListener("click", () => {
    const pedidos = selecionados();
    if (!pedidos.length) return;

    resumo.textContent = "Apagar " + plural(pedidos.length, "pedido", "pedidos") + "?";

    lista.replaceChildren(...pedidos.map((pedido) => {
      const item = document.createElement("li");
      item.textContent = pedido.codigo + " (" + pedido.nome + ")";
      return item;
    }));

    painel.hidden = false;
    painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  cancelar.addEventListener("click", fecharPainel);

  atualizar();
});
