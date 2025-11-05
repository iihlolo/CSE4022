import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from main import app, save_todos, load_todos, TodoItem

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # 테스트 전 초기화
    save_todos([])
    yield
    # 테스트 후 정리
    save_todos([])

def test_get_todos_empty():
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []

def test_get_todos_with_items():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    response = client.get("/todos")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Test"

def test_create_todo():
    todo = {"id": 1, "title": "Test", "description": "Test description", "completed": False}
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    returned_todo = response.json()
    assert returned_todo["title"] == "Test"
    assert "id" in returned_todo

def test_create_todo_invalid():
    todo = {"id": 1, "title": "Test"}
    response = client.post("/todos", json=todo)
    assert response.status_code == 422

def test_update_todo():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    updated_todo = {"id": 1, "title": "Updated", "description": "Updated description", "completed": True}
    response = client.put("/todos/1", json=updated_todo)
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"

def test_update_todo_not_found():
    updated_todo = {"id": 1, "title": "Updated", "description": "Updated description", "completed": True}
    response = client.put("/todos/1", json=updated_todo)
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
    assert response.json()["detail"] == "To-Do item not found"

def test_toggle_todo_completed():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    response = client.patch("/todos/1/toggle")
    assert response.status_code == 200
    assert response.json()["completed"] == True
    assert response.json()["title"] == "Test"

def test_toggle_todo_uncompleted():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=True)
    save_todos([todo.dict()])
    response = client.patch("/todos/1/toggle")
    assert response.status_code == 200
    assert response.json()["completed"] == False
    assert response.json()["title"] == "Test"

def test_toggle_todo_multiple_times():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.dict()])
    
    response1 = client.patch("/todos/1/toggle")
    assert response1.status_code == 200
    assert response1.json()["completed"] == True
    
    response2 = client.patch("/todos/1/toggle")
    assert response2.status_code == 200
    assert response2.json()["completed"] == False
    
    response3 = client.patch("/todos/1/toggle")
    assert response3.status_code == 200
    assert response3.json()["completed"] == True

def test_toggle_todo_not_found():
    response = client.patch("/todos/1/toggle")
    assert response.status_code == 404
    assert response.json()["detail"] == "To-Do item not found"

def test_toggle_todo_with_multiple_items():
    todos = [
        TodoItem(id=1, title="Test1", description="Test description1", completed=False),
        TodoItem(id=2, title="Test2", description="Test description2", completed=True),
        TodoItem(id=3, title="Test3", description="Test description3", completed=False)
    ]
    save_todos([todo.dict() for todo in todos])
    
    response = client.patch("/todos/2/toggle")
    assert response.status_code == 200
    assert response.json()["completed"] == False
    
    all_todos = client.get("/todos").json()
    assert len(all_todos) == 3
    assert all_todos[0]["completed"] == False
    assert all_todos[1]["completed"] == False
    assert all_todos[2]["completed"] == False
