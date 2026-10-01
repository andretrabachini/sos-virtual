-- Criação do banco de dados (caso ainda não exista)
CREATE DATABASE IF NOT EXISTS sos_virtual;
USE sos_virtual;

-- Tabela de Usuários (Isolamento e Segurança)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NOT NULL
);

-- Tabela de Nós / Vértices do Grafo (Contas, Categorias, Metas, Rendas)
CREATE TABLE IF NOT EXISTS nos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(50) NOT NULL, -- Ex: 'conta', 'categoria', 'meta', 'renda'
    FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabela de Arestas / Conexões (Transações Financeiras Direcionadas)
CREATE TABLE IF NOT EXISTS arestas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    origem_id INT NOT NULL,  -- De onde o dinheiro sai (aponta para nos.id)
    destino_id INT NOT NULL, -- Para onde o dinheiro vai (aponta para nos.id)
    peso DECIMAL(10, 2) NOT NULL, -- Valor monetário em R$
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (origem_id) REFERENCES nos(id) ON DELETE CASCADE,
    FOREIGN KEY (destino_id) REFERENCES nos(id) ON DELETE CASCADE
)