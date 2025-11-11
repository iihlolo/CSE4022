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
    # 테스트 전 초기화
    save_todos([])
    yield
    # 테스트 후 정리
    save_todos([])

# ===== 기본 CRUD 테스트 =====
def test_get_todos_empty():
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []

def test_create_todo():
    todo = {"title": "Test", "description": "Test description", "completed": False}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    returned_todo = response.json()
    assert returned_todo["title"] == "Test"
    assert "id" in returned_todo

def test_create_todo_invalid():
    todo = {"title": "Test"}  # description 누락
    response = client.post("/todos", json=todo)
    assert response.status_code == 422

def test_update_todo():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    updated_todo = {"title": "Updated", "description": "Updated description", "completed": True}
    response = client.put("/todos/1", json=updated_todo)
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"

def test_update_todo_not_found():
    response = client.put("/todos/1", json={"title": "Updated", "description": "Updated", "completed": True})
    assert response.status_code == 404

def test_delete_todo():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    response = client.delete("/todos/1")
    assert response.status_code == 200
    assert response.json()["message"] == "To-Do item deleted"
    
def test_delete_todo_not_found():
    response = client.delete("/todos/1")
    assert response.status_code == 404

# ===== 토글 기능 테스트 =====
def test_toggle_todo():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    
    # False -> True
    response1 = client.patch("/todos/1/toggle")
    assert response1.status_code == 200
    assert response1.json()["completed"] == True
    
    # True -> False
    response2 = client.patch("/todos/1/toggle")
    assert response2.status_code == 200
    assert response2.json()["completed"] == False

def test_toggle_todo_not_found():
    response = client.patch("/todos/1/toggle")
    assert response.status_code == 404

def test_create_todo_with_due_date():
    todo = {"title": "Test with due date", "description": "Test description", "completed": False, "due_date": "2024-12-31"}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    assert response.json()["due_date"] == "2024-12-31"

def test_expired_todos():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    todos_data = [
        {"id": 1, "title": "Expired", "description": "Expired todo", "completed": False, "due_date": yesterday},
        {"id": 2, "title": "Not expired", "description": "Future todo", "completed": False, "due_date": tomorrow},
        {"id": 3, "title": "Completed expired", "description": "Completed", "completed": True, "due_date": yesterday}
    ]
    save_todos(todos_data)
    
    # 전체 목록에서 expired 상태 확인
    response = client.get("/todos")
    todos = response.json()
    assert todos[0]["expired"] == True   # 만료됨
    assert todos[1]["expired"] == False  # 만료 안됨
    assert todos[2]["expired"] == True   # 완료되었지만 만료됨
    
    # 만료된 할일만 조회 (완료된 것 제외)
    expired_response = client.get("/todos/expired")
    expired_todos = expired_response.json()
    assert len(expired_todos) == 1  # 완료되지 않은 만료된 할일만
    assert expired_todos[0]["title"] == "Expired"

def test_is_expired_function():
    from main import is_expired
    
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    assert is_expired(yesterday) == True
    assert is_expired(tomorrow) == False
    assert is_expired(None) == False
    assert is_expired("invalid-date") == False
