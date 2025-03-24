from fastapi import FastAPI, HTTPException, APIRouter, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
import subprocess
import openai
import boto3
import os
import textwrap
import re

app = FastAPI()
router = APIRouter(prefix="/api")

PROJECTS_DIR = "/app/workspaces"
os.makedirs(PROJECTS_DIR, exist_ok=True)

dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
s3_client = boto3.client("s3", region_name="us-east-2")
table = dynamodb.Table("ai-code-history")

openai.api_key = os.getenv("OPENAI_API_KEY")

class CodeRequest(BaseModel):
    command: str = ""
    filename: str = "main.py"
    project: str = "default_project"

class SearchFilters(BaseModel):
    project: str
    command: str = None
    date: str = None

# ---------- Funções auxiliares ----------
def upload_code_to_s3(code: str, project: str, filename: str = "main.py"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    key = f"{project}/{timestamp}_{filename}"
    s3_client.put_object(Bucket="ai-dev-assistant-code-history", Key=key, Body=code.encode("utf-8"))
    print(f"Código salvo no S3 em: {key}")

def save_to_dynamodb(project: str, filename: str, command: str, code: str, output: str, errors: str):
    timestamp = datetime.utcnow().isoformat()
    table.put_item(Item={
        "project_id": project,
        "timestamp": timestamp,
        "filename": filename,
        "command": command,
        "code": code,
        "output": output,
        "errors": errors
    })
    print(f"Dados salvos no DynamoDB: {timestamp}")

# ---------- Endpoints API ----------
@router.get("/")
def root():
    return {"message": "API está rodando corretamente com prefixo /api!"}

@router.post("/generate_code/")
def generate_code(request: CodeRequest):
    path = os.path.join(PROJECTS_DIR, request.project)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, request.filename)

    # OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Você é um assistente que escreve código funcional. Retorne apenas o código."},
            {"role": "user", "content": request.command}
        ]
    )
    code = re.sub(r"```[a-zA-Z]*\n|```", "", response["choices"][0]["message"]["content"]).strip()

    with open(file_path, "w") as f:
        f.write(code)

    upload_code_to_s3(code, request.project, request.filename)

    result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)

    save_to_dynamodb(request.project, request.filename, request.command, code, result.stdout, result.stderr)

    return {
        "message": "Código gerado com sucesso!",
        "file": file_path,
        "output": result.stdout,
        "errors": result.stderr
    }

@router.post("/run_code/")
def run_code(request: CodeRequest):
    file_path = os.path.join(PROJECTS_DIR, request.project, request.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)
    return {"output": result.stdout, "errors": result.stderr}

@router.get("/get_code/", response_class=PlainTextResponse)
def get_code(project: str = "default_project", filename: str = "main.py"):
    file_path = os.path.join(PROJECTS_DIR, project, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    with open(file_path, "r") as f:
        return f.read()

@router.get("/get_last_session/")
def get_last_session(project: str):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('project_id').eq(project),
            ScanIndexForward=False,
            Limit=1
        )
        return response["Items"][0] if response["Items"] else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_sessions_by_command/")
def get_sessions_by_command(project: str, command: str):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('project_id').eq(project)
        )
        filtered = [item for item in response["Items"] if command.lower() in item["command"].lower()]
        return filtered
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_sessions_by_date/")
def get_sessions_by_date(project: str, date: str):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('project_id').eq(project)
        )
        filtered = [item for item in response["Items"] if item["timestamp"].startswith(date)]
        return filtered
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search_history/")
def search_history(filters: SearchFilters):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('project_id').eq(filters.project)
        )
        items = response["Items"]
        if filters.command:
            items = [i for i in items if filters.command.lower() in i["command"].lower()]
        if filters.date:
            items = [i for i in items if i["timestamp"].startswith(filters.date)]
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
app.include_router(router)
print("Pipeline funcionando!")