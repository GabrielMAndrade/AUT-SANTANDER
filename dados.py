"""Leitura da lista de clientes e gravação transacional do CSV de resultado."""

from __future__ import annotations

import csv
import os
import re
import tempfile
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


class ResultadoCSV:
    """Regrava o CSV de forma atômica após CADA cliente; retoma sem duplicar."""

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
