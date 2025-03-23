import os
import subprocess
import openai
import boto3
import re
import textwrap

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

    # Tenta até 3 vezes corrigir e executar o código
    for _ in range(3):
        result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            return {"output": result.stdout, "message": "Código executado com sucesso sem erros."}

        # Carrega o código atual com erro
        with open(file_path, "r", encoding="utf-8") as f:
            current_code = f.read()

        # Gera prompt de correção
        prompt = textwrap.dedent(f"""
            O código abaixo está com erro. Corrija o erro retornado no traceback:

            Código atual:
            {current_code}

            Erro encontrado:
            {result.stderr}

            Retorne apenas o código corrigido, sem explicações.
        """).strip()

        # Solicita correção ao modelo
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