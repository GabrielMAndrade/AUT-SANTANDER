"""Testes sem abrir Chrome nem fazer requisições ao Santander."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch


@unittest.skipUnless(importlib.util.find_spec("selenium"), "Instale as dependencias antes")
class TestesConexaoChrome(unittest.TestCase):
    def test_conecta_em_chrome_existente(self):
        import conexao_chrome as conexao
        with patch.object(conexao, "verificar_porta", return_value="Chrome/teste"), \
             patch.object(conexao.webdriver, "Chrome") as criar:
            driver = conexao.conectar_chrome()
            self.assertIs(driver, criar.return_value)
            self.assertEqual(criar.call_args.kwargs["options"].debugger_address, "127.0.0.1:9222")
            self.assertNotIn("--headless", str(criar.call_args))

    def test_seleciona_aba_portal_e_nao_cria_nova_aba(self):
        import conexao_chrome as conexao
        driver = MagicMock()
        driver.window_handles = ["a", "b"]
        driver.current_window_handle = "a"
        driver.current_url = "https://parceirosantander.com.br/spa-base/"
        self.assertTrue(conexao.selecionar_aba_portal(driver))
        driver.switch_to.window.assert_not_called()
        driver.get.assert_not_called()

    def test_fecha_chrome_dedicado_somente_quando_solicitado(self):
        import conexao_chrome as conexao
        driver = MagicMock()
        self.assertTrue(conexao.fechar_chrome_dedicado(driver))
        driver.execute_cdp_cmd.assert_called_once_with("Browser.close", {})

    def test_porta_fechada_mensagem_de_ajuda(self):
        import conexao_chrome as conexao
        with patch.object(conexao, "urlopen", side_effect=OSError("porta fechada")):
            with self.assertRaisesRegex(RuntimeError, "abrir_chrome.cmd"):
                conexao.verificar_porta()


if __name__ == "__main__":
    unittest.main()
