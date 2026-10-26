"""Leitura da lista de clientes e gravação transacional do CSV de resultado."""

from __future__ import annotations

import csv
import os
import re
import tempfile
from datetime import datetime
from uuid import uuid4
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Cliente:
    nome: str
    cpf: str


def limpar_cpf(valor: str) -> str:
    return re.sub(r"\D", "", str(valor))


def _e_cpf(valor: str) -> bool:
    return len(limpar_cpf(valor)) == 11 and not any(ch.isalpha() for ch in valor)


def ler_clientes(caminho: Path) -> list[Cliente]:
    """Aceita CPF,NOME ou NOME,CPF, linha a linha ou pares em uma linha.

    Os nomes contendo vírgulas devem ser colocados entre aspas duplas.
    Comentários iniciados por # e linhas vazias são ignorados.
    """
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {caminho}")

    try:
        conteudo = caminho.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        conteudo = caminho.read_text(encoding="cp1252")

    clientes: list[Cliente] = []
    encontrados: set[str] = set()
    for numero_linha, linha in enumerate(conteudo.splitlines(), start=1):
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        try:
            campos = next(csv.reader([linha], delimiter=",", skipinitialspace=True, strict=True))
        except csv.Error as exc:
            raise ValueError(f"Linha {numero_linha}: vírgulas/aspas inválidas: {exc}") from exc
        campos = [campo.strip() for campo in campos]
        if len(campos) == 2 and {c.upper() for c in campos} == {"CPF", "NOME"}:
            continue
        if len(campos) % 2 != 0:
            raise ValueError(
                f"Linha {numero_linha}: esperado um par CPF,NOME separado por vírgula; "
                f"encontrados {len(campos)} campos."
            )
        for posicao in range(0, len(campos), 2):
            primeira, segunda = campos[posicao : posicao + 2]
            if _e_cpf(primeira) and segunda:
                cpf, nome = limpar_cpf(primeira), segunda
            elif _e_cpf(segunda) and primeira:
                cpf, nome = limpar_cpf(segunda), primeira
            else:
                raise ValueError(
                    f"Linha {numero_linha}, par {posicao // 2 + 1}: "
                    "é necessário um CPF com 11 dígitos e um nome não vazio."
                )
            if cpf not in encontrados:
                clientes.append(Cliente(nome=nome, cpf=cpf))
                encontrados.add(cpf)
    return clientes


def selecionar_clientes(
    clientes: list[Cliente], *, inicio: int = 1,
    cpf_inicial: str | None = None, limite: int = 0,
) -> tuple[list[Cliente], int]:
    """Seleciona um trecho da lista ATUAL, sem consultar CSV de outras execuções.

    A posição de início começa em 1. O CPF inicial, quando fornecido,
    corresponde ao próprio cliente e aos seguintes, na ordem do TXT.
    """
    if not clientes:
        raise ValueError("A lista de clientes está vazia.")
    if inicio < 1 or limite < 0:
        raise ValueError("--inicio precisa ser >= 1 e --limite >= 0.")

    if cpf_inicial is not None:
        cpf = limpar_cpf(cpf_inicial)
        if len(cpf) != 11:
            raise ValueError("--cpf-inicial precisa conter 11 dígitos.")
        indice = next((i for i, cliente in enumerate(clientes) if cliente.cpf == cpf), None)
        if indice is None:
            raise ValueError("--cpf-inicial não encontrado no cpf_nome.txt.")
    else:
        indice = inicio - 1
        if indice >= len(clientes):
            raise ValueError(
                f"--inicio={inicio} ultrapassa os {len(clientes)} clientes do TXT."
            )

    selecionados = clientes[indice:]
    if limite:
        selecionados = selecionados[:limite]
    return selecionados, indice + 1


def novo_caminho_csv(pasta_saida: Path) -> Path:
    """Gera um nome novo por execução; arquivos antigos não são reutilizados.

    A gravação inicial é realizada por ResultadoCSV. Um UUID reduz o risco
    de colisão inclusive em execuções iniciadas no mesmo segundo.
    """
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        # Nomes e margens são dados pessoais: restringir diretório na VPS.
        os.chmod(pasta_saida, 0o700)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return pasta_saida / f"resultado_margens_{timestamp}_{uuid4().hex[:8]}.csv"


class ResultadoCSV:
    """Grava de forma atômica após cada cliente. Um caminho novo inicia vazio."""

    CABECALHO = ("nome", "cpf", "margem", "status")

    def __init__(self, caminho: Path, clientes: list[Cliente]):
        self.caminho = caminho
        self.ordem = [c.cpf for c in clientes]
        self.registros: dict[str, dict[str, str]] = {}
        if caminho.exists():
            with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
                leitor = csv.DictReader(arquivo, delimiter=";")
                if tuple(leitor.fieldnames or ()) != self.CABECALHO:
                    raise ValueError(
                        f"O CSV existente '{caminho}' possui um cabeçalho incompatível. "
                        "Renomeie-o ou use um arquivo novo."
                    )
                for item in leitor:
                    cpf = limpar_cpf(item.get("cpf", ""))
                    if cpf:
                        self.registros[cpf] = {
                            coluna: str(item.get(coluna, "")) for coluna in self.CABECALHO
                        }
        self._salvar()  # Cabeçalho disponível imediatamente, antes das consultas.

    def ja_processado(self, cpf: str, reprocessar_erros: bool) -> bool:
        registro = self.registros.get(cpf)
        return bool(registro) and not (
            reprocessar_erros and registro.get("status") == "ERRO"
        )

    def registrar(self, cliente: Cliente, margem: str, status: str) -> None:
        if status not in {"OK", "ERRO"}:
            raise ValueError("Status inválido. Use OK ou ERRO.")
        # CSV é um formato que pode ser aberto no Excel: não permitir fórmula em nomes.
        nome_csv = "'" + cliente.nome if cliente.nome.startswith(("=", "+", "-", "@")) else cliente.nome
        self.registros[cliente.cpf] = {
            "nome": nome_csv,
            "cpf": cliente.cpf,
            "margem": margem if status == "OK" else "0",
            "status": status,
        }
        self._salvar()

    def _salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        # mesmo diretório permite os.replace atômico (não deixa o CSV vazio no meio)
        fd, temporario = tempfile.mkstemp(
            dir=self.caminho.parent, prefix=".resultado_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as arquivo:
                escritor = csv.DictWriter(
                    arquivo, fieldnames=self.CABECALHO, delimiter=";", lineterminator="\n"
                )
                escritor.writeheader()
                for cpf in self.ordem:
                    if cpf in self.registros:
                        escritor.writerow(self.registros[cpf])
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, self.caminho)
        finally:
            if os.path.exists(temporario):
                os.unlink(temporario)
