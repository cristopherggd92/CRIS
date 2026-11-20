// Interacciones del módulo de Tareas (sin librerías externas)
(function () {
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;

  // Los filtros se aplican solos al cambiar un select
  const filters = document.getElementById("filters");
  filters?.querySelectorAll("select").forEach((el) =>
    el.addEventListener("change", () => filters.submit())
  );

  async function setStatus(form, status) {
    const body = new FormData(form);
    body.set("status", status);
    const res = await fetch(form.action, {
      method: "POST",
      body,
      headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf },
    });
    if (!res.ok) throw new Error("No se pudo actualizar");
    return res.json();
  }

  function paint(row, data) {
    row.className = row.className.replace(/task--(pendiente|en_progreso|completada)/, "task--" + data.status);
    const select = row.querySelector(".js-status");
    select.value = data.status;
    select.className = select.className.replace(/status-select--\w+/, "status-select--" + data.status);
    const toggle = row.querySelector(".task__check-form [name=status]");
    toggle.value = data.status === "completada" ? "pendiente" : "completada";
    const due = row.querySelector(".js-due");
    if (due) {
      due.classList.remove("due--overdue", "due--today", "due--soon");
      if (data.due_state) due.classList.add("due--" + data.due_state);
    }
  }

  // Cambio de estatus desde el select, sin recargar la página
  document.querySelectorAll(".js-status").forEach((select) => {
    select.addEventListener("change", async () => {
      const row = select.closest(".task");
      try {
        paint(row, await setStatus(select.form, select.value));
      } catch {
        select.form.submit();
      }
    });
  });

  // Botón circular: completar / reabrir
  document.querySelectorAll(".js-toggle").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      const form = btn.form;
      const row = btn.closest(".task");
      try {
        paint(row, await setStatus(form, form.status.value));
      } catch {
        form.submit();
      }
    });
  });
})();
