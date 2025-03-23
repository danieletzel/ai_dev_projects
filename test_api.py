from pydantic import BaseModel


class CodeRequest(BaseModel):
    command: str
    filename: str
    project: str

@app.get("/")
def read_root():
    return {"message": "API está rodando!"}

@app.post("/generate_code/")
def generate_code(request: CodeRequest):
    return {"message": f"Código gerado para {request.filename} no projeto {request.project}"}