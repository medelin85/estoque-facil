"""Aplicação monolítica: rotas, serviços e persistência separados."""
import os
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path
import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db, close_db, init_db
from . import services

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    secret=os.environ.get('SECRET_KEY')
    production=os.environ.get('APP_ENV')=='production'
    if production and (not secret or len(secret)<32):
        raise RuntimeError('Configure SECRET_KEY com pelo menos 32 caracteres em produção.')
    app.config.from_mapping(SECRET_KEY=secret or secrets.token_hex(32),
        DATABASE=os.environ.get('DATABASE_PATH',str(Path(app.instance_path)/'estoque.db')),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=production,
        MAX_CONTENT_LENGTH=16384, PERMANENT_SESSION_LIFETIME=1800)
    if test_config:
        app.config.update(test_config)
    app.teardown_appcontext(close_db)
    CSRFProtect(app)
    with app.app_context():
        init_db()

    @app.before_request
    def load_user():
        g.user=None
        uid=session.get('uid')
        if uid is not None:
            user=get_db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if user and user['active'] and user['token'] and secrets.compare_digest(user['token'],session.get('token','')) and time.time()-user['last_seen']<=1800:
                g.user=user
                db=get_db()
                with db:
                    db.execute('UPDATE users SET last_seen=? WHERE id=?',(time.time(),uid))
            else:
                session.clear()

    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        if production:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    def protected(view):
        @wraps(view)
        def wrapped(*args,**kwargs):
            if g.user is None:
                return redirect(url_for('login'))
            return view(*args,**kwargs)
        return wrapped

    @app.route('/login',methods=['GET','POST'])
    def login():
        error=None
        if request.method=='POST':
            login=request.form.get('login','').strip()[:100]
            password=request.form.get('password','')
            db=get_db()
            user=db.execute('SELECT * FROM users WHERE login=?',(login,)).fetchone()
            now=time.time()
            if user and user['active'] and user['locked_until']<=now and check_password_hash(user['password_hash'],password):
                token=secrets.token_hex(32)
                with db:
                    db.execute('UPDATE users SET token=?,last_seen=?,failures=0,locked_until=0 WHERE id=?',(token,now,user['id']))
                session.clear()
                session.permanent=True
                session.update(uid=user['id'],token=token)
                return redirect(url_for('index'))
            if user and user['locked_until']<=now:
                failures=user['failures']+1
                with db:
                    db.execute('UPDATE users SET failures=?,locked_until=? WHERE id=?',(0 if failures>=5 else failures,now+900 if failures>=5 else 0,user['id']))
            error='Não foi possível entrar. Confira os dados ou tente novamente mais tarde.'
        return render_template('login.html',error=error)

    @app.post('/logout')
    @protected
    def logout():
        db=get_db()
        with db:
            db.execute('UPDATE users SET token=NULL WHERE id=?',(g.user['id'],))
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @protected
    def index():
        return render_template('index.html')

    @app.route('/products/new',methods=['GET','POST'])
    @protected
    def product_new():
        error=None
        if request.method=='POST':
            try:
                services.add_product(request.form.get('name',''),request.form.get('unit',''),request.form.get('minimum','0'))
                flash('Produto cadastrado com sucesso.')
                return redirect(url_for('lot_new'))
            except ValueError as exc:
                error=str(exc)
        return render_template('form.html',kind='product',title='Cadastrar produto',error=error)

    @app.route('/lots/new',methods=['GET','POST'])
    @protected
    def lot_new():
        error=None
        if request.method=='POST':
            try:
                services.add_lot(request.form.get('product_id',''),request.form.get('code',''),request.form.get('expiry',''))
                flash('Lote cadastrado com sucesso. Registre uma entrada para atualizar o saldo.')
                return redirect(url_for('stock'))
            except ValueError as exc:
                error=str(exc)
            except sqlite3.IntegrityError:
                error='Não foi possível cadastrar. Confira o produto e o código do lote.'
        products=get_db().execute('SELECT * FROM products ORDER BY name').fetchall()
        return render_template('form.html',kind='lot',title='Cadastrar lote',products=products,error=error)

    @app.route('/movements/new',methods=['GET','POST'])
    @protected
    def movement_new():
        error=None
        if request.method=='POST':
            try:
                services.move(request.form.get('lot_id',''),g.user['id'],request.form.get('kind',''),request.form.get('quantity',''),request.form.get('reason',''))
                flash('Movimentação registrada com sucesso.')
                return redirect(url_for('stock'))
            except ValueError as exc:
                error=str(exc)
        lots=get_db().execute('SELECT l.*,p.name,p.unit FROM lots l JOIN products p ON p.id=l.product_id ORDER BY p.name,l.expiry').fetchall()
        return render_template('form.html',kind='movement',title='Registrar movimentação',lots=lots,error=error)

    @app.get('/stock')
    @protected
    def stock():
        search=request.args.get('q','').strip()[:100]
        try:
            page=max(1,min(int(request.args.get('page',1)),10000))
        except ValueError:
            page=1
        rows,more=services.stock(search,page)
        return render_template('stock.html',rows=rows,more=more,page=page,search=search,status=services.expiry_status)

    @app.get('/health')
    def health():
        get_db().execute('SELECT 1').fetchone()
        return {'status':'ok'}

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template('error.html',message='Formulário expirado ou inválido. Reabra a página e tente novamente.'),400

    @app.errorhandler(500)
    def server_error(error):
        return render_template('error.html',message='Não foi possível concluir a operação. Consulte os registros antes de tentar novamente.'),500

    @app.cli.command('create-user')
    @click.argument('login')
    @click.password_option(confirmation_prompt=True)
    def create_user(login,password):
        """Cria conta operacional sem cadastro público."""
        if len(password)<15 or len(password)>256:
            raise click.ClickException('Use senha de 15 a 256 caracteres.')
        login=services.text(login)
        db=get_db()
        try:
            with db:
                db.execute('INSERT INTO users(login,password_hash) VALUES(?,?)',(login,generate_password_hash(password,method='scrypt')))
        except sqlite3.IntegrityError:
            raise click.ClickException('Login já cadastrado.') from None
        click.echo('Conta criada.')

    @app.cli.command('backup-db')
    @click.argument('destination',type=click.Path())
    def backup_db(destination):
        """Destino deve ser privado e externo ao diretório público."""
        with sqlite3.connect(destination) as target:
            get_db().backup(target)
        click.echo('Backup concluído. Guarde uma cópia privada fora do servidor.')
    return app
