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

# Caminho onde os projetos são armazenados
PROJECTS_DIR = "/app/workspaces"
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Inicializa clientes da AWS
dynamodb_client = boto3.client("dynamodb", region_name="us-east-2")
dynamodb_resource = boto3.resource("dynamodb", region_name="us-east-2")

# Define chave da API OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Função de upload para o S3 (versionamento de código)
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

# Endpoint para listar arquivos versionados no S3
@router.get("/list_versions/")
def list_versions(project: str = "default_project"):
    try:
        s3_client = boto3.client("s3", region_name="us-east-2")
        response = s3_client.list_objects_v2(
            Bucket="ai-dev-assistant-code-history",
            Prefix=f"{project}/"
        )

        files = []
        for obj in response.get("Contents", []):
            files.append({
                "filename": obj["Key"],
                "last_modified": obj["LastModified"].isoformat(),
                "size": obj["Size"]
            })

        return {"project": project, "versions": files}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar versões: {str(e)}")

# Estruturas das requisições
class CodeRequest(BaseModel):
    command: str = ""
    filename: str = "main.py"
    project: str = "default_project"

class GitHubConfig(BaseModel):
    project: str = "default_project"
    github_url: str

class DynamoDBRequest(BaseModel):
    table_name: str
    item: dict

# Teste simples da API
@router.get("/")
def root():
    return {"message": "API está rodando corretamente com prefixo /api!"}

# Geração de código com base no prompt
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

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(clean_code)

    # Versionamento no S3
    upload_code_to_s3(clean_code, request.project, request.filename)

    return {"message": "Código gerado com sucesso!", "file": file_path}

# Executa o código salvo
@router.post("/run_code/")
def run_code(request: CodeRequest):
    project_path = os.path.join(PROJECTS_DIR, request.project)
    file_path = os.path.join(project_path, request.filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)
    return {"output": result.stdout, "errors": result.stderr}

# Retorna o código salvo em texto puro
@router.get("/get_code/", response_class=PlainTextResponse)
def get_generated_code(project: str = "default_project", filename: str = "main.py"):
    file_path = os.path.join(PROJECTS_DIR, project, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

# Corrige o código automaticamente se houver erro
@router.post("/auto_fix_code/")
def auto_fix_code(request: CodeRequest):
    project_path = os.path.join(PROJECTS_DIR, request.project)
    file_path = os.path.join(project_path, request.filename)

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

        with open(file_path, "w", encoding="utf-8") as file:
            file.write(fixed_code)

    return {
        "output": result.stdout,
        "errors": result.stderr,
        "message": "Tentativas de correção esgotadas."
    }

# Monta os arquivos do frontend
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")

# Aplica as rotas da API
app.include_router(router)

print("Pipeline funcionando!")