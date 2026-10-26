"""Garantia de retorno obrigatório pelo menu Produtos, sem URL/refresh."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale selenium')
class TesteNavegacaoSemRedirecionamento(unittest.TestCase):
    def test_formulario_pronto_nao_clica_nem_muda_url(self):
        import main
        driver = MagicMock()
        with patch.object(main, 'visivel', return_value=True), \
             patch.object(main, 'retornar_para_produtos') as retorno:
            main.abrir_consulta(driver, 3)
            retorno.assert_not_called()
        driver.get.assert_not_called()
        driver.refresh.assert_not_called()
        driver.switch_to.window.assert_not_called()

    def test_sem_formulario_chama_retorno_a_produtos(self):
        import main
        driver = MagicMock()
        with patch.object(main, 'visivel', return_value=False), \
             patch.object(main, 'retornar_para_produtos') as retorno:
            main.abrir_consulta(driver, 5)
            retorno.assert_called_once_with(driver, 5)
        driver.get.assert_not_called()
        driver.refresh.assert_not_called()

    def test_retorno_produtos_clica_menu_e_aguarda_formulario(self):
        import main
        driver = MagicMock()
        menu = MagicMock()
        with patch.object(main, 'visivel', return_value=False), \
             patch.object(main, '_localizar_menu_produtos', return_value=menu), \
             patch.object(main, 'abrir_sidebar_com_mouse') as hover, \
             patch.object(main, 'WebDriverWait') as esperar, \
             patch.object(main, 'clicar_elemento') as clicar, \
             patch.object(main, 'aguardar_visivel') as aguardar:
            esperar.return_value.until.return_value = menu
            main.retornar_para_produtos(driver, 7)
            hover.assert_called_once_with(driver)
            clicar.assert_called_once_with(driver, menu)
            aguardar.assert_called_once_with(driver, main.XP['nome'], timeout=7)
        driver.get.assert_not_called()
        driver.refresh.assert_not_called()

    def test_retorno_nao_repete_clique_se_formulario_ja_aberto(self):
        import main
        driver = MagicMock()
        with patch.object(main, 'visivel', return_value=True), \
             patch.object(main, 'clicar_elemento') as clicar:
            main.retornar_para_produtos(driver, 7)
            clicar.assert_not_called()

    def test_sessao_autenticada_nao_troca_de_aba(self):
        import main
        driver = MagicMock()
        with patch.object(main, 'visivel', return_value=True):
            self.assertTrue(main.sessao_autenticada(driver))
        driver.switch_to.window.assert_not_called()
        driver.get.assert_not_called()

    def test_seleciona_primeiro_a_aba_atual(self):
        import conexao_chrome
        driver = MagicMock()
        driver.current_window_handle = 'consulta'
        driver.window_handles = ['login', 'consulta']
        driver.current_url = 'https://www.parceirosantander.com.br/spa-base/consulta'
        self.assertTrue(conexao_chrome.selecionar_aba_portal(driver))
        driver.switch_to.window.assert_not_called()
        driver.get.assert_not_called()

if __name__ == '__main__':
    unittest.main()
