// Interacciones del módulo de Compras (sin librerías externas)
(function () {
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const HIDE_KEY = "cris-shop-hide-checked";

  async function post(form, extra) {
    const body = new FormData(form);
    if (extra) Object.entries(extra).forEach(([k, v]) => body.set(k, v));
    const res = await fetch(form.action, {
      method: "POST",
      body,
      headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf },
    });
    if (!res.ok) throw new Error("No se pudo guardar");
    return res.json();
  }

  function setText(selector, value) {
    document.querySelectorAll(selector).forEach((el) => (el.textContent = value));
  }

  // Actualiza los totales de arriba con la respuesta del servidor
  function paintSummary(data) {
    setText(".js-checked", data.checked);
    setText(".js-count", data.count);
    setText(".js-estimated", data.estimated);
    setText(".js-in-cart", data.in_cart);
    document.querySelectorAll(".js-progress").forEach((el) => (el.style.width = data.progress + "%"));
    const left = document.querySelector(".js-budget-left");
    if (left && data.budget_left) {
      left.textContent = data.budget_left;
      left.classList.toggle("is-neg", data.over_budget);
      left.classList.toggle("is-pos", !data.over_budget);
      document.querySelector(".js-budget-kpi")?.classList.toggle("is-over", data.over_budget);
      setText(".js-budget-hint", data.over_budget ? "Rebasas el presupuesto" : "Disponible según el estimado");
    }
  }

  // Marcar / desmarcar artículo (al carrito)
  document.querySelectorAll(".js-item-toggle").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      const row = btn.closest(".item");
      try {
        const data = await post(btn.form);
        row.classList.toggle("is-checked", data.is_checked);
        btn.setAttribute("aria-label", data.is_checked ? "Sacar del carrito" : "Poner en el carrito");
        paintSummary(data);
      } catch {
        btn.form.submit();
      }
    });
  });

  // Precio real capturado en el pasillo: se guarda al salir del campo
  document.querySelectorAll(".js-price").forEach((input) => {
    let last = input.value;
    const save = async () => {
      if (input.value === last) return;
      const row = input.closest(".item");
      try {
        const data = await post(input.form);
        last = input.value;
        row.querySelector(".js-subtotal").textContent = data.subtotal;
        paintSummary(data);
        input.classList.add("is-saved");
        setTimeout(() => input.classList.remove("is-saved"), 900);
      } catch {
        input.classList.add("is-error");
      }
    };
    input.addEventListener("change", save);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        save();
        input.blur();
      }
    });
  });

  // Eliminar sin recargar
  document.querySelectorAll(".js-item-delete").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      const row = btn.closest(".item");
      try {
        paintSummary(await post(btn.form));
        const section = row.closest(".aisle");
        row.remove();
        if (section && !section.querySelector(".item")) section.remove();
      } catch {
        btn.form.submit();
      }
    });
  });

  // Ocultar lo que ya está en el carrito (se recuerda en este navegador)
  const hide = document.querySelector(".js-hide-checked");
  if (hide) {
    try { hide.checked = localStorage.getItem(HIDE_KEY) === "1"; } catch {}
    const apply = () => document.body.classList.toggle("hide-checked", hide.checked);
    hide.addEventListener("change", () => {
      apply();
      try { localStorage.setItem(HIDE_KEY, hide.checked ? "1" : "0"); } catch {}
    });
    apply();
  }

  // Autollenado desde tu catálogo: pasillo, unidad y último precio
  const catalogEl = document.getElementById("catalog-data");
  const nameInput = document.querySelector(".quick-add [name=name]");
  if (catalogEl && nameInput) {
    const catalog = JSON.parse(catalogEl.textContent);
    const form = nameInput.form;
    const hint = form.querySelector(".js-hint");
    nameInput.addEventListener("change", () => {
      const p = catalog[nameInput.value.trim().toLowerCase()];
      if (!p) {
        hint.hidden = true;
        return;
      }
      form.aisle.value = p.aisle;
      form.unit.value = p.unit;
      if (p.price && !form.price.value) form.price.value = p.price;
      hint.textContent = "Datos tomados de tu catálogo" + (p.price ? " · último precio $" + p.price : "");
      hint.hidden = false;
    });
  }
})();
