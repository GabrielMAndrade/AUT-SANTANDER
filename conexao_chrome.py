"""Conexão ao Chrome que o operador abriu previamente pelo CMD.

Não inicia outro Chrome, não faz login e não manipula credenciais.
A porta de depuração deve ficar acessível SOMENTE em 127.0.0.1.
"""
from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import urlopen
from selenium import webdriver
from selenium.common.exceptions import WebDriverException

HOST = "127.0.0.1"
PORTA = 9222
ENDERECO = f"{HOST}:{PORTA}"
DOMINIO_PORTAL = "parceirosantander.com.br"


def verificar_porta() -> str:
    """Valida que a porta local é de um Chrome com DevTools habilitado."""
    try:
        with urlopen(f"http://{ENDERECO}/json/version", timeout=3) as resposta:
            info = json.load(resposta)
        if not isinstance(info, dict) or not info.get("Browser"):
            raise ValueError("a porta não retornou informações do Chrome")
        return str(info["Browser"])
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Não encontrei o Google Chrome com depuração na porta {PORTA}. "
            "Abra primeiro 'abrir_chrome.cmd' (ou use o comando do README), "
            "confirme que o navegador abriu e depois execute python main.py. "
            f"Detalhe: {type(exc).__name__}: {exc}"
        ) from exc


def conectar_chrome():
    """Conecta ao Chrome existente sem injetar scripts no navegador.

    O preenchimento dos formulários ocorre exclusivamente em main.py,
    via WebElement.send_keys(), com os eventos normais de entrada e blur.
    Não há tentativa de alterar navigator.webdriver ou outras propriedades.
    """
    verificar_porta()
    opcoes = webdriver.ChromeOptions()
    opcoes.debugger_address = ENDERECO
    try:
        return webdriver.Chrome(options=opcoes)
    except WebDriverException as exc:
        raise RuntimeError(
            "Não foi possível conectar o Selenium ao Chrome já aberto. "
            "Confirme se Chrome e ChromeDriver são compatíveis e se "
            f"a porta {PORTA} está ativa. Detalhe: {str(exc)[:350]}"
        ) from exc


def selecionar_aba_portal(driver) -> bool:
    """Prioriza a aba atual; nunca faz get, refresh ou cria abas.

    Se o WebDriver não estiver na aba do portal, procura outra aba
    existente do Santander. Caso não encontre, restaura a aba original.
    Esta seleção ocorre somente na conexão inicial, antes do ENTER.
    """
    try:
        atual = driver.current_window_handle
        handles = [atual] + [h for h in driver.window_handles if h != atual]
        for handle in handles:
            if handle != atual:
                driver.switch_to.window(handle)
            url = (driver.current_url or "").lower()
            if url.startswith("https://") and (
                url.split("/", 3)[2].split(":")[0] == DOMINIO_PORTAL
                or url.split("/", 3)[2].split(":")[0].endswith("." + DOMINIO_PORTAL)
            ):
                return True
        # Retorna ao identificador original em vez de deixar outra aba ativa.
        driver.switch_to.window(atual)
    except (WebDriverException, IndexError):
        return False
    return False


def fechar_chrome_dedicado(driver) -> bool:
    """Encerra o Chrome iniciado para a automação após timeout de login.

    Só deve ser chamado para o perfil Chrome aberto na porta local 9222.
    """
    try:
        driver.execute_cdp_cmd("Browser.close", {})
        return True
    except WebDriverException:
        try:
            driver.close()
            return True
        except WebDriverException:
            return False
