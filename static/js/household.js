// Módulo Hogar: panel lateral con formularios dinámicos, acciones rápidas y filtros.
// Sin librerías externas.
(function () {
  const drawer = document.getElementById("drawer");
  const content = document.getElementById("drawer-content");
  const toastEl = document.getElementById("hh-toast");
  const TOAST_KEY = "cris-hh-toast";
  const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  let lastFocus = null;

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const csrf = () => $("[name=csrfmiddlewaretoken]")?.value;

  // ---------- Fechas ----------
  function parseDate(value) {
    if (!value) return null;
    const [y, m, d] = value.split("-").map(Number);
    return y ? new Date(y, m - 1, d) : null;
  }
  function addMonths(date, months) {
    const d = new Date(date.getFullYear(), date.getMonth() + months, 1);
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    d.setDate(Math.min(date.getDate(), last));
    return d;
  }
  const iso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const nice = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  function relative(d) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.round((d - today) / 86400000);
    if (days === 0) return "es hoy";
    if (days === 1) return "es mañana";
    if (days < 0) return `venció hace ${-days} día${days === -1 ? "" : "s"}`;
    if (days < 60) return `faltan ${days} días`;
    return `faltan ${Math.round(days / 30)} meses`;
  }

  // ---------- Avisos ----------
  function toast(message, link) {
    if (!toastEl || !message) return;
    toastEl.innerHTML = "";
    toastEl.append(document.createTextNode(message));
    if (link) {
      const a = document.createElement("a");
      a.href = link;
      a.textContent = "Registrar en Finanzas →";
      toastEl.append(a);
    }
    toastEl.hidden = false;
    toastEl.classList.add("is-in");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => {
      toastEl.classList.remove("is-in");
      toastEl.hidden = true;
    }, link ? 7000 : 3500);
  }
  // Un aviso guardado sobrevive a la recarga de la página
  function reloadWithToast(message, link, url) {
    try {
      sessionStorage.setItem(TOAST_KEY, JSON.stringify({ message, link }));
    } catch {}
    if (url && url !== location.pathname + location.search) location.href = url;
    else location.reload();
  }
  try {
    const saved = JSON.parse(sessionStorage.getItem(TOAST_KEY) || "null");
    sessionStorage.removeItem(TOAST_KEY);
    if (saved) toast(saved.message, saved.link);
  } catch {}

  // ---------- Panel lateral ----------
  async function openDrawer(url) {
    if (!drawer) {
      location.href = url;
      return;
    }
    lastFocus = document.activeElement;
    content.innerHTML = '<div class="drawer__loading">Cargando…</div>';
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("no-scroll");
    try {
      const res = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
      if (!res.ok) throw new Error();
      mount(await res.text());
    } catch {
      location.href = url; // sin JavaScript también funciona como página normal
    }
  }
  function closeDrawer() {
    if (!drawer?.classList.contains("is-open")) return;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("no-scroll");
    lastFocus?.focus?.();
  }
  function mount(html) {
    content.innerHTML = html;
    const form = $(".js-hform", content);
    if (form) {
      enhance(form);
      const first = $(".hf-error", form)?.closest(".hf-field")?.querySelector("input,select,textarea") ||
        $("input:not([type=hidden]):not([type=radio]):not([type=checkbox]), select", $(".hf__body", form));
      setTimeout(() => first?.focus(), 60);
    }
  }

  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-drawer]");
    if (opener && opener.href) {
      e.preventDefault();
      $$(".js-qa").forEach((d) => (d.open = false));
      openDrawer(opener.href);
      return;
    }
    if (e.target.closest(".js-drawer-close")) {
      e.preventDefault();
      closeDrawer();
    }
    // Cierra los menús desplegables al hacer clic fuera
    $$(".js-qa[open], .pay-pop[open]").forEach((d) => {
      if (!d.contains(e.target)) d.open = false;
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDrawer();
  });

  // Envío del formulario del panel sin recargar
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest(".js-hform");
    if (!form || !content.contains(form)) return;
    e.preventDefault();
    const submitter = e.submitter;
    if (submitter?.classList.contains("js-confirm") && !submitter.classList.contains("is-armed")) {
      submitter.classList.add("is-armed");
      submitter.querySelector("span").textContent = "¿Seguro? Toca otra vez";
      setTimeout(() => {
        submitter.classList.remove("is-armed");
        submitter.querySelector("span").textContent = "Eliminar";
      }, 3000);
      return;
    }
    const action = submitter?.getAttribute("formaction") || form.action;
    const save = $(".js-save", form);
    save?.classList.add("is-loading");
    try {
      const res = await fetch(action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf() },
      });
      const type = res.headers.get("content-type") || "";
      if (type.includes("application/json")) {
        const data = await res.json();
        closeDrawer();
        reloadWithToast(data.message, data.finance_url);
      } else {
        mount(await res.text()); // errores de validación: se muestran en el panel
        $(".hf", content)?.classList.add("shake");
      }
    } catch {
      form.submit();
    }
  });

  // ---------- Comportamientos de los formularios ----------
  function enhance(form) {
    // Tiles que autollenan el nombre (si el usuario no lo ha escrito)
    $$("[data-autofill]", form).forEach((group) => {
      const target = $(group.dataset.autofill, form);
      if (!target) return;
      let auto = null;
      const fill = (tile) => {
        const label = tile?.querySelector(".hf-tile__label")?.textContent.trim();
        if (label && (target.value === "" || target.value === auto)) {
          target.value = auto = label;
          target.dispatchEvent(new Event("input", { bubbles: true }));
        }
      };
      group.addEventListener("change", (e) => fill(e.target.closest(".hf-tile")));
      fill($("input:checked", group)?.closest(".hf-tile")); // el tipo que ya viene marcado
    });

    // Chips que ponen un valor en un campo
    $$("[data-set]", form).forEach((chip) =>
      chip.addEventListener("click", () => {
        const input = $(chip.dataset.set, form);
        input.value = chip.dataset.value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        mark(chip);
      })
    );
    // Chips de fecha relativa a hoy
    $$("[data-from-today]", form).forEach((chip) =>
      chip.addEventListener("click", () => {
        const input = $(chip.dataset.target, form);
        input.value = iso(addMonths(new Date(), Number(chip.dataset.fromToday)));
        input.dispatchEvent(new Event("input", { bubbles: true }));
        mark(chip);
      })
    );
    function mark(chip) {
      chip.parentElement.querySelectorAll(".hf-chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    }

    // Vista previa "vence ..." para cualquier campo de fecha marcado
    const dueInput = $("#id_due_date", form);
    const duePreview = $(".js-due-preview", form);
    if (dueInput && duePreview) {
      const paint = () => {
        const d = parseDate(dueInput.value);
        duePreview.hidden = !d;
        if (d) $(".js-due-text", duePreview).textContent = `${nice(d)} · ${relative(d)}`;
      };
      dueInput.addEventListener("input", paint);
      paint();
    }

    const kind = form.dataset.kind;
    if (kind === "servicio") serviceForm(form);
    if (kind === "recibo") billForm(form);
    if (kind === "vehiculo") vehicleForm(form);
    if (kind === "mantenimiento") maintenanceForm(form);
    if (kind === "articulo") assetForm(form);
  }

  function serviceForm(form) {
    const providers = JSON.parse(form.dataset.providers || "{}");
    const list = $("#providers", form);
    const fillProviders = () => {
      const kind = $("[name=kind]:checked", form)?.value;
      list.innerHTML = (providers[kind] || []).map((p) => `<option value="${p}">`).join("");
    };
    form.addEventListener("change", (e) => e.target.name === "kind" && fillProviders());
    fillProviders();

    const MONTHS_BY = { mensual: 1, bimestral: 2, trimestral: 3, semestral: 6, anual: 12 };
    const box = $(".js-preview-service", form);
    const paint = () => {
      const start = parseDate($("#id_next_due", form).value);
      const freq = $("[name=frequency]:checked", form)?.value || "mensual";
      box.hidden = !start;
      if (!start) return;
      const dates = [0, 1, 2].map((i) => addMonths(start, MONTHS_BY[freq] * i));
      $(".js-preview-text", box).textContent = dates.map(nice).join(" · ");
    };
    form.addEventListener("input", paint);
    form.addEventListener("change", paint);
    paint();
  }

  function billForm(form) {
    const data = JSON.parse($("#hf-services", form)?.textContent || "{}");
    const select = $("#id_service", form);
    const amount = $("#id_amount", form);
    const due = $("#id_due_date", form);
    let autoAmount = null;
    let autoDue = null;
    select.addEventListener("change", () => {
      const s = data[select.value];
      if (!s) return;
      if (!amount.value || amount.value === autoAmount) amount.value = autoAmount = s.amount;
      if (!due.value || due.value === autoDue) due.value = autoDue = s.due;
      due.dispatchEvent(new Event("input", { bubbles: true }));
      amount.classList.add("flash");
      setTimeout(() => amount.classList.remove("flash"), 600);
    });
  }

  function vehicleForm(form) {
    const name = $("#id_name", form);
    const plate = $("#id_plate", form);
    const desc = () =>
      ["#id_brand", "#id_model", "#id_year"].map((s) => $(s, form).value.trim()).filter(Boolean).join(" ") ||
      "Marca · modelo · año";
    const preview = $(".js-car-preview", form);
    const paint = () => {
      $(".js-car-name", form).textContent = name.value || "Mi vehículo";
      $(".js-car-desc", form).textContent = desc();
      $(".js-car-plate", form).textContent = (plate.value || "PLACAS").toUpperCase();
      const color = $("[name=color]:checked", form)?.value || "indigo";
      preview.className = `hf-car-preview js-car-preview hf-car-preview--${color}`;
    };
    form.addEventListener("input", paint);
    form.addEventListener("change", paint);
    paint();
  }

  function maintenanceForm(form) {
    const chips = JSON.parse(form.dataset.chips || "{}");
    const vehicles = JSON.parse($("#hf-vehicles", form)?.textContent || "{}");
    const box = $(".js-title-chips", form);
    const title = $("#id_title", form);
    const km = $("#id_km", form);
    const vehicle = $("#id_vehicle", form);
    const area = () => $("[name=area]:checked", form)?.value || "auto";

    const paint = () => {
      const isCar = area() === "auto";
      $$(".js-car-only", form).forEach((el) => (el.hidden = !isCar));
      box.innerHTML = "";
      (chips[area()] || []).forEach((label) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "hf-chip" + (title.value === label ? " is-on" : "");
        b.textContent = label;
        b.addEventListener("click", () => {
          title.value = label;
          $$(".hf-chip", box).forEach((c) => c.classList.toggle("is-on", c === b));
        });
        box.append(b);
      });
    };
    form.addEventListener("change", (e) => e.target.name === "area" && paint());
    vehicle?.addEventListener("change", () => {
      if (!km.value && vehicles[vehicle.value]) km.value = vehicles[vehicle.value];
    });
    // "+5,000 km" y "6 meses" calculan el siguiente servicio
    $$("[data-add-km]", form).forEach((chip) =>
      chip.addEventListener("click", () => {
        const base = Number(km.value || vehicles[vehicle?.value] || 0);
        $("#id_next_km", form).value = base + Number(chip.dataset.addKm);
      })
    );
    $$("[data-add-months]", form).forEach((chip) =>
      chip.addEventListener("click", () => {
        const base = parseDate($("#id_date", form).value) || new Date();
        $("#id_next_date", form).value = iso(addMonths(base, Number(chip.dataset.addMonths)));
      })
    );
    paint();
  }

  function assetForm(form) {
    const months = $("#id_warranty_months", form);
    const bought = $("#id_purchase_date", form);
    const box = $(".js-warranty", form);
    const paint = () => {
      const start = parseDate(bought.value);
      const m = Number(months.value || 0);
      $$("[data-set]", form).forEach((c) => c.classList.toggle("is-on", Number(c.dataset.value) === m));
      box.hidden = !(start && m);
      if (box.hidden) return;
      const end = addMonths(start, m);
      const total = end - start;
      const left = end - new Date();
      const pct = Math.max(0, Math.min(100, (left / total) * 100));
      box.classList.toggle("is-expired", left < 0);
      $(".js-warranty-text", box).textContent =
        left < 0 ? `La garantía venció el ${nice(end)}` : `Garantía hasta el ${nice(end)} · ${relative(end)}`;
      $(".js-warranty-bar", box).style.width = pct + "%";
    };
    form.addEventListener("input", paint);
    paint();
  }

  // Página sin JavaScript (form_page.html): aplica los mismos comportamientos
  $$(".hf-page .js-hform").forEach(enhance);

  // ---------- Acciones rápidas (pagar, hecho) ----------
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest(".js-quick");
    if (!form) return;
    e.preventDefault();
    const row = form.closest(".ag, .svc");
    row?.classList.add("is-working");
    try {
      const res = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf() },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.message);
      row?.classList.add("is-gone");
      setTimeout(() => reloadWithToast(data.message, data.finance_url), 350);
    } catch (err) {
      row?.classList.remove("is-working");
      toast(err.message || "No se pudo completar la acción.");
    }
  });

  // Kilometraje en línea: se guarda al salir del campo
  $$(".js-km").forEach((form) => {
    const input = $("input[name=km]", form);
    let last = input.value;
    const save = async () => {
      if (input.value === last) return;
      try {
        const res = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf() },
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message);
        last = input.value;
        toast(data.message);
        input.classList.add("is-saved");
        setTimeout(() => input.classList.remove("is-saved"), 900);
      } catch (err) {
        toast(err.message || "No se pudo guardar.");
      }
    };
    input.addEventListener("change", save);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      save();
    });
  });

  // ---------- Filtros y búsqueda en la lista ----------
  const money = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });
  function applyFilters(target) {
    const list = $(target);
    if (!list) return;
    const chip = $(`.js-filter[data-target="${target}"] .hf-chip.is-on`);
    const tag = chip?.dataset.filter || "";
    const q = ($(`.js-search[data-target="${target}"]`)?.value || "").trim().toLowerCase();
    let total = 0;
    let visible = 0;
    Array.from(list.children).forEach((row) => {
      const tags = (row.dataset.tags || "").split(" ");
      const show = (!tag || tags.includes(tag)) && (!q || row.textContent.toLowerCase().includes(q));
      row.hidden = !show;
      if (show) {
        visible += 1;
        total += Number(row.dataset.amount || 0);
      }
    });
    const totalEl = $(".js-filter-total");
    if (totalEl && list.querySelector("[data-amount]")) totalEl.textContent = money.format(total);
    const empty = $(".js-no-results");
    if (empty) empty.hidden = visible > 0;
  }
  $$(".js-filter").forEach((group) =>
    group.addEventListener("click", (e) => {
      const chip = e.target.closest(".hf-chip");
      if (!chip) return;
      $$(".hf-chip", group).forEach((c) => c.classList.toggle("is-on", c === chip));
      applyFilters(group.dataset.target);
    })
  );
  $$(".js-search").forEach((input) => input.addEventListener("input", () => applyFilters(input.dataset.target)));
})();
