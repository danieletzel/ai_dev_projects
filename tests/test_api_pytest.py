
import requests

API_URL = "http://localhost:8000"

def test_root():
    response = requests.get(f"{API_URL}/")
    assert response.status_code == 200
    assert "API está rodando corretamente" in response.json()["message"]

def test_generate_code():
    payload = {
        "command": "def soma(a, b): return a + b",
        "filename": "main.py",
        "project": "default_project"
    }
    response = requests.post(f"{API_URL}/generate_code/", json=payload)
    assert response.status_code == 200
    assert "Código gerado com sucesso" in response.json()["message"]

def test_run_code_success():
    payload = {
        "command": "print('Executado com sucesso!')",
        "filename": "main.py",
        "project": "default_project"
    }
    response = requests.post(f"{API_URL}/run_code/", json=payload)
    assert response.status_code == 200
    assert "Executado com sucesso!" in response.json()["output"]

def test_run_code_divisao_por_zero():
    payload = {
        "command": "print(1 / 0)",
        "filename": "main.py",
        "project": "default_project"
    }
    response = requests.post(f"{API_URL}/run_code/", json=payload)
    assert response.status_code == 200
    assert "ZeroDivisionError" in response.json()["errors"]
