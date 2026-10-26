"""API HTTP do consultor Santander para integração n8n / VPS.

API própria da automação, NÃO é uma API oficial do banco Santander.
Apenas organiza chamadas ao Selenium dentro de uma sessão bancária autorizada.
"""
from __future__ import annotations

import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from api_store import Repository
from api_worker import QueueWorker

PASTA = Path(__file__).resolve().parent
load_dotenv(PASTA / '.env')


def _cpf(valor: str) -> str:
    cpf = re.sub(r'\D', '', str(valor))
    if len(cpf) != 11:
        raise ValueError('cpf precisa conter 11 dígitos')
    return cpf


def _celular(valor: str) -> str:
    numero = re.sub(r'\D', '', str(valor))
    if len(numero) not in {10, 11}:
        raise ValueError('celular precisa conter DDD e 10 ou 11 dígitos')
    return numero


class ClientePayload(BaseModel):
    cpf: str
    nome: str = Field(min_length=2, max_length=150)

    @field_validator('cpf')
    @classmethod
    def validar_cpf(cls, v: str):
        return _cpf(v)

    @field_validator('nome')
    @classmethod
    def validar_nome(cls, v: str):
        v = v.strip()
        if len(v) < 2:
            raise ValueError('nome obrigatório')
        return v


class ConsultaUnica(ClientePayload):
    convenio: str = Field(min_length=1, max_length=50)
    celular: str | None = None

    @field_validator('convenio')
    @classmethod
    def validar_convenio(cls, v: str):
        v = v.strip()
        if not v:
            raise ValueError('convênio obrigatório')
        return v

    @field_validator('celular')
    @classmethod
    def validar_celular(cls, v: str | None):
        return _celular(v) if v is not None else None


class ConsultaLote(BaseModel):
    convenio: str = Field(min_length=1, max_length=50)
    celular: str | None = None
    clientes: list[ClientePayload] = Field(min_length=1, max_length=100)

    @field_validator('convenio')
    @classmethod
    def validar_convenio(cls, v: str):
        v = v.strip()
        if not v:
            raise ValueError('convênio obrigatório')
        return v

    @field_validator('celular')
    @classmethod
    def validar_celular(cls, v: str | None):
        return _celular(v) if v is not None else None


autorizacao = HTTPBearer(auto_error=False)


def create_app(*, db_path: str | Path | None = None, api_token: str | None = None,
               start_worker: bool = True, runner_factory=None) -> FastAPI:
    token = api_token if api_token is not None else os.getenv('SANTANDER_API_TOKEN', '')
    if len(token) < 32:
        raise RuntimeError('Defina SANTANDER_API_TOKEN com no mínimo 32 caracteres no .env')

    caminho = db_path if db_path is not None else os.getenv(
        'SANTANDER_DB_PATH', str(PASTA / 'private' / 'consultas.sqlite3')
    )
    repo = Repository(caminho)
    worker = QueueWorker(repo, **({'runner_factory': runner_factory} if runner_factory else {}))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_worker:
            worker.iniciar()
        yield
        if start_worker:
            worker.parar()

    app = FastAPI(
        title='Soma | API de Consulta Santander', version='1.0.0',
        description='API própria da automação. Não é endpoint oficial do Santander.',
        lifespan=lifespan,
        docs_url='/docs', redoc_url=None,
    )
    app.state.repo = repo
    app.state.worker = worker

    def exigir_token(credenciais: HTTPAuthorizationCredentials | None = Depends(autorizacao)):
        if (not credenciais or credenciais.scheme.lower() != 'bearer' or
                not secrets.compare_digest(credenciais.credentials, token)):
            raise HTTPException(status_code=401, detail='Token inválido ou ausente',
                                headers={'WWW-Authenticate': 'Bearer'})

    def telefone_final(numero: str | None) -> str:
        valor = numero or os.getenv('SANTANDER_CELULAR', '')
        try:
            return _celular(valor)
        except ValueError as exc:
            raise HTTPException(422, detail='Envie celular válido no JSON ou configure SANTANDER_CELULAR') from exc

    def enfileirar(convenio: str, telefone: str, clientes: list[dict], idem: str | None):
        if idem is not None:
            if not (1 <= len(idem) <= 128) or not all(32 <= ord(ch) < 127 for ch in idem):
                raise HTTPException(422, detail='Idempotency-Key deve ter entre 1 e 128 caracteres ASCII')
        cpfs = [x['cpf'] for x in clientes]
        if len(cpfs) != len(set(cpfs)):
            raise HTTPException(422, detail='O lote contém CPFs duplicados')
        try:
            job_id, criado = repo.criar(convenio, telefone, clientes, idem)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        return {'id': job_id, 'status': repo.obter(job_id)['status'],
                'criado': criado, 'url_resultado': f'/consultas/{job_id}',
                'total': len(clientes)}

    @app.get('/health', tags=['Status'])
    def health():
        return {'status': 'ok', 'servico': 'api-consultas-santander'}

    @app.get('/status', dependencies=[Depends(exigir_token)], tags=['Status'])
    def status_geral():
        return {
            'worker': worker.state.estado,
            'ultimo_erro_tecnico': worker.state.ultima_falha,
            'fila': repo.resumo_fila(),
            'aviso': 'API ativa não garante sessão autenticada no portal bancário',
        }

    @app.post('/margem_cpf', status_code=status.HTTP_202_ACCEPTED,
              dependencies=[Depends(exigir_token)], tags=['Consultas'])
    def margem_cpf(pedido: ConsultaUnica, idempotency_key: str | None = Header(default=None)):
        cliente = {'cpf': pedido.cpf, 'nome': pedido.nome}
        return enfileirar(pedido.convenio, telefone_final(pedido.celular), [cliente], idempotency_key)

    @app.post('/consultas', status_code=status.HTTP_202_ACCEPTED,
              dependencies=[Depends(exigir_token)], tags=['Consultas'])
    def consultar_lote(pedido: ConsultaLote, idempotency_key: str | None = Header(default=None)):
        return enfileirar(pedido.convenio, telefone_final(pedido.celular),
                         [c.model_dump() for c in pedido.clientes], idempotency_key)

    @app.get('/consultas/{consulta_id}', dependencies=[Depends(exigir_token)], tags=['Consultas'])
    def obter_resultado(consulta_id: str):
        resultado = repo.obter(consulta_id)
        if resultado is None:
            raise HTTPException(404, detail='Consulta não encontrada')
        return resultado

    @app.post('/consultas/{consulta_id}/retomar',
              dependencies=[Depends(exigir_token)], tags=['Consultas'])
    def retomar_consulta(consulta_id: str):
        retomado = repo.retomar(consulta_id)
        if retomado is None:
            raise HTTPException(404, detail='Consulta não encontrada')
        if not retomado:
            raise HTTPException(409, detail='Somente consulta interrompida pode ser retomada')
        return {'id': consulta_id, 'status': 'pendente',
                'aviso': 'A retomada pode repetir a última consulta que foi interrompida; confira antes.'}

    return app


# Inicialização em importação; é necessário configurar .env antes de subir o servidor.
app = create_app()
