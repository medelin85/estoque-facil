from datetime import date, timedelta
import re
import sqlite3
import time
import pytest
from werkzeug.security import generate_password_hash
from estoque_facil import create_app, services
from estoque_facil.db import get_db

@pytest.fixture
def app(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'test-secret-only','DATABASE':str(tmp_path/'test.db')})
    with app.app_context():
        db=get_db()
        db.execute('INSERT INTO users(login,password_hash) VALUES(?,?)',('operador',generate_password_hash('senha de teste longa')))
        db.commit()
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def csrf(client,path):
    body=client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"',body).group(1)

def login(client):
    return client.post('/login',data={'csrf_token':csrf(client,'/login'),'login':'operador','password':'senha de teste longa'})

def seed():
    p=services.add_product('Arroz 1 kg','un','0')
    l=services.add_lot(p,'ARR-001',(date.today()+timedelta(days=5)).isoformat())
    return p,l

@pytest.mark.parametrize('raw,unit,expected',[('12','un',12),('1.250','kg',1250)])
def test_base_units(raw,unit,expected):
    assert services.amount(raw,unit)==expected

@pytest.mark.parametrize('raw,unit',[('0','un'),('-1','un'),('1.5','un'),('NaN','kg'),('Infinity','kg'),('1.0001','kg')])
def test_invalid_quantity(raw,unit):
    with pytest.raises(ValueError): services.amount(raw,unit)

@pytest.mark.parametrize('days,balance,label',[(-1,1,'vencido'),(0,1,'hoje'),(5,1,'5 dias'),(31,1,'Dentro'),(-1,0,'Sem saldo')])
def test_alert_boundaries(days,balance,label):
    today=date(2026,11,17)
    assert label in services.expiry_status((today+timedelta(days=days)).isoformat(),balance,today)[1]

def test_lot_unique_and_zero_balance(app):
    with app.app_context():
        p,l=seed()
        assert services.balance(l)==0
        with pytest.raises(ValueError): services.add_lot(p,'ARR-001','2026-11-22')
        with pytest.raises(ValueError): services.add_lot(p,'OTHER','not-date')

def test_stock_transaction_and_expired_loss(app):
    with app.app_context():
        p,l=seed()
        services.move(l,1,'entrada','12','compra')
        with pytest.raises(ValueError): services.move(l,1,'saida','13','venda')
        assert services.balance(l)==12
        services.move(l,1,'saida','2','venda')
        assert services.balance(l)==10
        with pytest.raises(ValueError): services.move(l,1,'entrada','1','venda')
        future=date.today()+timedelta(days=10)
        with pytest.raises(ValueError): services.move(l,1,'saida','1','venda',future)
        services.move(l,1,'saida','1','perda_vencimento',future)
        assert services.balance(l)==9

def test_safe_search_and_html(app):
    with app.app_context():
        seed()
        assert services.stock("' OR 1=1 --")[0]==[]
        assert get_db().execute('SELECT COUNT(*) FROM products').fetchone()[0]==1
        with pytest.raises(ValueError): services.add_product('<script>alert(1)</script>','un','0')

def test_authenticated_full_flow(client,app):
    assert client.get('/stock').status_code==302
    assert login(client).status_code==302
    assert client.post('/products/new',data={'csrf_token':csrf(client,'/products/new'),'name':'Arroz 1 kg','unit':'un','minimum':'0'}).status_code==302
    assert client.post('/lots/new',data={'csrf_token':csrf(client,'/lots/new'),'product_id':'1','code':'ARR-001','expiry':(date.today()+timedelta(days=5)).isoformat()}).status_code==302
    body=client.get('/stock').get_data(as_text=True)
    assert 'Sem saldo' in body
    response=client.post('/movements/new',data={'csrf_token':csrf(client,'/movements/new'),'lot_id':'1','kind':'entrada','quantity':'12','reason':'compra'},follow_redirects=True)
    assert '12 un' in response.get_data(as_text=True)
    assert 'Vence em 5 dias' in response.get_data(as_text=True)

def test_csrf_and_session_revocation(client,app):
    login(client)
    with client.session_transaction() as s:
        old=dict(s)
    assert client.post('/products/new',data={'name':'No token'}).status_code==400
    assert client.post('/logout',data={'csrf_token':csrf(client,'/')}).status_code==302
    with client.session_transaction() as s:
        s.update(old)
    assert client.get('/stock').status_code==302

def test_session_timeout_and_inactive(client,app):
    login(client)
    with app.app_context():
        db=get_db()
        db.execute('UPDATE users SET last_seen=?',(time.time()-1900,)); db.commit()
    assert client.get('/stock').status_code==302
    login(client)
    with app.app_context():
        db=get_db(); db.execute('UPDATE users SET active=0'); db.commit()
    assert client.get('/stock').status_code==302

def test_login_lock_and_hash(client,app):
    for _ in range(5):
        client.post('/login',data={'csrf_token':csrf(client,'/login'),'login':'operador','password':'wrong'})
    assert login(client).status_code==200
    with app.app_context():
        u=get_db().execute('SELECT * FROM users').fetchone()
        assert u['locked_until']>time.time()
        assert u['password_hash'].startswith('scrypt:')
        assert 'senha de teste longa' not in u['password_hash']

def test_error_preserves_fields(client):
    login(client)
    response=client.post('/lots/new',data={'csrf_token':csrf(client,'/lots/new'),'code':'ABC','expiry':'wrong','product_id':'99'})
    body=response.get_data(as_text=True)
    assert 'value="ABC"' in body and 'data de validade válida' in body

def test_pagination_and_foreign_keys(app):
    with app.app_context():
        p,_=seed()
        for i in range(22): services.add_lot(p,f'L{i}','2026-12-01')
        rows,more=services.stock(page=1)
        assert len(rows)==20 and more
        assert len(services.stock(page=2)[0])==3
        with pytest.raises(sqlite3.IntegrityError):
            get_db().execute("INSERT INTO lots(product_id,code,expiry) VALUES(999,'X','2026-12-01')")

def test_headers_escape_and_health(client,app):
    login(client)
    response=client.get('/stock?q=%3Cscript%3E')
    body=response.get_data(as_text=True)
    assert '<script>' not in body and '&lt;script&gt;' in body
    assert "script-src 'none'" in response.headers['Content-Security-Policy']
    assert 'HttpOnly' in response.headers.get('Set-Cookie','')
    assert client.get('/health').json=={'status':'ok'}

def test_create_account_and_backup(app,tmp_path):
    runner=app.test_cli_runner()
    assert runner.invoke(args=['create-user','new','--password','short']).exit_code!=0
    assert runner.invoke(args=['create-user','new','--password','outra senha muito longa']).exit_code==0
    dest=tmp_path/'backup.db'
    assert runner.invoke(args=['backup-db',str(dest)]).exit_code==0
    with sqlite3.connect(dest) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==2
