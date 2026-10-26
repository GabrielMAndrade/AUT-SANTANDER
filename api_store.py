"""Fila SQLite local: um processo WebDriver, consultas persistentes e rastreáveis.

Não registrar nomes/CPFs em logs de aplicação. Proteja o diretório private/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self.path.parent, 0o700)
        self._init()

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    def _init(self):
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS consultas (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    request_hash TEXT NOT NULL,
                    convenio TEXT NOT NULL,
                    celular TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    erro TEXT,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consulta_id TEXT NOT NULL REFERENCES consultas(id),
                    pos INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    cpf TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    margem TEXT,
                    detalhe TEXT,
                    atualizado_em TEXT NOT NULL,
                    UNIQUE(consulta_id, pos)
                );
                CREATE INDEX IF NOT EXISTS idx_consultas_status ON consultas(status, criado_em);
                CREATE INDEX IF NOT EXISTS idx_itens_consulta ON itens(consulta_id, pos);
            """)
            # O processo caiu durante uma consulta: exigir retomada explícita.
            db.execute("UPDATE consultas SET status='interrompido', erro='Reinício durante execução' WHERE status='processando'")
            db.execute("UPDATE itens SET status='interrompido', detalhe='Execução interrompida; verificar antes de reenviar' WHERE status='processando'")
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def criar(self, convenio: str, celular: str, clientes: list[dict[str, str]],
              idempotency_key: str | None = None) -> tuple[str, bool]:
        body = {'convenio': convenio, 'celular': celular, 'clientes': clientes}
        digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        job_id, now = uuid.uuid4().hex, agora()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if idempotency_key:
                existente = db.execute(
                    'SELECT id, request_hash FROM consultas WHERE idempotency_key=?',
                    (idempotency_key,)
                ).fetchone()
                if existente:
                    if existente['request_hash'] != digest:
                        db.rollback()
                        raise ValueError('Idempotency-Key já utilizada para outra solicitação')
                    db.commit()
                    return existente['id'], False
            db.execute(
                'INSERT INTO consultas (id,idempotency_key,request_hash,convenio,celular,status,criado_em,atualizado_em) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (job_id, idempotency_key, digest, convenio, celular, 'pendente', now, now)
            )
            db.executemany(
                'INSERT INTO itens (consulta_id,pos,nome,cpf,status,atualizado_em) VALUES (?,?,?,?,?,?)',
                [(job_id, pos, c['nome'], c['cpf'], 'pendente', now) for pos, c in enumerate(clientes)]
            )
            db.commit()
        return job_id, True

    def proxima(self) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM consultas WHERE status IN ('pendente','aguardando_sessao') "
                'ORDER BY criado_em, rowid LIMIT 1'
            ).fetchone()
            return dict(row) if row else None

    def pendentes(self, job_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM itens WHERE consulta_id=? AND status='pendente' ORDER BY pos", (job_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def atualizar_job(self, job_id: str, status: str, erro: str | None = None):
        with self._db() as db:
            db.execute(
                'UPDATE consultas SET status=?, erro=?, atualizado_em=? WHERE id=?',
                (status, erro, agora(), job_id)
            )

    def atualizar_item(self, item_id: int, status: str, margem: str | None = None,
                       detalhe: str | None = None):
        with self._db() as db:
            db.execute(
                'UPDATE itens SET status=?, margem=?, detalhe=?, atualizado_em=? WHERE id=?',
                (status, margem, detalhe, agora(), item_id)
            )

    def finalizar(self, job_id: str):
        with self._db() as db:
            total = db.execute(
                "SELECT COUNT(*) AS n FROM itens WHERE consulta_id=? AND status<>'ok'", (job_id,)
            ).fetchone()['n']
        self.atualizar_job(job_id, 'concluido_com_pendencias' if total else 'concluido')

    def obter(self, job_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            job = db.execute('SELECT * FROM consultas WHERE id=?', (job_id,)).fetchone()
            if job is None:
                return None
            rows = db.execute(
                'SELECT pos,nome,cpf,status,margem,detalhe,atualizado_em FROM itens '
                'WHERE consulta_id=? ORDER BY pos', (job_id,)
            ).fetchall()
        itens = [dict(r) for r in rows]
        counts: dict[str,int] = {}
        for item in itens:
            counts[item['status']] = counts.get(item['status'], 0) + 1
        return {
            'id': job['id'], 'status': job['status'], 'convenio': job['convenio'],
            'criado_em': job['criado_em'], 'atualizado_em': job['atualizado_em'],
            'erro': job['erro'], 'total': len(itens), 'contagem': counts, 'resultados': itens,
        }

    def resumo_fila(self) -> dict[str, int]:
        with self._db() as db:
            rows = db.execute('SELECT status, COUNT(*) AS n FROM consultas GROUP BY status').fetchall()
            return {r['status']: r['n'] for r in rows}

    def interromper_em_andamento(self, job_id: str):
        """Marca item em trânsito como interrompido após uma exceção inesperada."""
        with self._db() as db:
            db.execute(
                "UPDATE itens SET status='interrompido', detalhe='Falha técnica inesperada', "
                "atualizado_em=? WHERE consulta_id=? AND status='processando'",
                (agora(), job_id)
            )

    def retomar(self, job_id: str) -> bool | None:
        """None: não encontrado; False: status não permite retomada."""
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM consultas WHERE id=?', (job_id,)).fetchone()
            if row is None:
                db.rollback()
                return None
            if row['status'] != 'interrompido':
                db.rollback()
                return False
            db.execute(
                "UPDATE itens SET status='pendente', detalhe=NULL, atualizado_em=? "
                "WHERE consulta_id=? AND status IN ('interrompido','processando')", (agora(), job_id)
            )
            db.execute(
                "UPDATE consultas SET status='pendente', erro=NULL, atualizado_em=? WHERE id=?",
                (agora(), job_id)
            )
            db.commit()
            return True
