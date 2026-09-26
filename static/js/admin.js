/* ==========================================================================
   Verllog Logística — exclusão de clientes no painel

   O botão "Apagar" não envia nada: ele abre um aviso na própria página com os
   nomes e a quantidade de pedidos. Só o "Confirmar exclusão" envia o
   formulário para /admin/apagar.

   Um cliente pode ter mais de um pedido, então aparece em mais de uma linha.
   Marcar uma linha marca todas as do mesmo cliente, para ficar claro que
   tudo dele vai junto.
   ========================================================================== */

document.querySelectorAll("form[data-apagar]").forEach((form) => {
  const abrir = form.querySelector("[data-apagar-abrir]");
  const painel = form.querySelector("[data-apagar-painel]");
  const resumo = form.querySelector("[data-apagar-resumo]");
  const lista = form.querySelector("[data-apagar-lista]");
  const cancelar = form.querySelector("[data-apagar-cancelar]");
  const contagem = form.querySelector("[data-apagar-contagem]");
  const todos = form.querySelector("[data-apagar-todos]");
  const marcadores = [...form.querySelectorAll('input[type="checkbox"][name="clientes"]')];

  // Na página do pedido o cliente vem num campo escondido, sempre "marcado".
  function selecionados() {
    const campos = marcadores.length
      ? marcadores.filter((campo) => campo.checked)
      : [...form.querySelectorAll('input[name="clientes"]')];

    const porId = new Map();
    campos.forEach((campo) => {
      porId.set(campo.value, {
        nome: campo.dataset.nome,
        pedidos: Number(campo.dataset.pedidos) || 0,
      });
    });
    return [...porId.values()];
  }

  function plural(numero, singular, varios) {
    return numero + " " + (numero === 1 ? singular : varios);
  }

  function fecharPainel() {
    painel.hidden = true;
  }

  function atualizar() {
    const clientes = selecionados();
    if (marcadores.length) {
      abrir.disabled = clientes.length === 0;
      contagem.textContent = clientes.length
        ? plural(clientes.length, "cliente selecionado", "clientes selecionados")
        : "";
      if (todos) {
        const marcados = marcadores.filter((campo) => campo.checked).length;
        todos.checked = marcados > 0 && marcados === marcadores.length;
        todos.indeterminate = marcados > 0 && marcados < marcadores.length;
      }
    }
    // Mudou a seleção com o aviso aberto: fecha para não confirmar outra lista.
    fecharPainel();
  }

  marcadores.forEach((campo) => {
    campo.addEventListener("change", () => {
      marcadores
        .filter((outro) => outro.value === campo.value)
        .forEach((outro) => { outro.checked = campo.checked; });
      atualizar();
    });
  });

  if (todos) {
    todos.addEventListener("change", () => {
      marcadores.forEach((campo) => { campo.checked = todos.checked; });
      atualizar();
    });
  }

  abrir.addEventListener("click", () => {
    const clientes = selecionados();
    if (!clientes.length) return;

    const pedidos = clientes.reduce((soma, cliente) => soma + cliente.pedidos, 0);
    resumo.textContent =
      "Apagar " + plural(clientes.length, "cliente", "clientes") +
      " e " + plural(pedidos, "pedido", "pedidos") + "?";

    lista.replaceChildren(...clientes.map((cliente) => {
      const item = document.createElement("li");
      item.textContent = cliente.nome + " (" + plural(cliente.pedidos, "pedido", "pedidos") + ")";
      return item;
    }));

    painel.hidden = false;
    painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  cancelar.addEventListener("click", fecharPainel);

  atualizar();
});
