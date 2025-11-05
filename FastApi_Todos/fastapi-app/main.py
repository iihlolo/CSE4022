from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import json
import os
from datetime import date
from typing import Optional


app = FastAPI()

# To-Do 항목 모델
class TodoItem(BaseModel):
    id: int
    title: str
    description: str
    completed: bool
    due_date: Optional[str] = None

# JSON 파일 경로
TODO_FILE = "todo.json"

# JSON 파일에서 To-Do 항목 로드
def load_todos():
    if os.path.exists(TODO_FILE):
        try:
            with open(TODO_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return []
    return []

# JSON 파일에 To-Do 항목 저장
def save_todos(todos):
    with open(TODO_FILE, "w", encoding="utf-8") as file:
        json.dump(todos, file, indent=4, ensure_ascii=False)

# 다음 사용 가능한 ID 생성
def get_next_id():
    todos = load_todos()
    if todos:
        return max(t["id"] for t in todos) + 1
    return 1

# 기한 만료 여부 확인
def is_expired(due_date_str: str) -> bool:
    if not due_date_str:
        return False
    try:
        due_date = date.fromisoformat(due_date_str)
        return due_date < date.today()
    except ValueError:
        return False

# To-Do 목록 조회
@app.get("/todos", response_model=list[dict])
def get_todos():
    todos = load_todos()
    for todo in todos:
        todo["expired"] = is_expired(todo.get("due_date"))
    return todos

# 신규 To-Do 항목 추가
@app.post("/todos", response_model=TodoItem)
def create_todo(todo: TodoItem):
    todos = load_todos()
    # ID 자동 할당
    todo.id = get_next_id()
    todos.append(todo.dict())
    save_todos(todos)
    return todo

# To-Do 항목 수정
@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, updated_todo: TodoItem):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo["id"] == todo_id:
            updated_todo.id = todo_id  # ID는 변경하지 않음
            todos[i] = updated_todo.dict()
            save_todos(todos)
            return updated_todo
    raise HTTPException(status_code=404, detail="To-Do item not found")

# To-Do 항목 완료 상태 토글
@app.patch("/todos/{todo_id}/toggle", response_model=TodoItem)
def toggle_todo_completion(todo_id: int):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo["id"] == todo_id:
            todo["completed"] = not todo["completed"]
            todos[i] = todo
            save_todos(todos)
            return TodoItem(**todo)
    raise HTTPException(status_code=404, detail="To-Do item not found")

# To-Do 항목 삭제
@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int):
    todos = load_todos()
    original_count = len(todos)
    todos = [todo for todo in todos if todo["id"] != todo_id]
    if len(todos) == original_count:
        raise HTTPException(status_code=404, detail="To-Do item not found")
    save_todos(todos)
    return {"message": "To-Do item deleted"}

# 만료된 할일 목록 조회
@app.get("/todos/expired")
def get_expired_todos():
    todos = load_todos()
    expired_todos = []
    for todo in todos:
        if is_expired(todo.get("dueDate")) and not todo.get("completed", False):
            todo["expired"] = True
            expired_todos.append(todo)
    return expired_todos

# HTML 파일 서빙
@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as file:
            content = file.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="HTML template not found")