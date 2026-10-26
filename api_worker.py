"""Executor sequencial para Selenium: um navegador e um CPF por vez."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from api_store import Repository

logger = logging.getLogger(__name__)


@dataclass
class WorkerState:
    estado: str = 'iniciando'
    ultima_falha: str | None = None


class SeleniumRunner:
    """Importação tardia: API pode responder /health sem Selenium instalado.

    A execução exige Chrome da própria VPS aberto na porta local 9222,
    autenticação e 2FA realizados manualmente conforme autorização do banco.
    """
    def __init__(self):
        self.driver = None
        self.core = None

    def conectar(self):
        import main as core
        from conexao_chrome import conectar_chrome, selecionar_aba_portal
        self.core = core
        self.driver = conectar_chrome()
        selecionar_aba_portal(self.driver)
        if not core.sessao_autenticada(self.driver):
            raise RuntimeError('Sessão não autenticada: faça login e 2FA manualmente no Chrome da VPS')

    def consultar(self, cliente: dict[str, str], convenio: str, celular: str):
        from dados import Cliente
        return self.core.consultar_com_retorno(
            self.driver, Cliente(nome=cliente['nome'], cpf=cliente['cpf']),
            convenio, celular, self.core.TEMPO_ESPERA,
        )

    def fechar(self):
        if self.driver is not None:
            try:
                self.driver.quit()  # Desconecta WebDriver; não encerra o perfil do Chrome manual.
            except Exception:
                pass
            self.driver = None


class QueueWorker:
    def __init__(self, repo: Repository, runner_factory=SeleniumRunner, wait_seconds=10):
        self.repo = repo
        self.runner_factory = runner_factory
        self.wait_seconds = wait_seconds
        self.state = WorkerState()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def iniciar(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, name='santander-selenium', daemon=True)
            self.thread.start()

    def parar(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)

    def _loop(self):
        self.state.estado = 'ocioso'
        while not self.stop_event.is_set():
            job = self.repo.proxima()
            if not job:
                self.state.estado = 'ocioso'
                self.stop_event.wait(1)
                continue
            runner = self.runner_factory()
            try:
                # Não marca como processando até validar a sessão.
                runner.conectar()
            except Exception as exc:
                self.state.estado = 'aguardando_sessao'
                self.state.ultima_falha = f'{type(exc).__name__}: {str(exc)[:160]}'
                self.repo.atualizar_job(job['id'], 'aguardando_sessao',
                                        'Chrome indisponível ou sessão sem autenticação manual')
                logger.warning('Robô aguardando sessão válida (%s)', type(exc).__name__)
                runner.fechar()
                self.stop_event.wait(self.wait_seconds)
                continue
            try:
                self.state.estado = 'processando'
                self.state.ultima_falha = None
                self._processar(job, runner)
            except Exception as exc:
                # Falha geral: parar este lote e exigir retomar, sem misturar CPFs.
                logger.exception('Falha técnica no processamento (%s)', type(exc).__name__)
                self.state.ultima_falha = type(exc).__name__
                self.repo.interromper_em_andamento(job['id'])
                self.repo.atualizar_job(job['id'], 'interrompido',
                                        f'Falha técnica ({type(exc).__name__}); verifique a sessão')
            finally:
                runner.fechar()

    def _processar(self, job: dict[str, Any], runner):
        # Importação isolada para facilitar testes de armazenamento/API.
        from main import FalhaNavegacao, PularCliente
        self.repo.atualizar_job(job['id'], 'processando')
        for item in self.repo.pendentes(job['id']):
            if self.stop_event.is_set():
                self.repo.atualizar_job(job['id'], 'interrompido', 'Serviço desligado durante a consulta')
                return
            self.repo.atualizar_item(item['id'], 'processando')
            try:
                margem, status = runner.consultar(item, job['convenio'], job['celular'])
                if status == 'OK':
                    self.repo.atualizar_item(item['id'], 'ok', margem=margem)
                else:
                    self.repo.atualizar_item(
                        item['id'], 'erro_portal', margem='0',
                        detalhe='O robô não confirmou margem positiva ou encontrou aviso do portal'
                    )
            except PularCliente as exc:
                # O navegador retornou ao menu Produtos via finally no main.py.
                self.repo.atualizar_item(item['id'], 'pulado_timeout', detalhe=str(exc)[:300])
            except FalhaNavegacao as exc:
                self.repo.atualizar_item(item['id'], 'interrompido', detalhe=str(exc)[:300])
                self.repo.atualizar_job(job['id'], 'interrompido',
                                        'Falha de navegação; confirmar retorno ao formulário Produtos')
                return
            except Exception as exc:
                self.repo.atualizar_item(item['id'], 'interrompido',
                                        detalhe=f'Falha técnica: {type(exc).__name__}')
                self.repo.atualizar_job(job['id'], 'interrompido',
                                        f'Falha técnica: {type(exc).__name__}')
                logger.error('Falha técnica numa consulta: %s', type(exc).__name__)
                return
        self.repo.finalizar(job['id'])
