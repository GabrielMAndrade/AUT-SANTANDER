"""Consulta assistida de margem no portal Parceiros Santander.

O código de autenticação de dois fatores é inserido pela pessoa no portal.
A automação só consulta CPFs depois que o operador pressiona ENTER no terminal.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from dados import Cliente, ResultadoCSV, ler_clientes


PASTA = Path(__file__).resolve().parent
URL_PORTAL = "https://www.parceirosantander.com.br/spa-base/"

XP = {
    "nome": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[2]/dss-form-field/div/input",
    "cpf": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[3]/dss-form-field/div/input",
    "celular": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[4]/dss-form-field/div/input",
    "ver_produtos": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[5]/button",
    "simular": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-select-product/div[2]/div/div/div/div/dss-product-card/div/dss-product-card-actions/button",
    "sem_srcc": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-select-product/app-dialog-srcc/dss-dialog/div/div/dss-dialog-footer/button[1]",
    "simular_proposta": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-home/section/section[2]/section[1]/div/button",
    "dropdown_convenio": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[1]/dss-form-field/div/dss-dropdown/div/button",
    "opcao_codigo": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[1]/dss-form-field/div/dss-dropdown/div/ul/li[2]/a/span/option",
    "input_convenio": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[2]/csg-input-autocomplete/form/dss-search-bar/div/div/input",
    "buscar": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[3]/button",
    "erro": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/section/div[1]/csg-warning/dss-alert-banner/div/div/span",
    "margem": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/online-form/section[1]/section[2]/dss-form-field[2]/div/input",
    "produtos_menu": "/html/body/fve-root/fve-logged-area/fve-menu/dss-menu/aside/div[2]/dss-menu-item[2]/div/div",
}


def configuracao_bool(chave: str, padrao: bool = False) -> bool:
    raw = os.getenv(chave, str(padrao)).strip().lower()
    if raw not in ("true", "false"):
        raise ValueError(f"{chave} no .env deve ser true ou false (valor atual: {raw!r}).")
    return raw == "true"


def aguardar_visivel(driver, xpath: str, timeout: float = 35):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath))
    )


def aguardar_clicavel(driver, xpath: str, timeout: float = 35):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )


def visivel(driver, xpath: str) -> bool:
    try:
        return any(item.is_displayed() for item in driver.find_elements(By.XPATH, xpath))
    except (StaleElementReferenceException, WebDriverException):
        return False


def clicar_elemento(driver, elemento) -> None:
    try:
        elemento.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        # Se um componente de UI interceptar o clique, tenta o clique nativo do DOM.
        driver.execute_script("arguments[0].click();", elemento)


def clicar(driver, xpath: str, timeout: float = 35) -> None:
    elemento = aguardar_clicavel(driver, xpath, timeout)
    clicar_elemento(driver, elemento)


def digitar(driver, xpath: str, texto: str, timeout: float = 35) -> None:
    campo = aguardar_visivel(driver, xpath, timeout)
    campo.click()
    campo.send_keys(Keys.CONTROL, "a")
    campo.send_keys(Keys.BACKSPACE)
    campo.send_keys(texto)
    # Componentes Angular costumam validar ao perder o foco.
    campo.send_keys(Keys.TAB)


def driver_chrome(headless: bool):
    configuracao = ChromeOptions()
    configuracao.add_argument("--window-size=1440,960")
    configuracao.add_argument("--disable-notifications")
    configuracao.add_argument("--no-first-run")
    # Sessão exclusiva deste projeto: evita misturar cookies com o Chrome pessoal.
    perfil = PASTA / "perfil_chrome"
    perfil.mkdir(exist_ok=True)
    configuracao.add_argument(f"--user-data-dir={perfil}")
    if headless:
        configuracao.add_argument("--headless=new")
    return webdriver.Chrome(options=configuracao)


def _inputs_visiveis(driver, css: str):
    try:
        return [x for x in driver.find_elements(By.CSS_SELECTOR, css) if x.is_displayed() and x.is_enabled()]
    except WebDriverException:
        return []


def _input_login(driver):
    # Campos comuns de usuário. Não adivinha um XPath bancário não fornecido.
    seletores = [
        "input[autocomplete='username']",
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[name*='login' i]",
        "input[id*='login' i]",
        "input[placeholder*='usuário' i]",
        "input[placeholder*='usuario' i]",
        "input[placeholder*='login' i]",
        "input[type='email']",
        "input[type='text']",
    ]
    for seletor in seletores:
        candidatos = _inputs_visiveis(driver, seletor)
        if candidatos:
            return candidatos[0]
    return None


def _input_senha(driver):
    candidatos = _inputs_visiveis(driver, "input[type='password']")
    return candidatos[0] if candidatos else None


def _preencher_elemento(campo, valor: str):
    campo.click()
    campo.send_keys(Keys.CONTROL, "a")
    campo.send_keys(Keys.BACKSPACE)
    campo.send_keys(valor)


def _clicar_continuar_login(driver, campo):
    # Prioriza o botão do mesmo formulário para não clicar ações de outras áreas.
    try:
        formulario = campo.find_element(By.XPATH, "ancestor::form[1]")
        botoes = formulario.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
    except NoSuchElementException:
        botoes = driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
    for botao in botoes:
        try:
            nome = (botao.text or botao.get_attribute("value") or "").lower().strip()
            if botao.is_displayed() and botao.is_enabled() and any(
                palavra in nome for palavra in ("entrar", "acessar", "login", "continuar", "avançar")
            ):
                clicar_elemento(driver, botao)
                return True
        except (StaleElementReferenceException, WebDriverException):
            continue
    # Submit sem texto somente quando ele está no MESMO form do campo.
    try:
        formulario = campo.find_element(By.XPATH, "ancestor::form[1]")
        botoes = formulario.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        for botao in botoes:
            if botao.is_displayed() and botao.is_enabled():
                clicar_elemento(driver, botao)
                return True
    except (NoSuchElementException, StaleElementReferenceException, WebDriverException):
        pass
    return False


def autenticar_automaticamente(driver, usuario: str, senha: str) -> bool:
    """Tentativa conservadora; se o site mudar, o operador termina manualmente.

    Não automatiza ou contorna OTP/captcha. Não registra a senha em logs.
    """
    print("Tentando preencher login e senha no portal...")
    try:
        limite = time.monotonic() + 22
        while time.monotonic() < limite:
            if visivel(driver, XP["produtos_menu"]) or visivel(driver, XP["nome"]):
                print("Sessão aparentemente autenticada; login manual não necessário.")
                return True
            senha_input = _input_senha(driver)
            login_input = _input_login(driver)
            if senha_input is not None and login_input is not None:
                _preencher_elemento(login_input, usuario)
                _preencher_elemento(senha_input, senha)
                if not _clicar_continuar_login(driver, senha_input):
                    print("Dados preenchidos; clique manualmente em Entrar, se necessário.")
                else:
                    print("Login enviado; conclua a autenticação em duas etapas no portal.")
                return True
            if login_input is not None and senha_input is None:
                # Alguns portais pedem o usuário antes de apresentar a senha.
                _preencher_elemento(login_input, usuario)
                if _clicar_continuar_login(driver, login_input):
                    try:
                        senha_input = WebDriverWait(driver, 8).until(lambda d: _input_senha(d))
                        _preencher_elemento(senha_input, senha)
                        if not _clicar_continuar_login(driver, senha_input):
                            print("Senha preenchida; finalize o login manualmente.")
                        else:
                            print("Login enviado; insira o código de autenticação no portal.")
                        return True
                    except TimeoutException:
                        break
            time.sleep(0.6)
    except WebDriverException as exc:
        logging.info("Preenchimento automático de login indisponível: %s", type(exc).__name__)
    print("Não foi possível identificar com segurança os campos de login.")
    print("Faça login e digite sua senha manualmente na janela do Chrome.")
    return False


def abrir_consulta(driver, tempo_espera: int) -> None:
    """Volta pelo menu Produtos e aguarda a SPA montar a próxima consulta."""
    if visivel(driver, XP["produtos_menu"]):
        clicar(driver, XP["produtos_menu"], timeout=tempo_espera)
    else:
        # Depois de uma tela interna, retorna à raiz. O menu pode levar
        # alguns segundos para ser criado pelo Angular: aguarde sua presença.
        driver.get(URL_PORTAL)
        WebDriverWait(driver, tempo_espera).until(
            lambda d: visivel(d, XP["produtos_menu"]) or visivel(d, XP["nome"])
        )
        if visivel(driver, XP["produtos_menu"]):
            clicar(driver, XP["produtos_menu"], timeout=tempo_espera)
    aguardar_visivel(driver, XP["nome"], timeout=tempo_espera)


def escolher_codigo_convenio(driver, convenio: str, tempo_espera: int) -> None:
    clicar(driver, XP["dropdown_convenio"], timeout=tempo_espera)
    try:
        clicar(driver, XP["opcao_codigo"], timeout=7)
    except (TimeoutException, WebDriverException):
        # Fallback quando a SPA usa <li><a><span> sem a tag <option>.
        seletores_alternativos = [
            XP["opcao_codigo"].rsplit("/option", 1)[0],
            XP["opcao_codigo"].split("/a/span/option")[0] + "/a",
            XP["opcao_codigo"].split("/a/span/option")[0],
        ]
        for seletor in seletores_alternativos:
            try:
                clicar(driver, seletor, timeout=3)
                break
            except (TimeoutException, WebDriverException):
                continue
        else:
            raise RuntimeError("Não foi possível selecionar 'Código do convênio' no dropdown.")
    digitar(driver, XP["input_convenio"], convenio, timeout=tempo_espera)
    clicar(driver, XP["buscar"], timeout=tempo_espera)


def margem_positiva(valor: str) -> bool:
    """Checa >0 sem alterar o texto original que será salvo no CSV."""
    numero = re.sub(r"[^0-9,.-]", "", valor or "")
    if not numero:
        return False
    if "," in numero:
        numero = numero.replace(".", "").replace(",", ".")
    try:
        return Decimal(numero) > 0
    except InvalidOperation:
        return False


def aguardar_margem_ou_erro(driver, tempo_espera: int) -> tuple[str, str]:
    """Detecta o banner de erro ou lê o VALOR do input de margem."""
    limite = time.monotonic() + tempo_espera
    while time.monotonic() < limite:
        if visivel(driver, XP["erro"]):
            return "0", "ERRO"
        try:
            campos = driver.find_elements(By.XPATH, XP["margem"])
            for campo in campos:
                if campo.is_displayed():
                    valor = (campo.get_property("value") or campo.get_attribute("value") or "").strip()
                    if margem_positiva(valor):
                        return valor, "OK"
        except (StaleElementReferenceException, WebDriverException):
            pass
        time.sleep(0.35)
    return "0", "ERRO"


def consultar(driver, cliente: Cliente, convenio: str, celular: str, tempo_espera: int) -> tuple[str, str]:
    abrir_consulta(driver, tempo_espera)
    digitar(driver, XP["nome"], cliente.nome, tempo_espera)
    digitar(driver, XP["cpf"], cliente.cpf, tempo_espera)
    digitar(driver, XP["celular"], celular, tempo_espera)
    clicar(driver, XP["ver_produtos"], tempo_espera)
    clicar(driver, XP["simular"], tempo_espera)

    # Este diálogo não aparece em todas as jornadas do portal.
    try:
        clicar(driver, XP["sem_srcc"], timeout=5)
    except TimeoutException:
        pass

    clicar(driver, XP["simular_proposta"], tempo_espera)
    escolher_codigo_convenio(driver, convenio, tempo_espera)
    return aguardar_margem_ou_erro(driver, tempo_espera)


def salvar_diagnostico(driver, cpf: str):
    diretorio = PASTA / "diagnosticos"
    diretorio.mkdir(parents=True, exist_ok=True)
    # Atenção: screenshots podem conter informações financeiras pessoais.
    arquivo = diretorio / f"falha_terminacao_{cpf[-4:]}_{int(time.time())}.png"
    try:
        driver.save_screenshot(str(arquivo))
        logging.info("Captura de diagnóstico criada: %s", arquivo.name)
    except WebDriverException:
        logging.warning("Não foi possível capturar tela de diagnóstico.")


def solicitar_dados_entrada():
    print("\n=== CONSULTA DE MARGEM | SANTANDER ===")
    usuario = input("Login: ").strip()
    senha = getpass.getpass("Senha: ")
    convenio = input("Código do convênio: ").strip()
    if not all((usuario, senha, convenio)):
        raise ValueError("Login, senha e código do convênio são obrigatórios.")
    return usuario, senha, convenio


def executar():
    load_dotenv(PASTA / ".env", override=False)
    headless = configuracao_bool("HEADLESS")
    reprocessar_erros = configuracao_bool("REPROCESSAR_ERROS")
    salvar_captura = configuracao_bool("SALVAR_DIAGNOSTICO")
    celular = re.sub(r"\D", "", os.getenv("CELULAR", "51998554621"))
    tempo_espera = int(os.getenv("TEMPO_ESPERA", "35"))
    if not (10 <= len(celular) <= 11):
        raise ValueError("CELULAR no .env deve conter 10 ou 11 dígitos.")
    if not (5 <= tempo_espera <= 300):
        raise ValueError("TEMPO_ESPERA precisa ser de 5 a 300 segundos.")

    parser = argparse.ArgumentParser(description="Consultor de margem Santander")
    parser.add_argument("--verificar", action="store_true", help="Validar o TXT sem abrir o site")
    argumentos = parser.parse_args()

    clientes = ler_clientes(PASTA / "cpf_nome.txt")
    if not clientes:
        raise ValueError("O arquivo cpf_nome.txt está vazio. Inclua linhas CPF,NOME e execute novamente.")
    print(f"Clientes válidos para consulta: {len(clientes)}")
    if argumentos.verificar:
        print("TXT validado. Nenhum login ou consulta foi realizado.")
        return

    usuario, senha, convenio = solicitar_dados_entrada()
    resultado = ResultadoCSV(PASTA / "resultado_margens.csv", clientes)
    pendentes = [c for c in clientes if not resultado.ja_processado(c.cpf, reprocessar_erros)]
    print(f"Pendentes: {len(pendentes)} | Já registrados: {len(clientes) - len(pendentes)}")
    print(f"CSV: {PASTA / 'resultado_margens.csv'}")
    if not pendentes:
        print("Nenhum CPF pendente. Ajuste REPROCESSAR_ERROS=true para refazer os erros.")
        return

    if headless:
        print("ATENÇÃO: HEADLESS=true não exibe a tela para digitar o código 2FA.")
        print("Use headless somente quando a sessão salva no perfil_chrome ainda estiver válida.")
    navegador = None
    try:
        navegador = driver_chrome(headless)
        navegador.get(URL_PORTAL)
        autenticar_automaticamente(navegador, usuario, senha)
        if headless:
            input("Verifique se já existe uma sessão autenticada. Pressione ENTER no CMD para iniciar: ")
        else:
            print("\nConclua qualquer código de autenticação 2FA na janela do Chrome.")
            print("Se o login não tiver sido preenchido, finalize-o manualmente.")
            input("Somente depois de estar logado, pressione ENTER no terminal do VS Code: ")

        # Verifica a sessão antes de iniciar a lista. Não cria ERRO em massa
        # se o usuário ainda não concluiu o 2FA.
        if not visivel(navegador, XP["produtos_menu"]) and not visivel(navegador, XP["nome"]):
            try:
                WebDriverWait(navegador, 15).until(
                    lambda d: visivel(d, XP["produtos_menu"]) or visivel(d, XP["nome"])
                )
            except TimeoutException as exc:
                raise RuntimeError(
                    "O menu Produtos não foi localizado. Verifique se o login e o 2FA "
                    "foram finalizados antes de apertar ENTER. Nenhuma consulta foi marcada como ERRO."
                ) from exc

        for indice, cliente in enumerate(pendentes, start=1):
            print(f"[{indice}/{len(pendentes)}] Consultando {cliente.nome} | CPF final {cliente.cpf[-4:]}")
            try:
                margem, status = consultar(
                    navegador, cliente, convenio, celular, tempo_espera
                )
            except KeyboardInterrupt:
                print("\nInterrompido. O CPF atual não foi marcado como ERRO; pode ser retomado.")
                break
            except (WebDriverException, TimeoutException, RuntimeError) as exc:
                status, margem = "ERRO", "0"
                logging.warning("Falha nesta consulta: %s: %s", type(exc).__name__, str(exc)[:180])
                if salvar_captura:
                    salvar_diagnostico(navegador, cliente.cpf)
            except Exception as exc:
                status, margem = "ERRO", "0"
                logging.exception("Erro inesperado na consulta: %s", type(exc).__name__)
                if salvar_captura:
                    salvar_diagnostico(navegador, cliente.cpf)
            # Esta linha persiste resultado mesmo com falha e antes do próximo CPF.
            resultado.registrar(cliente, margem, status)
            print(f"   Salvo no CSV: margem={margem} | status={status}")
        print("\nExecução encerrada. CSV atualizado no disco após cada consulta.")
    finally:
        if navegador is not None:
            try:
                navegador.quit()
            except WebDriverException:
                pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
    try:
        executar()
    except (FileNotFoundError, ValueError, RuntimeError, WebDriverException) as erro:
        print(f"\nFALHA: {erro}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        sys.exit(130)
