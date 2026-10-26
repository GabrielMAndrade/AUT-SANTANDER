"""Consulta Santander conectada a Chrome aberto previamente no CMD.

Apenas conecta via depuração local; NÃO abre Chrome, faz login ou 2FA.
Aguarda 5 minutos para reconhecer o login e o ENTER antes dos CPFs.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from dados import Cliente, ResultadoCSV, ler_clientes, selecionar_clientes, novo_caminho_csv
from conexao_chrome import conectar_chrome, selecionar_aba_portal, fechar_chrome_dedicado


PASTA = Path(__file__).resolve().parent

# Configuracoes: este main.py nao precisa do .env.
CELULAR = "51998554621"
TEMPO_ESPERA = 35
TEMPO_SIMULAR = 10  # Tempo máximo para localizar o botão Simular Proposta por texto.
TEMPO_BOTAO = 10  # Botões de consulta não encontrados: pular CPF após 10 s.
DELAY_ANTES_SIMULAR = 5.0  # Espera após o botão aparecer, antes de clicar.
INTERVALO_CONVENIO = 0.4  # Cinco pausas de 0,4 s: aproximadamente 2 s fixos no convênio.
TEMPO_ABRIR_SIDEBAR = 8  # Tempo máximo para a opção Produtos aparecer após o movimento do mouse.
LIMITE_PULOS_SEGUIDOS = 0  # 0 = continuar após CPF pulado; um número >0 ativa parada de segurança.
LIMITE_LOGIN = 300  # 5 minutos
SALVAR_DIAGNOSTICO = False
# Limita sequências de avisos/tentativas sem margem para revisar o portal.
LIMITE_ERROS_SEGUIDOS = 0  # 0 = continuar mesmo com margem não encontrada; >0 ativa parada.

XP = {
    "nome": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[2]/dss-form-field/div/input",
    "cpf": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[3]/dss-form-field/div/input",
    "celular": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[4]/dss-form-field/div/input",
    "ver_produtos": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-verify-account/div/form/div[5]/button",
    "simular": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-select-product/div[2]/div/div/div/div/dss-product-card/div/dss-product-card-actions/button",
    "sem_srcc": "/html/body/fve-root/fve-logged-area/main/fve-mfe-recommendation-element/fve-select-product/app-dialog-srcc/dss-dialog/div/div/dss-dialog-footer/button[1]",
    # O botão Simular Proposta agora é encontrado pelo texto/aria-label dentro de csg-home.
    "dropdown_convenio": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[1]/dss-form-field/div/dss-dropdown/div/button",
    "opcao_codigo": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[1]/dss-form-field/div/dss-dropdown/div/ul/li[2]/a/span/option",
    "input_convenio": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[2]/csg-input-autocomplete/form/dss-search-bar/div/div/input",
    "buscar": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/div/csg-agreement-form/section/div/main/form/section[1]/div/div[3]/button",
    "erro": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/section/div[1]/csg-warning/dss-alert-banner/div/div/span",
    "margem": "/html/body/fve-root/fve-logged-area/main/fve-mfe-mob-element/div/csg-stepper/section/div/csg-employer-page/div/online-form/section[1]/section[2]/dss-form-field[2]/div/input",
    "produtos_menu": "/html/body/fve-root/fve-logged-area/fve-menu/dss-menu/aside/div[2]/dss-menu-item[2]/div/div",
}


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
    """Clique nativo WebDriver. Não executa JavaScript ou clique sintético DOM."""
    try:
        elemento.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        # Ação de mouse via Selenium, para elementos que exigem posição/foco.
        # Se houver overlay ou bloqueio, falha em vez de forçar o clique via JS.
        ActionChains(driver).move_to_element(elemento).click().perform()


def clicar(driver, xpath: str, timeout: float = 35) -> None:
    elemento = aguardar_clicavel(driver, xpath, timeout)
    clicar_elemento(driver, elemento)


def _campo_corresponde_ao_valor(atual: str, esperado: str) -> bool:
    """Compara valores, aceitando formatação de CPF/telefone pelo portal."""
    atual = str(atual or '').strip()
    esperado = str(esperado).strip()
    if esperado.isdecimal():
        return re.sub(r"\D", "", atual) == esperado
    return atual.casefold() == esperado.casefold()


def digitar(driver, xpath: str, texto: str, timeout: float = 35) -> None:
    """Digitação real por WebDriver (input/change/blur esperados na UI)."""
    campo = aguardar_visivel(driver, xpath, timeout)
    if not campo.is_enabled():
        raise FalhaNavegacao('Campo de formulário visível, porém desabilitado.')
    campo.click()
    campo.send_keys(Keys.CONTROL, 'a')
    campo.send_keys(Keys.BACKSPACE)
    campo.send_keys(str(texto))
    # Aplicações Angular geralmente validam ao perder o foco.
    campo.send_keys(Keys.TAB)
    try:
        WebDriverWait(driver, 4, poll_frequency=0.2).until(
            lambda d: _campo_corresponde_ao_valor(
                (d.find_element(By.XPATH, xpath).get_property('value') or ''),
                str(texto),
            )
        )
    except TimeoutException as exc:
        raise FalhaNavegacao(
            'O portal não confirmou o valor digitado em um campo. '
            'Confira a máscara/validação e o XPath antes de prosseguir.'
        ) from exc


# Verifica APENAS a aba atual. Não troca de aba, não recarrega nem muda URL.
# A presença isolada de fve-logged-area não comprova que o 2FA terminou.
def sessao_autenticada(driver) -> bool:
    return visivel(driver, XP["produtos_menu"]) or visivel(driver, XP["nome"])


def aguardar_login_manual(driver, limite_segundos: int = 300) -> bool:
    """Aguarda até 5 minutos pelo login/2FA na aba já aberta do Santander.

    Retorna False se não reconhecer a área autenticada no prazo.
    """
    print("\nConectado ao Chrome aberto pelo CMD. Faça login + 2FA manualmente.")
    print(f"Tempo máximo para concluir o login: {limite_segundos // 60} minutos.")
    print("Nenhum CPF será consultado antes de você pressionar ENTER.\n")
    try:
        WebDriverWait(driver, limite_segundos, poll_frequency=0.5).until(sessao_autenticada)
    except TimeoutException:
        print("\nTEMPO ESGOTADO: login não identificado em 5 minutos.")
        print("Fechando o navegador sem consultar nenhum CPF.")
        return False
    print("Login identificado no portal.")
    return True


class FalhaNavegacao(RuntimeError):
    """Página inesperada: não consultar nem registrar ERRO para o CPF atual."""


def _localizar_menu_produtos(driver):
    """Identifica a opção Produtos do menu lateral por texto; XPath como reserva.

    Não confunde o botão 'Ver Produtos' dentro do formulário com o menu.
    """
    seletores = (
        (By.XPATH, "//fve-menu//dss-menu-item[.//*[normalize-space()='Produtos'] or "
                   "normalize-space(.)='Produtos' or contains(normalize-space(.), 'Produtos')]"),
        (By.XPATH, XP["produtos_menu"]),
    )
    for by, seletor in seletores:
        try:
            for item in driver.find_elements(by, seletor):
                if item.is_displayed() and item.is_enabled():
                    return item
        except (StaleElementReferenceException, WebDriverException):
            continue
    return None


def abrir_sidebar_com_mouse(driver) -> None:
    """Provoca o hover no menu recolhido, do centro ao canto esquerdo.

    Move o ponteiro REAL do WebDriver; a consulta de dimensões do viewport
    usa JavaScript somente de leitura, sem alterar DOM ou propriedades.
    """
    try:
        dimensoes = driver.execute_script(
            "return {width: document.documentElement.clientWidth, "
            "height: document.documentElement.clientHeight};"
        )
        largura = int(dimensoes["width"])
        altura = int(dimensoes["height"])
        if largura < 150 or altura < 150:
            raise ValueError('Viewport inválido')
        meio_x, meio_y = largura // 2, altura // 2
        movimentos = ActionChains(driver)
        movimentos.w3c_actions.pointer_action.move_to_location(meio_x, meio_y)
        movimentos.pause(0.3)
        movimentos.w3c_actions.pointer_action.move_to_location(2, meio_y)
        movimentos.pause(0.5)
        movimentos.perform()
        print('   [Produtos] mouse do centro até a borda esquerda; aguardando sidebar...')
    except (WebDriverException, ValueError, TypeError, KeyError) as exc:
        raise FalhaNavegacao(
            'Não foi possível mover o ponteiro para abrir a sidebar. '
            'Confira se a janela do Chrome está visível e em primeiro plano.'
        ) from exc


def retornar_para_produtos(driver, tempo_espera: int) -> None:
    """Após CADA CPF, volta ao formulário por clique no menu Produtos.

    Não usa driver.get()/refresh() e não tenta consultar o próximo CPF
    enquanto a tela de nome/CPF/celular não estiver realmente pronta.
    Se o formulário já estiver visível, a navegação já está concluída.
    """
    if visivel(driver, XP["nome"]):
        print('   [Produtos] formulário já aberto; pronto para o próximo CPF.')
        return

    print('   [Produtos] retornando ao menu Produtos...')
    # A sidebar está recolhida: sem hover, a opção Produtos não fica visível.
    abrir_sidebar_com_mouse(driver)
    try:
        menu = WebDriverWait(driver, min(TEMPO_ABRIR_SIDEBAR, tempo_espera), poll_frequency=0.2).until(
            lambda d: _localizar_menu_produtos(d) or
            (True if visivel(d, XP["nome"]) else False)
        )
    except TimeoutException as exc:
        raise FalhaNavegacao(
            'A sidebar não abriu ou Produtos não apareceu após o movimento do mouse. '
            'Próximo CPF NÃO será iniciado.'
        ) from exc

    # A aplicação pode terminar sozinha a transição para a tela inicial.
    if visivel(driver, XP["nome"]):
        print('   [Produtos] formulário disponível.')
        return

    try:
        if menu is True:  # Retorno defensivo da condição de espera.
            raise FalhaNavegacao('Formulário inicial não está disponível após o retorno.')
        clicar_elemento(driver, menu)
        aguardar_visivel(driver, XP["nome"], timeout=tempo_espera)
    except (TimeoutException, WebDriverException, StaleElementReferenceException) as exc:
        raise FalhaNavegacao(
            'O clique em Produtos não abriu o formulário inicial. '
            'A execução será interrompida para não misturar clientes.'
        ) from exc

    print('   [Produtos] tela inicial confirmada. Próximo CPF liberado.')


def abrir_consulta(driver, tempo_espera: int) -> None:
    """Garante formulário pronto no início sem URL direta ou refresh."""
    if not visivel(driver, XP["nome"]):
        retornar_para_produtos(driver, tempo_espera)


def _normalizar_rotulo(texto: str) -> str:
    """Compara rótulos ignorando acentos, caixa e espaços extras."""
    valor = unicodedata.normalize('NFKD', str(texto or ''))
    valor = ''.join(c for c in valor if not unicodedata.combining(c))
    return ' '.join(valor.casefold().split())


# A busca é restrita à página csg-home: não confunde o botão de simulação
# de produto da etapa anterior com "Simular Proposta".
SELETORES_SIMULAR = (
    "//csg-home//button[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'simular') "
    "and contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'proposta')]",
    "//csg-home//button[contains(translate(normalize-space(@aria-label), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'simular')]",
    "//csg-home//button[contains(translate(normalize-space(@title), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'simular')]",
    "//csg-home//button[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'simular')]",
)


def localizar_simular_por_texto(driver):
    """Retorna o botão real visível/habilitado, sem depender do XPath absoluto."""
    for seletor in SELETORES_SIMULAR:
        try:
            for botao in driver.find_elements(By.XPATH, seletor):
                if botao.is_displayed() and botao.is_enabled():
                    return botao
        except (StaleElementReferenceException, WebDriverException):
            continue
    return None


class PularCliente(FalhaNavegacao):
    """Etapa indisponível nesta tentativa; CPF permanece pendente, sem erro no CSV.

    Um timeout de botão não prova, isoladamente, que o produto é indisponível.
    """


def clicar_botao_ou_pular(driver, xpath: str, nome: str, timeout: float = TEMPO_BOTAO) -> None:
    """Se um botão de consulta não ficar clicável no prazo, pula o CPF.

    Não transforma falha de clique nem erro de sessão em indisponibilidade.
    O retorno ao formulário Produtos é obrigatório antes do próximo CPF.
    """
    try:
        elemento = aguardar_clicavel(driver, xpath, timeout=timeout)
    except TimeoutException as exc:
        raise PularCliente(
            f'Botão "{nome}" não encontrado/habilitado em {timeout:g} segundos. '
            'Pulando este CPF e retornando a Produtos.'
        ) from exc
    clicar_elemento(driver, elemento)


def _dropdown_convenio_visivel(driver):
    """Dropdown do formulário, localizado por componente com XPath de reserva."""
    try:
        for botao in driver.find_elements(By.CSS_SELECTOR, 'csg-agreement-form dss-dropdown button'):
            if botao.is_displayed() and botao.is_enabled():
                return botao
    except (StaleElementReferenceException, WebDriverException):
        pass
    try:
        for botao in driver.find_elements(By.XPATH, XP['dropdown_convenio']):
            if botao.is_displayed() and botao.is_enabled():
                return botao
    except (StaleElementReferenceException, WebDriverException):
        pass
    return None


def avancar_ate_convenio(driver, tempo_espera: int) -> None:
    """Espera Simular Proposta por texto, aguarda 5 s e só então clica.

    Dez segundos para encontrar o botão inicialmente. Após a pausa, o
    elemento é procurado novamente, porque pode ter sido recriado pelo SPA.
    Se a etapa não estiver pronta, mantém o CPF pendente (PularCliente).
    """
    inicio = time.monotonic()
    fim = inicio + TEMPO_SIMULAR
    while time.monotonic() < fim:
        if _dropdown_convenio_visivel(driver) is not None:
            print('   [Simular] formulário de convênio já disponível.')
            return
        if visivel(driver, XP['sem_srcc']):
            print('   [Simular] concluindo diálogo SRCC...')
            try:
                clicar(driver, XP['sem_srcc'], timeout=min(3, max(1, fim-time.monotonic())))
            except (TimeoutException, WebDriverException) as exc:
                raise FalhaNavegacao('Diálogo SRCC não pôde ser concluído.') from exc
            fim = time.monotonic() + TEMPO_SIMULAR
            continue
        botao = localizar_simular_por_texto(driver)
        if botao is not None:
            print(f'   [Simular] localizado. Aguardando {DELAY_ANTES_SIMULAR:g} segundos antes do clique...')
            time.sleep(DELAY_ANTES_SIMULAR)
            # Não usar o WebElement obtido antes do delay: frameworks SPA
            # frequentemente recriam o botão durante o carregamento.
            try:
                botao = WebDriverWait(driver, TEMPO_SIMULAR, poll_frequency=0.25).until(
                    localizar_simular_por_texto
                )
            except TimeoutException as exc:
                raise PularCliente(
                    'Simular Proposta desapareceu após a espera de 5 segundos. '
                    'CPF permanecerá pendente.'
                ) from exc
            if _dropdown_convenio_visivel(driver) is not None:
                print('   [Simular] formulário de convênio já disponível; sem novo clique.')
                return
            print('   [Simular] botão estável e habilitado. Clicando...')
            try:
                clicar_elemento(driver, botao)
            except (WebDriverException, StaleElementReferenceException) as exc:
                raise PularCliente('O botão Simular foi recriado ou não recebeu o clique.') from exc
            try:
                WebDriverWait(driver, tempo_espera, poll_frequency=0.3).until(_dropdown_convenio_visivel)
            except TimeoutException as exc:
                raise PularCliente(
                    'Após o clique em Simular, o formulário de convênio não apareceu. '
                    'CPF permanecerá pendente.'
                ) from exc
            print('   [Simular] formulário de convênio confirmado.')
            return
        time.sleep(0.25)
    raise PularCliente(
        'Botão "Simular Proposta" não apareceu no csg-home em 10 segundos. '
        'CPF não foi gravado; retornando a Produtos.'
    )


def _opcoes_dropdown_visiveis(driver):
    """Busca só as opções do seletor de pesquisa, não do autocomplete."""
    try:
        return [
            item for item in driver.find_elements(
                By.CSS_SELECTOR, 'csg-agreement-form dss-dropdown ul li'
            ) if item.is_displayed()
        ]
    except (StaleElementReferenceException, WebDriverException):
        return []


def _codigo_selecionado(driver) -> bool:
    """Confirma indicação de Código do convênio no botão ou opção selecionada."""
    botao = _dropdown_convenio_visivel(driver)
    if botao is not None:
        pistas = (
            botao.text, botao.get_attribute('aria-label'),
            botao.get_attribute('title'), botao.get_attribute('value'),
        )
        if any('codigo do convenio' in _normalizar_rotulo(x) for x in pistas):
            return True
    try:
        opcoes = driver.find_elements(By.CSS_SELECTOR, 'csg-agreement-form dss-dropdown option')
        for opcao in opcoes:
            if 'codigo do convenio' in _normalizar_rotulo(opcao.get_attribute('textContent')):
                if opcao.is_selected() or opcao.get_attribute('selected') is not None:
                    return True
    except (StaleElementReferenceException, WebDriverException):
        pass
    return False


def _localizar_opcao_codigo(driver):
    """Clica no item pelo rótulo, preferindo seu <a> em vez do <option> interno."""
    for item in _opcoes_dropdown_visiveis(driver):
        texto = _normalizar_rotulo(item.text or item.get_attribute('textContent'))
        if 'codigo do convenio' not in texto:
            continue
        try:
            for acao in item.find_elements(By.CSS_SELECTOR, 'a, button, [role="option"]'):
                if acao.is_displayed() and acao.is_enabled():
                    return acao
        except (StaleElementReferenceException, WebDriverException):
            continue
        return item
    return None


def _fechar_lista_convenio_se_aberta(driver, origem, descricao: str):
    """Fecha menu remanescente por Escape, sem remover a seleção feita."""
    if not _opcoes_dropdown_visiveis(driver):
        return
    print(f'   [Convênio] lista permaneceu aberta {descricao}; fechando com ESC...')
    origem.send_keys(Keys.ESCAPE)
    try:
        WebDriverWait(driver, 2, poll_frequency=0.1).until(
            lambda d: not _opcoes_dropdown_visiveis(d)
        )
    except TimeoutException as exc:
        raise FalhaNavegacao(
            'A lista do tipo de consulta continua aberta após ESC. '
            'Preciso do HTML/XPath do dropdown para ajustar o seletor.'
        ) from exc


def _buscar_por_texto(driver, tempo_espera: int):
    """Prioriza o Buscar do formulário pelo texto; conserva XPath de reserva."""
    def encontrar(d):
        seletores = (
            "//csg-agreement-form//button[contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'buscar')]",
            XP['buscar'],
        )
        for seletor in seletores:
            try:
                for botao in d.find_elements(By.XPATH, seletor):
                    if botao.is_displayed() and botao.is_enabled():
                        return botao
            except (StaleElementReferenceException, WebDriverException):
                pass
        return False
    return WebDriverWait(driver, tempo_espera, poll_frequency=0.25).until(encontrar)


def escolher_codigo_convenio(driver, convenio: str, tempo_espera: int) -> None:
    """Seleciona o tipo, FECHA a lista e só então digita o código.

    Aproximadamente 2 s de pausas fixas ao todo (5 x 0,4 s), além das
    esperas condicionais para confirmar estado dos componentes.
    """
    try:
        botao = WebDriverWait(driver, tempo_espera, poll_frequency=0.25).until(
            _dropdown_convenio_visivel
        )
    except TimeoutException as exc:
        raise PularCliente(
            'O seletor de pesquisa do convênio não ficou disponível no prazo. '
            'Pulando CPF e retornando a Produtos.'
        ) from exc

    if not _codigo_selecionado(driver):
        print('   [Convênio] abrindo tipos de pesquisa...')
        clicar_elemento(driver, botao)
        time.sleep(INTERVALO_CONVENIO)

        try:
            opcao = WebDriverWait(driver, min(10, tempo_espera), poll_frequency=0.25).until(
                _localizar_opcao_codigo
            )
        except TimeoutException as exc:
            raise FalhaNavegacao(
                'Não encontrei a opção "Código do convênio" na lista. '
                'Confira o texto e o HTML deste dropdown.'
            ) from exc
        print('   [Convênio] selecionando Código do convênio...')
        clicar_elemento(driver, opcao)
        time.sleep(INTERVALO_CONVENIO)

    # O componente pode permanecer visualmente aberto após o clique no <a>.
    # Fechar com ESC e exigir indicação do tipo escolhido ANTES de preencher.
    botao = _dropdown_convenio_visivel(driver)
    if botao is None:
        raise FalhaNavegacao('O botão do dropdown desapareceu após selecionar o tipo.')
    _fechar_lista_convenio_se_aberta(driver, botao, 'após selecionar o tipo')
    if not _codigo_selecionado(driver):
        raise FalhaNavegacao(
            'A opção Código do convênio não ficou confirmada no dropdown. '
            'Nenhum código foi digitado; envie o HTML ou XPath do botão já selecionado.'
        )
    print('   [Convênio] opção confirmada e dropdown fechado.')
    time.sleep(INTERVALO_CONVENIO)

    campo = aguardar_visivel(driver, XP['input_convenio'], timeout=tempo_espera)
    if not campo.is_enabled():
        raise FalhaNavegacao('Campo do código está desabilitado.')
    print('   [Convênio] preenchendo código...')
    campo.click()
    campo.send_keys(Keys.CONTROL, 'a')
    campo.send_keys(Keys.BACKSPACE)
    campo.send_keys(str(convenio))
    campo.send_keys(Keys.TAB)
    time.sleep(INTERVALO_CONVENIO)
    try:
        WebDriverWait(driver, 4, poll_frequency=0.25).until(
            lambda d: _campo_corresponde_ao_valor(
                d.find_element(By.XPATH, XP['input_convenio']).get_property('value') or '',
                convenio,
            )
        )
    except TimeoutException as exc:
        raise FalhaNavegacao('O campo não manteve o código do convênio informado.') from exc

    botao = _dropdown_convenio_visivel(driver)
    if botao is not None:
        _fechar_lista_convenio_se_aberta(driver, botao, 'após preencher o código')
    if not _codigo_selecionado(driver):
        raise FalhaNavegacao('O tipo Código do convênio foi perdido durante a digitação.')
    print('   [Convênio] código validado; clicando Buscar...')
    try:
        buscar = _buscar_por_texto(driver, min(TEMPO_BOTAO, tempo_espera))
    except TimeoutException as exc:
        raise PularCliente(
            'Botão Buscar não apareceu habilitado após preencher o convênio. '
            'Pulando CPF e retornando a Produtos.'
        ) from exc
    time.sleep(INTERVALO_CONVENIO)
    clicar_elemento(driver, buscar)

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
            logging.warning("O portal apresentou aviso de erro/indisponibilidade na consulta.")
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
    logging.warning("Tempo esgotado sem obter margem positiva; conferir tela e regras do convênio.")
    return "0", "ERRO"


def consultar(driver, cliente: Cliente, convenio: str, celular: str, tempo_espera: int) -> tuple[str, str]:
    abrir_consulta(driver, tempo_espera)
    digitar(driver, XP["nome"], cliente.nome, tempo_espera)
    digitar(driver, XP["cpf"], cliente.cpf, tempo_espera)
    digitar(driver, XP["celular"], celular, tempo_espera)
    # Botões indisponíveis não abortam o lote: passam ao próximo CPF.
    clicar_botao_ou_pular(driver, XP["ver_produtos"], "Ver Produtos")
    clicar_botao_ou_pular(driver, XP["simular"], "Simular (seleção do produto)")

    # Aguardar a página csg-home, clicar no botão Simular informado e
    # confirmar o formulário de convênio antes de preencher/buscar.
    avancar_ate_convenio(driver, tempo_espera)
    escolher_codigo_convenio(driver, convenio, tempo_espera)
    return aguardar_margem_ou_erro(driver, tempo_espera)


def consultar_com_retorno(driver, cliente: Cliente, convenio: str, celular: str,
                         tempo_espera: int) -> tuple[str, str]:
    """A consulta SEMPRE termina tentando voltar a Produtos.

    O finally também vale para margem ausente, botão Simular não encontrado,
    timeout ou exceção durante a consulta. Sem retorno confirmado, o laço
    externo não deve consultar outro CPF.
    """
    try:
        return consultar(driver, cliente, convenio, celular, tempo_espera)
    finally:
        retornar_para_produtos(driver, tempo_espera)


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


def solicitar_codigo_convenio() -> str:
    print("\n=== CONSULTA DE MARGEM | SANTANDER ===")
    convenio = input("Código do convênio: ").strip()
    if not convenio:
        raise ValueError("O código do convênio é obrigatório.")
    return convenio


def executar():
    celular = re.sub(r"\D", "", CELULAR)
    tempo_espera = TEMPO_ESPERA
    salvar_captura = SALVAR_DIAGNOSTICO
    if not (10 <= len(celular) <= 11):
        raise ValueError("CELULAR deve conter 10 ou 11 digitos.")
    if not (5 <= tempo_espera <= 300):
        raise ValueError("TEMPO_ESPERA deve estar entre 5 e 300 segundos.")

    parser = argparse.ArgumentParser(description="Consultor de margem Santander")
    parser.add_argument("--verificar", action="store_true", help="Validar o TXT sem abrir o site")
    inicio_grupo = parser.add_mutually_exclusive_group()
    inicio_grupo.add_argument(
        "--inicio", type=int, default=1,
        help="Posição inicial do TXT (começa em 1; padrão: primeiro CPF)",
    )
    inicio_grupo.add_argument(
        "--cpf-inicial", type=str,
        help="Começar neste CPF do TXT, incluindo-o na execução",
    )
    parser.add_argument(
        "--limite", type=int, default=0,
        help="Consultar apenas N CPFs a partir do início escolhido (0 = todos)",
    )
    argumentos = parser.parse_args()
    if argumentos.limite < 0 or argumentos.inicio < 1:
        parser.error("--limite deve ser >= 0 e --inicio deve ser >= 1")

    clientes = ler_clientes(PASTA / "cpf_nome.txt")
    if not clientes:
        raise ValueError("O arquivo cpf_nome.txt está vazio. Inclua linhas CPF,NOME e execute novamente.")
    print(f"Clientes válidos para consulta: {len(clientes)}")
    if argumentos.verificar:
        print("TXT validado. Nenhum login ou consulta foi realizado.")
        return

    # Cada execução é independente: nenhuma informação de CSV antigo é usada
    # para pular clientes. Os CSVs anteriores permanecem preservados.
    selecionados, posicao_inicial = selecionar_clientes(
        clientes,
        inicio=argumentos.inicio,
        cpf_inicial=argumentos.cpf_inicial,
        limite=argumentos.limite,
    )
    convenio = solicitar_codigo_convenio()
    caminho_csv = novo_caminho_csv(PASTA / "resultados")
    resultado = ResultadoCSV(caminho_csv, selecionados)
    print(
        f"Início: posição {posicao_inicial} do TXT | "
        f"Clientes desta execução: {len(selecionados)} de {len(clientes)} | "
        "CSV anterior: ignorado"
    )
    print(f"CSV exclusivo desta execução: {caminho_csv}")

    navegador = None
    try:
        navegador = conectar_chrome()
        # Faz a seleção inicial uma única vez; após isso, fixa a aba.
        # Nenhuma URL é carregada e nenhuma aba é criada pelo Selenium.
        if not selecionar_aba_portal(navegador):
            print("Não encontrei a aba Santander ainda. Conclua o login na aba atual.")
        print("Chrome existente encontrado. Nenhuma nova janela foi criada pelo Python.")

        # A autenticação e o 2FA permanecem inteiramente manuais.
        if not aguardar_login_manual(navegador, limite_segundos=LIMITE_LOGIN):
            if fechar_chrome_dedicado(navegador):
                print("Janela de Chrome dedicada encerrada por timeout.")
            else:
                print("Não foi possível fechar o Chrome automaticamente. Feche-o no Windows.")
            return

        input("Quando estiver na tela correta, pressione ENTER no terminal para iniciar as consultas: ")
        print("Iniciando na aba e na URL atuais. Nenhum redirecionamento automático será feito.")

        # Evita marcar todos os CPFs como ERRO se a sessão expirou durante a espera.
        if not sessao_autenticada(navegador):
            raise RuntimeError(
                "A sessão autenticada não está disponível após o ENTER. "
                "Faça login novamente. Nenhum CPF foi consultado."
            )

        erros_seguidos = 0
        pulos_seguidos = 0
        for indice, cliente in enumerate(selecionados, start=1):
            if not sessao_autenticada(navegador):
                print("Sessão expirada ou janela fechada; execução interrompida sem marcar mais CPFs.")
                break
            print(f"[{indice}/{len(selecionados)}] Consultando {cliente.nome} | CPF final {cliente.cpf[-4:]}")
            try:
                margem, status = consultar_com_retorno(
                    navegador, cliente, convenio, celular, tempo_espera
                )
            except KeyboardInterrupt:
                print("\nInterrompido. O CPF atual não foi marcado como ERRO; pode ser retomado.")
                break
            except PularCliente as exc:
                pulos_seguidos += 1
                print(f'   [PULADO] {exc}')
                print('   CPF pulado nesta execução; nada gravado no CSV atual.')
                if LIMITE_PULOS_SEGUIDOS and pulos_seguidos >= LIMITE_PULOS_SEGUIDOS:
                    print(
                        f'{pulos_seguidos} CPFs seguidos com etapas de consulta indisponíveis. '
                        'Interrompendo para evitar repetir uma falha da página.'
                    )
                    break
                continue
            except FalhaNavegacao as exc:
                print(f"\nEXECUÇÃO INTERROMPIDA: {exc}")
                print("O CPF atual não foi registrado como ERRO no CSV.")
                break
            except (WebDriverException, TimeoutException, RuntimeError) as exc:
                logging.error("Falha técnica (%s): %s", type(exc).__name__, str(exc)[:160])
                if salvar_captura:
                    salvar_diagnostico(navegador, cliente.cpf)
                print("Falha técnica: o CPF atual NÃO foi registrado como ERRO. Corrija e retome.")
                break
            except Exception as exc:
                logging.exception("Falha inesperada (%s)", type(exc).__name__)
                if salvar_captura:
                    salvar_diagnostico(navegador, cliente.cpf)
                print("Falha inesperada: CPF atual não registrado; execução interrompida.")
                break

            # Grava somente resultados válidos do fluxo; não confunde
            # falha do Selenium com ausência de margem do cliente.
            pulos_seguidos = 0
            resultado.registrar(cliente, margem, status)
            print(f"   Salvo no CSV: margem={margem} | status={status}")
            erros_seguidos = erros_seguidos + 1 if status == "ERRO" else 0
            if LIMITE_ERROS_SEGUIDOS and erros_seguidos >= LIMITE_ERROS_SEGUIDOS:
                print(
                    f"{erros_seguidos} consultas consecutivas sem margem positiva/aviso do portal. "
                    "Pausado para verificar se há erro sistêmico ou restrição."
                )
                break
        print(f"\nExecução encerrada. Arquivo desta execução: {caminho_csv}")
    finally:
        if navegador is not None:
            try:
                # Libera conexão Selenium; o Chrome foi aberto pelo CMD.
                # Na execução normal, mantenha a janela para uso manual.
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
