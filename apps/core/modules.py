"""Registro de módulos de CRIS.

Para agregar un módulo nuevo basta con añadir un elemento a MODULES.
Cuando el módulo exista, llena "url_name" y el botón empezará a navegar.
"""

MODULES = [
    {
        "key": "tasks",
        "name": "Tareas",
        "description": "Organiza pendientes, prioridades y fechas límite.",
        "icon": "check",
        "color": "indigo",
        "url_name": "tasks:list",
    },
    {
        "key": "finance",
        "name": "Finanzas",
        "description": "Controla ingresos, gastos y presupuestos.",
        "icon": "wallet",
        "color": "emerald",
        "url_name": None,
    },
    {
        "key": "notes",
        "name": "Notas",
        "description": "Guarda ideas y apuntes rápidos.",
        "icon": "note",
        "color": "amber",
        "url_name": None,
    },
    {
        "key": "habits",
        "name": "Hábitos",
        "description": "Da seguimiento a tus rutinas diarias.",
        "icon": "calendar",
        "color": "rose",
        "url_name": None,
    },
]
