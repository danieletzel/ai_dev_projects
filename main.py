Aqui está um exemplo básico de um servidor web Flask em Python que exibe a mensagem "Bem-vindo ao meu site!" na página inicial:

```python
# Importar o módulo Flask
from flask import Flask

# Criar uma nova instância do Flask
app = Flask(__name__)

# Criar uma rota para a página inicial
@app.route('/')
def home():
    # Retornar uma mensagem de boas vindas
    return 'Bem-vindo ao meu site!'

# Executar o servidor
if __name__ == '__main__':
    app.run(debug=True)
```

Para executar este servidor, você precisará ter Flask instalado na sua máquina. Você pode instalar o Flask usando pip:

```
pip install flask
```

Uma vez que o Flask está instalado, você pode executar o servidor com o seguinte comando:

```
python filename.py
```

Substitua 'filename.py' com o nome do seu arquivo Python. Este servidor estará em execução no endereço 'http://localhost:5000'.
Neste código, `debug=True` está configurado para fornecer mensagens de erro mais detalhadas caso ocorra algum erro. Em um ambiente de produção, isso precisa ser desativado.