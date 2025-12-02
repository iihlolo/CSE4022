import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from main import app, db

client = TestClient(app)


# ===== DB 초기화 =====
@pytest.fixture(autouse=True)
def clear_db():
    import asyncio
    asyncio.run(db.todos.delete_many({}))
    yield
    asyncio.run(db.todos.delete_many({}))


# ===== 기본 CRUD 테스트 =====
def test_get_todos_empty():
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []


def test_create_todo():
    todo = {"title": "Test", "completed": False, "tags": ["home", "urgent"]}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    data = response.json()

    assert data["title"] == "Test"
    assert data["tags"] == ["home", "urgent"]
    assert isinstance(data["id"], str)  # MongoDB ObjectId 문자열


def test_create_todo_invalid():
    todo = {"completed": False}  # title 누락
    response = client.post("/todos", json=todo)
    assert response.status_code == 422


def test_update_todo():
    created = client.post("/todos", json={"title": "Test", "completed": False, "tags": []}).json()
    tid = created["id"]

    updated = {"title": "Updated", "completed": True, "tags": ["work"]}
    response = client.put(f"/todos/{tid}", json=updated)
    assert response.status_code == 200
    data = response.json()

    assert data["title"] == "Updated"
    assert data["completed"] is True
    assert data["tags"] == ["work"]


def test_update_todo_not_found():
    response = client.put("/todos/ffffffffffffffffffffffff", json={"title": "X", "completed": False, "tags": []})
    assert response.status_code == 404


def test_delete_todo():
    created = client.post("/todos", json={"title": "Test", "completed": False, "tags": []}).json()
    tid = created["id"]

    response = client.delete(f"/todos/{tid}")
    assert response.status_code == 200
    assert response.json()["message"] == "To-Do item deleted"


def test_delete_todo_not_found():
    response = client.delete("/todos/ffffffffffffffffffffffff")
    assert response.status_code == 404


# ===== 토글 기능 테스트 =====
def test_toggle_todo():
    created = client.post("/todos", json={"title": "Toggle", "completed": False, "tags": []}).json()
    tid = created["id"]

    response1 = client.patch(f"/todos/{tid}/toggle")
    assert response1.status_code == 200
    assert response1.json()["completed"] is True

    response2 = client.patch(f"/todos/{tid}/toggle")
    assert response2.status_code == 200
    assert response2.json()["completed"] is False


def test_toggle_todo_not_found():
    response = client.patch("/todos/ffffffffffffffffffffffff/toggle")
    assert response.status_code == 404


# ===== due_date 생성 테스트 =====
def test_create_todo_with_due_date():
    todo = {"title": "Test with due date", "completed": False, "due_date": "2024-12-31", "tags": ["future"]}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    returned = response.json()

    assert returned["due_date"] == "2024-12-31"
    assert returned["tags"] == ["future"]


# ===== expired 관련 =====
def test_expired_flag_and_filter():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    client.post("/todos", json={"title": "Expired", "completed": False, "due_date": yesterday})
    client.post("/todos", json={"title": "Not expired", "completed": False, "due_date": tomorrow})
    client.post("/todos", json={"title": "Completed expired", "completed": True, "due_date": yesterday})

    todos = client.get("/todos").json()
    names = {t["title"]: t["expired"] for t in todos}
    assert names["Expired"] is True
    assert names["Not expired"] is False
    assert names["Completed expired"] is True

    expired_only = client.get("/todos/expired").json()
    assert len(expired_only) == 1
    assert expired_only[0]["title"] == "Expired"


# ===== 정렬 로직 테스트 =====
def test_sorted_order():
    # 1: 기한 없는 TODO
    client.post("/todos", json={"title": "A", "completed": False})

    # 2: 미래 due_date
    client.post("/todos", json={
        "title": "B",
        "completed": False,
        "due_date": (date.today() + timedelta(days=1)).isoformat()
    })

    # 3: 과거 due_date (만료)
    client.post("/todos", json={
        "title": "C",
        "completed": False,
        "due_date": (date.today() - timedelta(days=1)).isoformat()
    })

    # 4: 완료된 TODO
    d = client.post("/todos", json={"title": "D", "completed": False}).json()
    client.patch(f"/todos/{d['id']}/toggle")

    todos = client.get("/todos").json()
    titles = [t["title"] for t in todos]

    # 정렬 결과 검증
    assert titles == ["A", "B", "C", "D"]


# ===== tags 관련 테스트 =====
def test_create_todo_multiple_tags():
    todo = {"title": "Tagged Task", "completed": False, "tags": ["home", "urgent", "2025"]}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    assert response.json()["tags"] == ["home", "urgent", "2025"]


def test_update_todo_tags():
    created = client.post("/todos", json={"title": "Test", "completed": False, "tags": ["initial"]}).json()
    tid = created["id"]

    updated = {"title": "Updated", "completed": False, "tags": ["work", "important"]}
    response = client.put(f"/todos/{tid}", json=updated)
    assert response.status_code == 200
    assert response.json()["tags"] == ["work", "important"]