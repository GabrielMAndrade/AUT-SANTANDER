"""Testes de seleção explícita do tipo de pesquisa; sem rede ou credenciais."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch, call


@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale selenium para rodar o teste')
class TesteDropdownConvenio(unittest.TestCase):
    def test_nao_digita_se_dropdown_nao_confirmar_selecao(self):
        import main
        driver = MagicMock()
        botao = MagicMock()
        opcao = MagicMock()
        with patch.object(main, '_dropdown_convenio_visivel', return_value=botao), \
             patch.object(main, '_codigo_selecionado', return_value=False), \
             patch.object(main, '_localizar_opcao_codigo', return_value=opcao), \
             patch.object(main, '_fechar_lista_convenio_se_aberta'), \
             patch.object(main, 'aguardar_visivel') as aguardar_input, \
             patch.object(main, 'clicar_elemento'), \
             patch.object(main, 'WebDriverWait') as esperar, \
             patch.object(main.time, 'sleep'):
            esperar.return_value.until.side_effect = [botao, opcao]
            with self.assertRaisesRegex(main.FalhaNavegacao, 'não ficou confirmada'):
                main.escolher_codigo_convenio(driver, '1234', 5)
            aguardar_input.assert_not_called()

    def test_seleciona_foca_digita_e_so_depois_busca(self):
        import main
        from selenium.webdriver.common.keys import Keys
        driver = MagicMock()
        botao = MagicMock()
        opcao = MagicMock()
        campo = MagicMock()
        campo.is_enabled.return_value = True
        driver.find_element.return_value = campo
        campo.get_property.return_value = '1234'
        busca = MagicMock()
        eventos = []
        def click(_, elemento):
            eventos.append('clicar tipo' if elemento is botao else 'selecionar tipo' if elemento is opcao else 'buscar')
        def aguardar(_, xpath, timeout):
            eventos.append('campo visivel')
            return campo
        def anotar_envio(*args):
            eventos.append('digitar')
        campo.send_keys.side_effect = anotar_envio
        with patch.object(main, '_dropdown_convenio_visivel', return_value=botao), \
             patch.object(main, '_codigo_selecionado', side_effect=[False, True, True]), \
             patch.object(main, '_localizar_opcao_codigo', return_value=opcao), \
             patch.object(main, '_fechar_lista_convenio_se_aberta'), \
             patch.object(main, 'aguardar_visivel', side_effect=aguardar), \
             patch.object(main, '_buscar_por_texto', return_value=busca), \
             patch.object(main, 'clicar_elemento', side_effect=click), \
             patch.object(main, 'WebDriverWait') as esperar, \
             patch.object(main.time, 'sleep') as pausas:
            esperar.return_value.until.side_effect = [botao, opcao, True]
            main.escolher_codigo_convenio(driver, '1234', 5)
            self.assertEqual(eventos[:3], ['clicar tipo', 'selecionar tipo', 'campo visivel'])
            self.assertEqual(eventos[-1], 'buscar')
            self.assertTrue(eventos.index('digitar') < eventos.index('buscar'))
            self.assertTrue(all(c == call(main.INTERVALO_CONVENIO) for c in pausas.call_args_list))
            self.assertEqual(pausas.call_count, 5)


if __name__ == '__main__':
    unittest.main()
