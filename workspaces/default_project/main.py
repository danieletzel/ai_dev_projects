from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/run", methods=["POST"])
def run_code():
    try:
        data = request.get_json()
        filename = data.get("filename", "main.py")
        code = data.get("code", "")

        filepath = os.path.join("/app/workspaces/default_project", filename)

        # Salva o código recebido no arquivo
        with open(filepath, "w") as f:
            f.write(code)

        # Executa o código com subprocess
        result = subprocess.run(
            ["python", filepath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )

        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }), 200

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Execução do código excedeu o tempo limite"}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)