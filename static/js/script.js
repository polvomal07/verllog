/* ==========================================================================
   Verllog Logística — script do site público

   Valida o formato do código antes de enviar, para o usuário receber o aviso
   na hora em vez de carregar uma página de "não encontrado".

   O formulário funciona sem JavaScript: o envio nativo (GET para
   /rastreamento) leva ao mesmo lugar, e a validação do servidor cobre o resto.
   ========================================================================== */

// Mesmo padrão definido em config.py (CODIGO_REGEX): 2 letras + 12 dígitos + 1 letra.
const PADRAO_CODIGO = /^[A-Z]{2}\d{12}[A-Z]$/;

// Códigos antigos, aceitos enquanto ACEITAR_CODIGOS_LEGADOS estiver ligado.
const PADRAO_LEGADO = /^[A-Z]{2}\d{8,20}[A-Z]?$/;

/* ------------------------------------------------------------------ Menu
   No celular o menu fica recolhido atrás do botão de três riscos. No
   desktop ele está sempre visível e este código não faz diferença.
   -------------------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
  const botao = document.getElementById("menu-botao");
  const navegacao = document.getElementById("navegacao");
  if (!botao || !navegacao) return;

  function fechar() {
    navegacao.classList.remove("aberto");
    botao.setAttribute("aria-expanded", "false");
    botao.setAttribute("aria-label", "Abrir menu");
  }

  botao.addEventListener("click", () => {
    const aberto = navegacao.classList.toggle("aberto");
    botao.setAttribute("aria-expanded", aberto ? "true" : "false");
    botao.setAttribute("aria-label", aberto ? "Fechar menu" : "Abrir menu");
  });

  // Fecha ao escolher um destino, ao apertar Esc e ao girar o aparelho.
  navegacao.querySelectorAll("a").forEach((link) =>
    link.addEventListener("click", fechar)
  );

  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") fechar();
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 720) fechar();
  });
});


/* ---------------------------------------------------- Busca de rastreio */
document.addEventListener("DOMContentLoaded", () => {
  const formulario = document.getElementById("form-rastreio");
  if (!formulario) return;

  const campo = document.getElementById("codigo");
  const aviso = document.getElementById("busca-aviso");

  // Deixa o código sempre em maiúsculas e sem separadores enquanto digita.
  campo.addEventListener("input", () => {
    campo.value = campo.value.toUpperCase().replace(/[\s\-\.]/g, "");
    if (aviso) aviso.textContent = "";
  });

  formulario.addEventListener("submit", (evento) => {
    const codigo = campo.value.trim();

    if (!codigo) {
      evento.preventDefault();
      if (aviso) aviso.textContent = "Digite um código de rastreamento para continuar.";
      campo.focus();
      return;
    }

    if (!PADRAO_CODIGO.test(codigo) && !PADRAO_LEGADO.test(codigo)) {
      evento.preventDefault();
      if (aviso) {
        aviso.textContent =
          "Código fora do padrão. Use 2 letras + 12 números + 1 letra. Exemplo: VL263198595496D";
      }
      campo.focus();
      return;
    }

    // Código válido: deixa o formulário seguir para /rastreamento?codigo=...
  });
});
