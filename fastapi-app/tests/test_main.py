import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from main import app, save_todos, load_todos, TodoItem
from datetime import date, timedelta

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    save_todos([])
    yield
    save_todos([])

# ===== 기본 CRUD 테스트 =====
def test_get_todos_empty():
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []

def test_create_todo():
    todo = {"title": "Test", "completed": False, "tags": ["home", "urgent"]}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    returned_todo = response.json()
    assert returned_todo["title"] == "Test"
    assert returned_todo["tags"] == ["home", "urgent"]
    assert "id" in returned_todo

def test_create_todo_invalid():
    todo = {"completed": False}  # title 누락
    response = client.post("/todos", json=todo)
    assert response.status_code == 422

def test_update_todo():
    todo = TodoItem(id=1, title="Test", completed=False, tags=[])
    save_todos([todo.dict()])
    updated_todo = {"title": "Updated", "completed": True, "tags": ["work"]}
    response = client.put("/todos/1", json=updated_todo)
    assert response.status_code == 200
    returned = response.json()
    assert returned["title"] == "Updated"
    assert returned["completed"] == True
    assert returned["tags"] == ["work"]

def test_update_todo_not_found():
    response = client.put("/todos/1", json={"title": "Updated", "completed": True, "tags": []})
    assert response.status_code == 404

def test_delete_todo():
    todo = TodoItem(id=1, title="Test", completed=False, tags=[])
    save_todos([todo.dict()])
    response = client.delete("/todos/1")
    assert response.status_code == 200
    assert response.json()["message"] == "To-Do item deleted"
    
def test_delete_todo_not_found():
    response = client.delete("/todos/1")
    assert response.status_code == 404

# ===== 토글 기능 테스트 =====
def test_toggle_todo():
    todo = TodoItem(id=1, title="Test", completed=False, tags=[])
    save_todos([todo.dict()])
    
    response1 = client.patch("/todos/1/toggle")
    assert response1.status_code == 200
    assert response1.json()["completed"] == True
    
    response2 = client.patch("/todos/1/toggle")
    assert response2.status_code == 200
    assert response2.json()["completed"] == False

def test_toggle_todo_not_found():
    response = client.patch("/todos/1/toggle")
    assert response.status_code == 404

def test_create_todo_with_due_date():
    todo = {"title": "Test with due date", "completed": False, "due_date": "2024-12-31", "tags": ["future"]}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    returned = response.json()
    assert returned["due_date"] == "2024-12-31"
    assert returned["tags"] == ["future"]

def test_expired_todos():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    todos_data = [
        {"id": 1, "title": "Expired", "completed": False, "due_date": yesterday, "tags": []},
        {"id": 2, "title": "Not expired", "completed": False, "due_date": tomorrow, "tags": ["pending"]},
        {"id": 3, "title": "Completed expired", "completed": True, "due_date": yesterday, "tags": ["done"]}
    ]
    save_todos(todos_data)
    
    response = client.get("/todos")
    todos = response.json()
    assert todos[0]["expired"] == True
    assert todos[1]["expired"] == False
    assert todos[2]["expired"] == True
    
    expired_response = client.get("/todos/expired")
    expired_todos = expired_response.json()
    assert len(expired_todos) == 1
    assert expired_todos[0]["title"] == "Expired"

def test_is_expired_function():
    from main import is_expired
    
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    assert is_expired(yesterday) == True
    assert is_expired(tomorrow) == False
    assert is_expired(None) == False
    assert is_expired("invalid-date") == False

# ===== tags 관련 테스트 =====
def test_create_todo_with_multiple_tags():
    todo = {"title": "Tagged Task", "completed": False, "tags": ["home", "urgent", "2025"]}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    returned = response.json()
    assert returned["tags"] == ["home", "urgent", "2025"]

def test_update_todo_tags():
    todo = TodoItem(id=1, title="Test", completed=False, tags=["initial"])
    save_todos([todo.dict()])
    updated = {"title": "Updated", "completed": False, "tags": ["work", "important"]}
    response = client.put("/todos/1", json=updated)
    assert response.status_code == 200
    returned = response.json()
    assert returned["tags"] == ["work", "important"]