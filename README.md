# Estoque Fácil — Controle de Produtos e Validades para um Pequeno Comércio

MVP acadêmico em Python 3.12, Flask e SQLite. Interface responsiva, cadastro de produtos e lotes, entradas e saídas e consulta paginada com alertas de validade. ODS 12, meta 12.3: apoiar redução de perdas evitáveis. Impacto social depende de validação e medição reais; não há resultados comunitários comprovados neste repositório.

## Executar no Windows PowerShell
Abra o PowerShell **na pasta que contém este README e requirements.txt**. Execute cada comando separadamente:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app run_local create-user operador
.\.venv\Scripts\python.exe run_local.py
```
A criação da conta pedirá uma senha de pelo menos 15 caracteres, sem exibi-la. Não existe senha padrão nem cadastro público. Abra http://127.0.0.1:5000. O banco é criado automaticamente em `instance/estoque.db`.

## Linux
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m flask --app run_local create-user operador
.venv/bin/python run_local.py
```

## Fluxo central
1. Cadastre produto com unidade `un` ou `kg`.
2. Cadastre lote e validade: saldo começa em zero.
3. Registre entrada de compra ou saldo inicial.
4. Consulte saldo e alertas. Saída não pode superar saldo. Venda de lote vencido é bloqueada, mas perda por vencimento pode ser registrada.

Unidades são inteiras; kg são armazenados em gramas inteiros para evitar arredondamento de ponto flutuante. Histórico de movimentos não tem edição/exclusão. Saldo é derivado desse histórico. Transação `BEGIN IMMEDIATE` protege leitura do saldo e gravação contra concorrência. Alertas: vencido, vence hoje e até 30 dias, apenas com saldo positivo. Consulte datas do servidor; configure seu fuso operacional antes do uso real.

## Arquitetura
- `estoque_facil/__init__.py`: fábrica Flask, autenticação, rotas e comandos administrativos.
- `services.py`: regras de estoque e validação.
- `db.py`: SQLite, esquema, restrições e fechamento de conexões.
- `templates/` e `static/`: Jinja2 e CSS sem dependência de JavaScript.
- `tests/`: testes unitários e de integração com banco temporário.

## Segurança e acessibilidade
Consultas parametrizadas, escape Jinja2, rejeição de HTML, CSRF, CSP, senha scrypt com salt, expiração após 30 minutos de inatividade, revogação de sessão no logout e bloqueio de 15 minutos após cinco erros consecutivos de login por conta. Uma nova sessão substitui a anterior. HTTPS/cookie Secure dependem de modo de produção e proxy TLS corretamente configurado. Não há limitação distribuída por IP; avaliar proteção adicional antes de exposição ampla. Logs devem ter acesso restrito e não conter formulários nem credenciais.

Rótulos associados, mensagens textuais, foco visível, link para pular conteúdo, controles com mínimo 48px e alertas com texto e símbolo. Dimensões, contraste, zoom e teclado ainda precisam de avaliação manual no navegador e com público externo. Testes automatizados não certificam acessibilidade nem segurança absoluta.

## Testes
```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest --cov=estoque_facil --cov-report=term-missing
```
No Windows, substitua `.venv/bin/python` por `.\.venv\Scripts\python.exe` e use `python -m pip` para instalar. Na execução local inicial: **24 testes passaram; cobertura Python 94%**. Cobertura não mede HTML/CSS. CI via GitHub Actions exige ao menos 85%; consulte o run para confirmar status na nuvem.

## Produção e cópias de segurança
Defina `APP_ENV=production`, `SECRET_KEY` aleatória com pelo menos 32 caracteres e `DATABASE_PATH` em diretório privado persistente. Não envie `.env`, banco, backups ou senhas ao GitHub. Use HTTPS e Gunicorn no Linux:
```bash
gunicorn 'estoque_facil:create_app()' --bind 0.0.0.0:8000 --workers 1
```
A conta deve ser criada no mesmo ambiente/configuração do servidor. Este projeto não inclui hospedagem paga nem deploy automático. Em plano com disco efêmero, use apenas dados fictícios e informe a possibilidade de perda. Uso operacional depende de disco persistente, backups e teste de restauração. `/health` verifica resposta e conectividade básica com SQLite; não substitui monitor externo ou validação completa.

```bash
.venv/bin/python -m flask --app run_local backup-db /diretorio/privado/backup.db
```
Agende cópia diária, transfira-a para destino privado fora do servidor e teste a restauração em instância isolada antes de operação real. Para restaurar, pare a aplicação e substitua o banco pela cópia validada, preservando permissões. SQLite limita múltiplos escritores; crescimento exigirá avaliar PostgreSQL.

## Limites e validação pendente
Sem PDV/fiscal, integrações com fornecedores, leitor de código de barras, sincronização offline ou alerta de estoque mínimo. O campo mínimo fica reservado à evolução. Cadastro simplificado não inclui peso unitário embalado; medir perdas de alimentos vendidos por unidade em kg exigirá registro externo de pesagem ou evolução do modelo. Nenhuma validação em campo, assinatura ou feedback é inventado. Rodadas de usabilidade, desempenho (mediana <=3s no perfil planejado) e portabilidade Windows precisam ser executadas e documentadas; execução local atual foi Linux.
