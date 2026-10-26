"""Testes unitários de interação nativa. Não acessam o Santander."""
import importlib.util
import unittest
from unittest.mock import MagicMock, call, patch


@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale selenium para rodar este teste')
class TestePreenchimentoSemJavaScript(unittest.TestCase):
    def test_conexao_nao_injeta_scripts_de_antideteccao(self):
        import conexao_chrome as conexao
        with patch.object(conexao, 'verificar_porta', return_value='Chrome/teste'), \
             patch.object(conexao.webdriver, 'Chrome') as criar:
            navegador = conexao.conectar_chrome()
            self.assertIs(navegador, criar.return_value)
            navegador.execute_cdp_cmd.assert_not_called()

    def test_clicar_nao_executa_javascript(self):
        import main
        navegador = MagicMock()
        elemento = MagicMock()
        main.clicar_elemento(navegador, elemento)
        elemento.click.assert_called_once()
        navegador.execute_script.assert_not_called()

    def test_digitar_preenche_e_dispara_tab(self):
        import main
        from selenium.webdriver.common.keys import Keys
        navegador = MagicMock()
        campo = MagicMock()
        campo.is_enabled.return_value = True
        campo.get_property.return_value = '123.456.789-01'
        navegador.find_element.return_value = campo
        with patch.object(main, 'aguardar_visivel', return_value=campo):
            main.digitar(navegador, '//input', '12345678901', timeout=2)
        campo.send_keys.assert_has_calls([
            call(Keys.CONTROL, 'a'),
            call(Keys.BACKSPACE),
            call('12345678901'),
            call(Keys.TAB),
        ])
        navegador.execute_script.assert_not_called()


if __name__ == '__main__':
    unittest.main()
