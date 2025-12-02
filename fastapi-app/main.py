from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, computed_field, ConfigDict, Field
from datetime import date, datetime
from typing import Optional, List
import logging
import time
from multiprocessing import Queue
from motor.motor_asyncio import AsyncIOMotorClient
from os import getenv
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from logging_loki import LokiQueueHandler

TODO_NOT_FOUND_MSG = "To-Do item not found"

MONGODB_URL = getenv("MONGODB_URL", "mongodb://admin:admin@mongo:27017/todo_db?authSource=admin")
client = AsyncIOMotorClient(MONGODB_URL)
db = client.get_default_database()
tasks_collection = db["tasks"]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

loki_logs_handler = LokiQueueHandler(
    Queue(-1),
    url=getenv("LOKI_ENDPOINT"),
    tags={"application": "fastapi"},
    version="1",
)

custom_logger = logging.getLogger("custom.access")
custom_logger.setLevel(logging.INFO)
custom_logger.addHandler(loki_logs_handler)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    log_message = (
        f'{request.client.host} - "{request.method} {request.url.path} HTTP/1.1" {response.status_code} {duration:.3f}s'
    )

    if duration:
        custom_logger.info(log_message)

    return response

class TodoItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    title: str
    completed: bool
    due_date: Optional[str] = None
    tags: Optional[List[str]] = []
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

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
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    @computed_field
    @property
    def expired(self) -> bool:
        return is_expired(self.due_date) if self.due_date else False

async def get_next_task_id() -> int:
    last_task = await tasks_collection.find_one(sort=[("id", -1)])
    if last_task:
        return last_task["id"] + 1
    return 1

def is_expired(due_date_str: Optional[str]) -> bool:
    if not due_date_str:
        return False
    try:
        due_date = date.fromisoformat(due_date_str)
        return due_date < date.today()
    except (ValueError, TypeError):
        return False

def task_to_response(task: dict) -> TodoResponse:
    task_copy = task.copy()
    task_copy.pop("_id", None)
    return TodoResponse(**task_copy)

def sort_tasks(tasks: List[dict]) -> List[dict]:
    def sort_key(task):
        completed = task.get("completed", False)
        due_date_str = task.get("due_date")
        expired = is_expired(due_date_str)
        has_date = bool(due_date_str) and not expired

        if completed:
            completed_at = task.get("completed_at")
            try:
                completed_time = datetime.fromisoformat(completed_at) if completed_at else datetime.min
            except (ValueError, TypeError):
                completed_time = datetime.min
            return (4, -completed_time.timestamp())
        
        if expired:
            try:
                due_date = datetime.fromisoformat(due_date_str + "T00:00:00") if len(due_date_str) == 10 else datetime.fromisoformat(due_date_str)
            except (ValueError, TypeError):
                due_date = datetime.max
            return (3, due_date.timestamp())
        
        if has_date:
            try:
                due_date = datetime.fromisoformat(due_date_str + "T00:00:00") if len(due_date_str) == 10 else datetime.fromisoformat(due_date_str)
            except (ValueError, TypeError):
                due_date = datetime.max
            return (2, due_date.timestamp())
        
        created_at = task.get("created_at") or "1970-01-01T00:00:00"
        try:
            created_time = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            created_time = datetime.min
        return (1, -created_time.timestamp())
    
    return sorted(tasks, key=sort_key)

@app.get("/todos/expired", response_model=list[TodoResponse])
async def get_expired_todos():
    tasks = []
    cursor = tasks_collection.find({"completed": False})
    async for task in cursor:
        todo_response = task_to_response(task)
        if todo_response.expired:
            tasks.append(todo_response)
    return tasks

@app.get("/todos", response_model=list[TodoResponse])
async def get_todos():
    tasks = []
    cursor = tasks_collection.find()
    async for task in cursor:
        task.pop("_id", None)
        tasks.append(task)

    sorted_tasks = sort_tasks(tasks)

    return [TodoResponse(**task) for task in sorted_tasks]

@app.post("/todos", response_model=TodoItem)
async def create_todo(todo: TodoCreate):

    new_task = {
        "id": await get_next_task_id(),
        "title": todo.title,
        "completed": todo.completed,
        "due_date": todo.due_date,
        "tags": todo.tags or [],
        "created_at": datetime.now().isoformat(),
        "completed_at": None
    }

    await tasks_collection.insert_one(new_task)
    return TodoItem(**new_task)

@app.put("/todos/{todo_id}", response_model=TodoItem)
async def update_todo(todo_id: int, updated_todo: TodoUpdate):
    existing_task = await tasks_collection.find_one({"id": todo_id})
    if not existing_task:
        raise HTTPException(status_code=404, detail=TODO_NOT_FOUND_MSG)
    
    completed_at = existing_task.get("completed_at")
    if updated_todo.completed and not existing_task.get("completed"):
        completed_at = datetime.now().isoformat()
    elif not updated_todo.completed and existing_task.get("completed"):
        completed_at = None
    
    updated_task = {
        "title": updated_todo.title,
        "completed": updated_todo.completed,
        "due_date": updated_todo.due_date,
        "tags": updated_todo.tags or [],
        "completed_at": completed_at
    }

    await tasks_collection.update_one(
        {"id": todo_id},
        {"$set": updated_task}
    )
    
    task = await tasks_collection.find_one({"id": todo_id})
    task.pop("_id", None)
    return TodoItem(**task)

@app.patch("/todos/{todo_id}/toggle", response_model=TodoItem)
async def toggle_todo_completion(todo_id: int):
    task = await tasks_collection.find_one({"id": todo_id})

    if not task:
        raise HTTPException(status_code=404, detail=TODO_NOT_FOUND_MSG)
    
    new_completed_status = not task["completed"]

    update_data = {
        "completed": new_completed_status,
        "completed_at": datetime.now().isoformat() if new_completed_status else None
    }

    await tasks_collection.update_one(
        {"id": todo_id},
        {"$set": update_data}
    )

    task["completed"] = new_completed_status
    task["completed_at"] = update_data["completed_at"]
    task = await tasks_collection.find_one({"id": todo_id})
    task.pop("_id", None)
    return TodoItem(**task)

@app.delete("/todos/{todo_id}", response_model=dict)
async def delete_todo(todo_id: int):
    result = await tasks_collection.delete_one({"id": todo_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=TODO_NOT_FOUND_MSG)
    
    return {"message": "To-Do item deleted"}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as file:
            content = file.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="HTML template not found")