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
        "url_name": "finance:home",
    },
    {
        "key": "shopping",
        "name": "Compras",
        "description": "Listas del súper por pasillo, precios y presupuesto.",
        "icon": "cart",
        "color": "amber",
        "url_name": "shopping:home",
    },
    {
        "key": "household",
        "name": "Hogar",
        "description": "Servicios, recibos, auto, garantías e inventario.",
        "icon": "house",
        "color": "rose",
        "url_name": "household:home",
    },
]
