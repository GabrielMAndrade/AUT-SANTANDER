"""Testes da navegação por texto e do pulo seguro; não acessam Santander."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch


@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale selenium para rodar o teste')
class TesteSimularCsgHome(unittest.TestCase):
    def test_clica_botao_encontrado_por_texto_e_confirma(self):
        import main
        driver = MagicMock()
        botao = MagicMock()
        with patch.object(main, '_dropdown_convenio_visivel', side_effect=[None, None]), \
             patch.object(main, 'visivel', return_value=False), \
             patch.object(main, 'localizar_simular_por_texto', return_value=botao), \
             patch.object(main, 'clicar_elemento') as clicar, \
             patch.object(main, 'WebDriverWait') as espera, \
             patch.object(main.time, 'sleep') as pausas:
            espera.return_value.until.side_effect = [botao, botao]
            main.avancar_ate_convenio(driver, tempo_espera=3)
            pausas.assert_called_once_with(main.DELAY_ANTES_SIMULAR)
            clicar.assert_called_once_with(driver, botao)

    def test_pula_cliente_quando_nao_acha_em_10_segundos(self):
        import main
        driver = MagicMock()
        # 0s primeira iteração, 10.1s segunda -> sai sem clique.
        with patch.object(main, '_dropdown_convenio_visivel', return_value=None), \
             patch.object(main, 'visivel', return_value=False), \
             patch.object(main, 'localizar_simular_por_texto', return_value=None), \
             patch.object(main.time, 'monotonic', side_effect=[0, 0, 10.1]), \
             patch.object(main.time, 'sleep'):
            with self.assertRaises(main.PularCliente):
                main.avancar_ate_convenio(driver, tempo_espera=3)

    def test_nao_clica_quando_formulario_ja_existe(self):
        import main
        driver = MagicMock()
        with patch.object(main, '_dropdown_convenio_visivel', return_value=MagicMock()), \
             patch.object(main, 'clicar_elemento') as clicar:
            main.avancar_ate_convenio(driver, tempo_espera=3)
            clicar.assert_not_called()

    def test_localiza_botao_no_csg_home_por_texto(self):
        import main
        driver = MagicMock()
        botao = MagicMock()
        botao.is_displayed.return_value = True
        botao.is_enabled.return_value = True
        driver.find_elements.return_value = [botao]
        self.assertIs(main.localizar_simular_por_texto(driver), botao)
        self.assertTrue(all('csg-home' in x for x in main.SELETORES_SIMULAR))

    def test_rotulo_codigo_aceita_acentos_e_maiusculas(self):
        import main
        self.assertEqual(main._normalizar_rotulo('  CÓDIGO  do   CONVÊNIO '), 'codigo do convenio')


if __name__ == '__main__':
    unittest.main()
