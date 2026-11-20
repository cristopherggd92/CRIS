// Tema claro / oscuro de CRIS.
// El tema inicial lo pone un script corto en base.html (para evitar parpadeo);
// este archivo solo maneja el botón y guarda la preferencia.
(function () {
  const KEY = "cris-theme";
  const root = document.documentElement;

  function save(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) {
      /* navegación privada: no pasa nada, solo no se recuerda */
    }
  }

  function apply(theme) {
    root.dataset.theme = theme;
    document.querySelectorAll(".js-theme-toggle").forEach((btn) => {
      const next = theme === "dark" ? "claro" : "oscuro";
      btn.setAttribute("aria-label", "Cambiar a tema " + next);
      btn.title = "Cambiar a tema " + next;
    });
  }

  apply(root.dataset.theme || "light");

  document.querySelectorAll(".js-theme-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const theme = root.dataset.theme === "dark" ? "light" : "dark";
      apply(theme);
      save(theme);
    });
  });

  // Si nunca elegiste tema, sigue al sistema operativo cuando éste cambie
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    let saved = null;
    try {
      saved = localStorage.getItem(KEY);
    } catch (err) {}
    if (!saved) apply(e.matches ? "dark" : "light");
  });
})();
