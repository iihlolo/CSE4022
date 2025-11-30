from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, computed_field, ConfigDict, Field
import json
import os
from datetime import date
from typing import Optional, List
import logging
import time
from multiprocessing import Queue
from os import getenv
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from logging_loki import LokiQueueHandler

TODO_NOT_FOUND_MSG = "To-Do item not found"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Prometheus 메트릭스 엔드포인트 (/metrics)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

loki_logs_handler = LokiQueueHandler(
    Queue(-1),
    url=getenv("LOKI_ENDPOINT"),
    tags={"application": "fastapi"},
    version="1",
)

# Custom access logger (ignore Uvicorn's default logging)
custom_logger = logging.getLogger("custom.access")
custom_logger.setLevel(logging.INFO)

# Add Loki handler (assuming `loki_logs_handler` is correctly configured)
custom_logger.addHandler(loki_logs_handler)

async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time  # Compute response time

    log_message = (
        f'{request.client.host} - "{request.method} {request.url.path} HTTP/1.1" {response.status_code} {duration:.3f}s'
    )

    # **Only log if duration exists**
    if duration:
        custom_logger.info(log_message)

    return response

# To-Do 항목 모델
class TodoItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    title: str
    completed: bool
    due_date: Optional[str] = None
    tags: Optional[List[str]] = []

class TodoCreate(BaseModel):
    title: str
    completed: bool = False
    due_date: Optional[str] = None
    tags: Optional[List[str]] = []

class TodoUpdate(BaseModel):
    title: str
    completed: bool
    due_date: Optional[str] = None
    tags: Optional[List[str]] = []

class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    completed: bool
    due_date: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def expired(self) -> bool:
        return is_expired(self.due_date) if self.due_date else False

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
def is_expired(due_date_str: Optional[str]) -> bool:
    if not due_date_str:
        return False
    try:
        due_date = date.fromisoformat(due_date_str)
        return due_date < date.today()
    except (ValueError, TypeError):
        return False

# 만료된 할일 목록 조회
@app.get("/todos/expired", response_model=list[TodoResponse])
def get_expired_todos():
    todos = load_todos()
    expired_todos = []
    for todo in todos:
        todo_response = TodoResponse(**todo)
        if todo_response.expired and not todo.get("completed", False):
            expired_todos.append(todo_response)
    return expired_todos

# To-Do 목록 조회
@app.get("/todos", response_model=list[TodoResponse])
def get_todos():
    todos = load_todos()
    return [TodoResponse(**todo) for todo in todos]

# 신규 To-Do 항목 추가
@app.post("/todos", response_model=TodoItem)
def create_todo(todo: TodoCreate):
    todos = load_todos()
    new_todo = TodoItem(
        id=get_next_id(),
        title=todo.title,
        completed=todo.completed,
        due_date=todo.due_date,
        tags=todo.tags
    )
    todos.append(new_todo.model_dump())
    save_todos(todos)
    return new_todo

# To-Do 항목 수정
@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, updated_todo: TodoUpdate):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo["id"] == todo_id:
            updated_item = TodoItem(
                id=todo_id,
                title=updated_todo.title,
                completed=updated_todo.completed,
                due_date=updated_todo.due_date,
                tags=updated_todo.tags
            )
            todos[i] = updated_item.model_dump()
            save_todos(todos)
            return updated_item
    raise HTTPException(status_code=404, detail=TODO_NOT_FOUND_MSG)

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
    raise HTTPException(status_code=404, detail=TODO_NOT_FOUND_MSG)

# To-Do 항목 삭제
@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int):
    todos = load_todos()
    original_count = len(todos)
    todos = [todo for todo in todos if todo["id"] != todo_id]
    if len(todos) == original_count:
        raise HTTPException(status_code=404, detail=TODO_NOT_FOUND_MSG)
    save_todos(todos)
    return {"message": "To-Do item deleted"}

# HTML 파일 서빙
@app.get("/", response_class=HTMLResponse)
def read_root():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as file:
            content = file.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="HTML template not found")