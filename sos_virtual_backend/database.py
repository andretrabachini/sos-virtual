from flask_sqlalchemy import SQLAlchemy

# Inicializa o ORM do SQLAlchemy
db = SQLAlchemy()

def configurar_banco(app):
    # Configuração da URI de conexão para o MySQL local
    # Formato: mysql+pymysql://usuario:senha@localhost/nome_do_banco
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:suasenha@localhost/sos_virtual'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Inicializa a aplicação com o banco de dados
    db.init_app(app)