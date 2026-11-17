"""Regras de estoque independentes das telas."""
from datetime import date
from decimal import Decimal, InvalidOperation
from .db import get_db

def text(value, maximum=100):
    value = str(value).strip()
    if not value or len(value)>maximum or '<' in value or '>' in value:
        raise ValueError('Preencha o texto sem HTML e dentro do limite permitido.')
    return value

def amount(value, unit):
    try:
        number = Decimal(str(value))
        scaled = number * (1000 if unit == 'kg' else 1)
        if not scaled.is_finite() or scaled<=0 or scaled!=scaled.to_integral_value() or scaled>10**12:
            raise ValueError
        return int(scaled)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError('Informe quantidade positiva: unidades inteiras ou kg com até três casas decimais.') from None

def add_product(name, unit, minimum):
    name = text(name)
    if unit not in ('un','kg'):
        raise ValueError('Selecione uma unidade válida.')
    minimum = str(minimum).strip()
    base = 0 if minimum in ('','0','0.0','0.000') else amount(minimum,unit)
    db = get_db()
    with db:
        return db.execute('INSERT INTO products(name,unit,minimum) VALUES(?,?,?)',(name,unit,base)).lastrowid

def add_lot(product_id, code, expiry):
    code = text(code,40)
    try:
        expiry = date.fromisoformat(expiry).isoformat()
    except (TypeError, ValueError):
        raise ValueError('Informe uma data de validade válida.') from None
    db = get_db()
    if not db.execute('SELECT 1 FROM products WHERE id=?',(product_id,)).fetchone():
        raise ValueError('Selecione um produto cadastrado.')
    if db.execute('SELECT 1 FROM lots WHERE product_id=? AND code=?',(product_id,code)).fetchone():
        raise ValueError('Este código de lote já existe para o produto selecionado.')
    with db:
        return db.execute('INSERT INTO lots(product_id,code,expiry) VALUES(?,?,?)',(product_id,code,expiry)).lastrowid

def balance(lot_id):
    return get_db().execute("SELECT COALESCE(SUM(CASE WHEN kind='entrada' THEN quantity ELSE -quantity END),0) FROM movements WHERE lot_id=?",(lot_id,)).fetchone()[0]

def move(lot_id, user_id, kind, quantity, reason, today=None):
    db = get_db()
    today = today or date.today()
    db.execute('BEGIN IMMEDIATE')
    try:
        lot = db.execute('SELECT l.*,p.unit FROM lots l JOIN products p ON p.id=l.product_id WHERE l.id=?',(lot_id,)).fetchone()
        if lot is None:
            raise ValueError('Selecione um lote existente.')
        qty = amount(quantity,lot['unit'])
        allowed = {'entrada':('compra','saldo_inicial'),'saida':('venda','perda_vencimento','outra_perda')}
        if kind not in allowed or reason not in allowed[kind]:
            raise ValueError('O motivo deve corresponder ao tipo de movimentação.')
        if kind=='saida' and reason=='venda' and lot['expiry']<today.isoformat():
            raise ValueError('Não é permitido vender produto vencido.')
        if kind=='saida' and qty>balance(lot_id):
            raise ValueError('Quantidade superior ao saldo disponível.')
        db.execute('INSERT INTO movements(lot_id,user_id,kind,quantity,reason) VALUES(?,?,?,?,?)',(lot_id,user_id,kind,qty,reason))
        db.commit()
    except Exception:
        db.rollback()
        raise

def expiry_status(expiry, stock, today=None):
    if stock<=0:
        return ('neutral','ⓘ Sem saldo — sem alerta de validade')
    days = (date.fromisoformat(expiry)-(today or date.today())).days
    if days<0:
        return ('danger','! Produto vencido')
    if days==0:
        return ('warning','⚠ Vence hoje')
    if days<=30:
        return ('warning',f'⚠ Vence em {days} dias')
    return ('normal','✓ Dentro da validade')

def stock(search='', page=1):
    rows=get_db().execute('''SELECT l.*,p.name,p.unit,
    COALESCE(SUM(CASE WHEN m.kind='entrada' THEN m.quantity ELSE -m.quantity END),0) AS balance
    FROM lots l JOIN products p ON p.id=l.product_id LEFT JOIN movements m ON m.lot_id=l.id
    WHERE p.name LIKE ? GROUP BY l.id ORDER BY l.expiry,l.id LIMIT 21 OFFSET ?''',('%'+search+'%',(page-1)*20)).fetchall()
    return rows[:20],len(rows)>20
