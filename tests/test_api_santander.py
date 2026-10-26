"""Testes locais de API; não acessam o banco Santander."""
import os
import sys
from types import ModuleType

os.environ.setdefault('SANTANDER_API_TOKEN', 'teste-' + 'x'*48)

from fastapi.testclient import TestClient
from api_santander import create_app
from api_store import Repository
from api_worker import QueueWorker

TOKEN = 'teste-' + 'x'*48
AUTH = {'Authorization': f'Bearer {TOKEN}'}


def client(tmp_path):
    return TestClient(create_app(db_path=tmp_path / 'consultas.sqlite3', api_token=TOKEN,
                                 start_worker=False))


def test_api_exige_token(tmp_path):
    c = client(tmp_path)
    payload = {'nome': 'CLIENTE TESTE', 'cpf': '000.000.000-00',
               'convenio': '123', 'celular': '51999999999'}
    assert c.get('/health').status_code == 200
    assert c.post('/margem_cpf', json=payload).status_code == 401
    assert c.post('/margem_cpf', json=payload, headers={'Authorization': 'Bearer errado'}).status_code == 401
    assert c.get('/status', headers=AUTH).status_code == 200


def test_requisicao_singular_e_resultado(tmp_path):
    c = client(tmp_path)
    response = c.post('/margem_cpf', headers=AUTH, json={
        'nome': 'CLIENTE EXEMPLO', 'cpf': '000.000.000-00', 'convenio': '55',
        'celular': '51999999999',
    })
    assert response.status_code == 202, response.text
    job_id = response.json()['id']
    result = c.get(f'/consultas/{job_id}', headers=AUTH).json()
    assert result['status'] == 'pendente'
    assert result['resultados'][0]['cpf'] == '00000000000'
    assert result['resultados'][0]['status'] == 'pendente'
    assert c.get('/consultas/inexistente', headers=AUTH).status_code == 404


def test_lote_validacao_e_resultados(tmp_path):
    c = client(tmp_path)
    data = {'convenio': '007', 'celular': '51999999999', 'clientes': [
        {'nome': 'CLIENTE UM', 'cpf': '11111111111'},
        {'nome': 'CLIENTE DOIS', 'cpf': '22222222222'},
    ]}
    r = c.post('/consultas', headers=AUTH, json=data)
    assert r.status_code == 202
    job_id = r.json()['id']
    repo = c.app.state.repo
    items = repo.pendentes(job_id)
    repo.atualizar_item(items[0]['id'], 'ok', '300,00')
    repo.atualizar_item(items[1]['id'], 'pulado_timeout', detalhe='Botão não encontrado')
    repo.finalizar(job_id)
    resultado = c.get(f'/consultas/{job_id}', headers=AUTH).json()
    assert resultado['status'] == 'concluido_com_pendencias'
    assert resultado['contagem']['ok'] == 1
    assert resultado['contagem']['pulado_timeout'] == 1
    assert resultado['resultados'][0]['margem'] == '300,00'
    # Não tentar o mesmo CPF duas vezes dentro de um mesmo lote.
    data['clientes'][1]['cpf'] = data['clientes'][0]['cpf']
    assert c.post('/consultas', headers=AUTH, json=data).status_code == 422


def test_idempotencia_protege_reenvio(tmp_path):
    c = client(tmp_path)
    payload = {'nome': 'CLIENTE EXEMPLO', 'cpf': '00000000000',
               'convenio': '55', 'celular': '51999999999'}
    headers = {**AUTH, 'Idempotency-Key': 'minha-operacao-123'}
    r1 = c.post('/margem_cpf', headers=headers, json=payload)
    r2 = c.post('/margem_cpf', headers=headers, json=payload)
    assert r1.status_code == r2.status_code == 202
    assert r1.json()['id'] == r2.json()['id']
    assert not r2.json()['criado']
    payload['convenio'] = '999'
    assert c.post('/margem_cpf', headers=headers, json=payload).status_code == 409


def test_retomada_explicita(tmp_path):
    c = client(tmp_path)
    r = c.post('/margem_cpf', headers=AUTH, json={
        'nome': 'CLIENTE EXEMPLO', 'cpf': '00000000000', 'convenio': '55', 'celular': '51999999999',
    })
    job_id = r.json()['id']
    repo = c.app.state.repo
    assert c.post(f'/consultas/{job_id}/retomar', headers=AUTH).status_code == 409
    item = repo.pendentes(job_id)[0]
    repo.atualizar_item(item['id'], 'interrompido')
    repo.atualizar_job(job_id, 'interrompido')
    retomada = c.post(f'/consultas/{job_id}/retomar', headers=AUTH)
    assert retomada.status_code == 200
    assert len(repo.pendentes(job_id)) == 1
    assert repo.obter(job_id)['status'] == 'pendente'


def test_recuperacao_apos_reinicio_exige_confirmacao(tmp_path):
    path = tmp_path / 'consultas.sqlite3'
    repo = Repository(path)
    job_id, _ = repo.criar('123', '51999999999', [{'nome':'CLIENTE','cpf':'00000000000'}])
    repo.atualizar_job(job_id, 'processando')
    repo.atualizar_item(repo.pendentes(job_id)[0]['id'], 'processando')
    novo = Repository(path)
    assert novo.obter(job_id)['status'] == 'interrompido'
    assert novo.obter(job_id)['resultados'][0]['status'] == 'interrompido'


def test_worker_sucesso_e_timeout_sem_selenium_real(tmp_path, monkeypatch):
    fake_main = ModuleType('main')
    class FalhaNavegacao(RuntimeError): pass
    class PularCliente(FalhaNavegacao): pass
    fake_main.FalhaNavegacao = FalhaNavegacao
    fake_main.PularCliente = PularCliente
    monkeypatch.setitem(sys.modules, 'main', fake_main)
    repo = Repository(tmp_path/'worker.sqlite3')
    job_id, _ = repo.criar('123', '51999999999', [
        {'nome': 'PRIMEIRO', 'cpf': '00000000000'},
        {'nome': 'SEGUNDO', 'cpf': '11111111111'},
    ])
    class FakeRunner:
        def consultar(self, cliente, convenio, celular):
            if cliente['nome'] == 'PRIMEIRO':
                return '135,60', 'OK'
            raise PularCliente('Simular não encontrado')
    QueueWorker(repo)._processar(repo.proxima(), FakeRunner())
    status = repo.obter(job_id)
    assert status['status'] == 'concluido_com_pendencias'
    assert [it['status'] for it in status['resultados']] == ['ok', 'pulado_timeout']


def test_api_worker_processa_na_fila(tmp_path, monkeypatch):
    import time
    fake_main = ModuleType('main')
    class FalhaNavegacao(RuntimeError): pass
    class PularCliente(FalhaNavegacao): pass
    fake_main.FalhaNavegacao = FalhaNavegacao
    fake_main.PularCliente = PularCliente
    monkeypatch.setitem(sys.modules, 'main', fake_main)

    class FakeRunner:
        def conectar(self): pass
        def fechar(self): pass
        def consultar(self, cliente, convenio, celular):
            return '124,90', 'OK'
    api = create_app(db_path=tmp_path/'worker-api.sqlite3', api_token=TOKEN,
                     start_worker=True, runner_factory=FakeRunner)
    with TestClient(api) as c:
        r = c.post('/margem_cpf', headers=AUTH, json={
            'nome':'CLIENTE DE TESTE', 'cpf':'00000000000',
            'convenio':'55', 'celular':'51999999999',
        })
        assert r.status_code == 202
        job_id = r.json()['id']
        result = None
        for _ in range(40):
            result = c.get(f'/consultas/{job_id}', headers=AUTH).json()
            if result['status'] == 'concluido':
                break
            time.sleep(.05)
        assert result['status'] == 'concluido'
        assert result['resultados'][0]['margem'] == '124,90'


def test_phone_missing_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv('SANTANDER_CELULAR', raising=False)
    c = client(tmp_path)
    r = c.post('/margem_cpf', headers=AUTH, json={
        'nome': 'CLIENTE EXEMPLO', 'cpf': '00000000000', 'convenio': '55',
    })
    assert r.status_code == 422
