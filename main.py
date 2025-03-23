from fastapi import FastAPI
from ai_dev_assistant import app as api_app

app = api_app  # Referência ao app dentro do ai_dev_assistant.py

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)