# ... [IMPORTS E INICIALIZAÇÕES IGUAIS]
import os
import subprocess
import openai
import boto3
import re
import textwrap
from datetime import datetime

from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()
router = APIRouter(prefix="/api")

PROJECTS_DIR = "/app/workspaces"
os.makedirs(PROJECTS_DIR, exist_ok=True)

dynamodb_client = boto3.client("dynamodb", region_name="us-east-2")
dynamodb_resource = boto3.resource("dynamodb", region_name="us-east-2")

openai.api_key = os.getenv("OPENAI_API_KEY")

# --- S3 ---
def upload_code_to_s3(code: str, project: str, filename: str = "main.py"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    s3_key = f"{project}/{timestamp}_{filename}"
    try:
        boto3.client("s3", region_name="us-east-2").put_object(
            Bucket="ai-dev-assistant-code-history",
            Key=s3_key,
            Body=code.encode("utf-8")
        )
        print(f"Código salvo no S3 em: {s3_key}")
    except Exception as e:
        print(f"Erro ao salvar código no S3: {e}")

# --- DynamoDB ---
def save_to_dynamodb(project: str, filename: str, command: str, code: str, output: str, errors: str):
    timestamp = datetime.utcnow().isoformat()
    try:
        table = dynamodb_resource.Table("ai-code-history")
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
    except Exception as e:
        print(f"Erro ao salvar no DynamoDB: {e}")

# --- ENDPOINTS ---
@router.get("/")
def root():
    return {"message": "API está rodando corretamente com prefixo /api!"}

class CodeRequest(BaseModel):
    command: str = ""
    filename: str = "main.py"
    project: str = "default_project"

@router.post("/generate_code/")
def generate_code(request: CodeRequest):
    project_path = os.path.join(PROJECTS_DIR, request.project)
    os.makedirs(project_path, exist_ok=True)
    file_path = os.path.join(project_path, request.filename)

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Você é um assistente de desenvolvimento que gera código funcional. Retorne apenas o código, sem explicações."},
            {"role": "user", "content": request.command}
        ]
    )

    raw_code = response["choices"][0]["message"]["content"]
    clean_code = re.sub(r"```[a-zA-Z]*\n|```", "", raw_code).strip()

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(clean_code)

    upload_code_to_s3(clean_code, request.project, request.filename)

    result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)

    save_to_dynamodb(
        project=request.project,
        filename=request.filename,
        command=request.command,
        code=clean_code,
        output=result.stdout,
        errors=result.stderr
    )

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
def get_generated_code(project: str = "default_project", filename: str = "main.py"):
    file_path = os.path.join(PROJECTS_DIR, project, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

@router.post("/auto_fix_code/")
def auto_fix_code(request: CodeRequest):
    file_path = os.path.join(PROJECTS_DIR, request.project, request.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    for _ in range(3):
        result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return {"output": result.stdout, "message": "Código executado com sucesso sem erros."}

        with open(file_path, "r", encoding="utf-8") as f:
            current_code = f.read()

        prompt = textwrap.dedent(f"""
        O código abaixo está com erro. Corrija o erro retornado no traceback:

        Código atual:
        {current_code}

        Erro encontrado:
        {result.stderr}

        Retorne apenas o código corrigido, sem explicações.
        """).strip()

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Você é um assistente de desenvolvimento que corrige erros em código."},
                {"role": "user", "content": prompt}
            ]
        )

        fixed_code = re.sub(r"```[a-zA-Z]*\n|```", "", response["choices"][0]["message"]["content"]).strip()
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)

    return {"output": result.stdout, "errors": result.stderr, "message": "Tentativas de correção esgotadas."}

# --- NOVO: Listagem de versões no S3
@router.get("/list_versions/")
def list_versions(project: str = "default_project"):
    try:
        s3 = boto3.client("s3", region_name="us-east-2")
        response = s3.list_objects_v2(
            Bucket="ai-dev-assistant-code-history",
            Prefix=f"{project}/"
        )
        return {
            "project": project,
            "versions": [
                {
                    "filename": obj["Key"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "size": obj["Size"]
                } for obj in response.get("Contents", [])
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar versões: {e}")

# --- NOVO: Rollback manual
@router.post("/rollback_version/")
def rollback_version(project: str, version_key: str):
    try:
        s3 = boto3.client("s3", region_name="us-east-2")
        response = s3.get_object(
            Bucket="ai-dev-assistant-code-history",
            Key=version_key
        )
        code = response["Body"].read().decode("utf-8")

        filename = version_key.split("/")[-1].split("_", 1)[-1]
        path = os.path.join(PROJECTS_DIR, project)
        os.makedirs(path, exist_ok=True)
        local_file = os.path.join(path, filename)

        with open(local_file, "w", encoding="utf-8") as f:
            f.write(code)

        return {"message": "Rollback realizado com sucesso.", "file": local_file}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no rollback: {e}")

# --- Frontend Mount
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
app.include_router(router)

print("Pipeline funcionando!")