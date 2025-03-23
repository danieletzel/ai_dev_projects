from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "API do Code Runner está rodando!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
