"""Entrada Gunicorn; inicialização restrita à demonstração fictícia."""
from datetime import date, timedelta
import secrets
from werkzeug.security import generate_password_hash
from estoque_facil import create_app, services
from estoque_facil.db import get_db

app=create_app()
if app.config['DEMO_MODE']:
    with app.app_context():
        db=get_db()
        if not db.execute('SELECT id FROM users WHERE login=?',('demonstracao',)).fetchone():
            with db:
                uid=db.execute('INSERT INTO users(login,password_hash) VALUES(?,?)',('demonstracao',generate_password_hash(secrets.token_urlsafe(32)))).lastrowid
            pid=services.add_product('Arroz branco 1 kg (demonstração)','un','5')
            lot=services.add_lot(pid,'DEMO-001',(date.today()+timedelta(days=5)).isoformat())
            services.move(lot,uid,'entrada','12','saldo_inicial')
