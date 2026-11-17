"""Iniciador Windows: ambiente isolado, conta local e navegador."""
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import venv
import webbrowser

ROOT=Path(__file__).resolve().parent

def run(args, env=None):
    subprocess.run(args,cwd=ROOT,env=env,check=True)

def main():
    os.chdir(ROOT)
    print('\nESTOQUE FÁCIL — INICIALIZAÇÃO LOCAL\n')
    if sys.version_info<(3,12):
        raise RuntimeError('É necessário Python 3.12 ou superior.')
    env_python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not env_python.exists():
        print('Preparando ambiente Python. Aguarde...')
        venv.EnvBuilder(with_pip=True).create(ROOT/'.venv')
    marker=ROOT/'.venv'/'estoque_requirements.txt'
    requirements=(ROOT/'requirements.txt').read_bytes()
    if not marker.exists() or marker.read_bytes()!=requirements:
        print('Instalando dependências. Esta etapa precisa de internet...')
        run([str(env_python),'-m','pip','install','-r','requirements.txt'])
        marker.write_bytes(requirements)
    instance=ROOT/'instance'
    instance.mkdir(exist_ok=True)
    secret_file=instance/'secret.key'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32))
    env=os.environ.copy()
    env['SECRET_KEY']=secret_file.read_text().strip()
    env['DATABASE_PATH']=str(instance/'estoque.db')
    env['APP_ENV']='local'
    exists=False
    db_path=instance/'estoque.db'
    if db_path.exists():
        with sqlite3.connect(db_path) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
                exists=db.execute('SELECT 1 FROM users WHERE active=1 LIMIT 1').fetchone() is not None
    if not exists:
        print('\nPRIMEIRO ACESSO\nUsuário: operador\nCrie uma senha de pelo menos 15 caracteres.\nEla não aparece durante a digitação.\n')
        run([str(env_python),'-m','flask','--app','run_local','create-user','operador'],env)
    print('\nAbrindo http://127.0.0.1:5000\nEntre com operador e a senha que você criou.\nMantenha esta janela aberta enquanto usar o sistema.\nPara encerrar, pressione Ctrl+C.\n')
    timer=threading.Timer(2,lambda:webbrowser.open('http://127.0.0.1:5000'))
    timer.daemon=True
    timer.start()
    try:
        run([str(env_python),'run_local.py'],env)
    except KeyboardInterrupt:
        print('\nSistema encerrado.')

if __name__=='__main__':
    try:
        main()
    except (RuntimeError,subprocess.CalledProcessError,OSError) as exc:
        print(f'\nNão foi possível iniciar: {exc}\nVerifique Python, internet e permissões da pasta.')
        sys.exit(1)
