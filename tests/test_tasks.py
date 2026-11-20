from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.tasks.models import Tag, Task

PASSWORD = "clave-segura-123"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="cris", password=PASSWORD)


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(username="otro", password=PASSWORD)


@pytest.fixture
def logged(client, user):
    client.force_login(user)
    return client


def make_task(owner, **kwargs):
    data = {"title": "Tarea", "owner": owner}
    data.update(kwargs)
    return Task.objects.create(**data)


# ---------- Modelo ----------


def test_completar_registra_fecha_y_reabrir_la_limpia(user):
    task = make_task(user)
    task.status = Task.Status.DONE
    task.save()
    assert task.completed_at is not None
    task.status = Task.Status.PENDING
    task.save()
    assert task.completed_at is None


@pytest.mark.parametrize(
    ("days", "expected"),
    [(-1, "overdue"), (0, "today"), (2, "soon"), (10, None)],
)
def test_estado_de_vencimiento(user, days, expected):
    task = make_task(user, due_date=timezone.localdate() + timedelta(days=days))
    assert task.due_state == expected


def test_tarea_completada_nunca_esta_vencida(user):
    task = make_task(
        user, due_date=timezone.localdate() - timedelta(days=5), status=Task.Status.DONE
    )
    assert task.due_state is None


# ---------- Acceso ----------


@pytest.mark.django_db
def test_anonimo_no_ve_tareas(client):
    response = client.get(reverse("tasks:list"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_no_puedo_ver_ni_editar_tareas_de_otro(logged, other_user):
    ajena = make_task(other_user, title="Secreta")
    assert "Secreta" not in logged.get(reverse("tasks:list")).content.decode()
    assert logged.get(reverse("tasks:update", args=[ajena.pk])).status_code == 404
    assert logged.post(reverse("tasks:delete", args=[ajena.pk])).status_code == 404
    response = logged.post(reverse("tasks:set_status", args=[ajena.pk]), {"status": "completada"})
    assert response.status_code == 404


# ---------- CRUD ----------


def test_crear_tarea_con_etiquetas(logged, user):
    response = logged.post(
        reverse("tasks:create"),
        {
            "title": "Pagar luz",
            "description": "",
            "status": "pendiente",
            "priority": 3,
            "due_date": "2030-01-15",
            "tags_text": "Casa, pagos, casa ,",
        },
    )
    assert response.status_code == 302
    task = Task.objects.get(title="Pagar luz")
    assert task.owner == user
    assert task.priority == Task.Priority.HIGH
    assert sorted(t.name for t in task.tags.all()) == ["casa", "pagos"]


def test_titulo_es_obligatorio(logged):
    response = logged.post(
        reverse("tasks:create"), {"title": "", "status": "pendiente", "priority": 2}
    )
    assert response.status_code == 200
    assert Task.objects.count() == 0


def test_editar_tarea_reemplaza_etiquetas(logged, user):
    task = make_task(user, title="Vieja")
    task.tags.add(Tag.objects.create(owner=user, name="viejo"))
    logged.post(
        reverse("tasks:update", args=[task.pk]),
        {"title": "Nueva", "status": "en_progreso", "priority": 4, "tags_text": "nuevo"},
    )
    task.refresh_from_db()
    assert task.title == "Nueva"
    assert task.status == Task.Status.IN_PROGRESS
    assert [t.name for t in task.tags.all()] == ["nuevo"]


def test_eliminar_tarea(logged, user):
    task = make_task(user)
    response = logged.post(reverse("tasks:delete", args=[task.pk]))
    assert response.status_code == 302
    assert not Task.objects.filter(pk=task.pk).exists()


def test_cambiar_estatus_por_fetch_responde_json(logged, user):
    task = make_task(user)
    response = logged.post(
        reverse("tasks:set_status", args=[task.pk]),
        {"status": "completada"},
        headers={"x-requested-with": "fetch"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completada"
    task.refresh_from_db()
    assert task.status == Task.Status.DONE


def test_estatus_invalido(logged, user):
    task = make_task(user)
    response = logged.post(reverse("tasks:set_status", args=[task.pk]), {"status": "x"})
    assert response.status_code == 400


# ---------- Lista y filtros ----------


def titles(response):
    return [t.title for t in response.context["tasks"]]


def test_filtros(logged, user):
    casa = Tag.objects.create(owner=user, name="casa")
    a = make_task(user, title="Comprar pan", priority=1)
    a.tags.add(casa)
    make_task(user, title="Reporte", priority=4, status=Task.Status.IN_PROGRESS)
    make_task(user, title="Viejo", due_date=timezone.localdate() - timedelta(days=1))
    url = reverse("tasks:list")

    assert titles(logged.get(url, {"q": "pan"})) == ["Comprar pan"]
    assert titles(logged.get(url, {"status": "en_progreso"})) == ["Reporte"]
    assert titles(logged.get(url, {"priority": "4"})) == ["Reporte"]
    assert titles(logged.get(url, {"tag": "casa"})) == ["Comprar pan"]
    assert titles(logged.get(url, {"status": "vencidas"})) == ["Viejo"]


def test_orden_por_defecto_deja_completadas_al_final(logged, user):
    make_task(user, title="Hecha", status=Task.Status.DONE, priority=4)
    make_task(user, title="Pendiente", priority=1)
    make_task(user, title="En curso", status=Task.Status.IN_PROGRESS)
    assert titles(logged.get(reverse("tasks:list"))) == ["En curso", "Pendiente", "Hecha"]


def test_contadores(logged, user):
    make_task(user)
    make_task(user, status=Task.Status.DONE)
    counts = logged.get(reverse("tasks:list")).context["counts"]
    assert counts["total"] == 2
    assert counts["pendiente"] == 1
    assert counts["completada"] == 1


def test_tarjeta_de_tareas_en_el_menu_ya_navega(logged):
    html = logged.get(reverse("core:dashboard")).content.decode()
    assert f'href="{reverse("tasks:list")}"' in html
