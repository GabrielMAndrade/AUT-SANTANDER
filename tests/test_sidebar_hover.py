"""Regressões locais para abrir menu recolhido por hover de ponteiro."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale Selenium para rodar o teste')
class TesteHoverProdutos(unittest.TestCase):
    def test_move_ponteiro_do_centro_ate_borda_esquerda(self):
        import main
        driver = MagicMock()
        driver.execute_script.return_value = {'width':1200,'height':800}
        chain = MagicMock()
        with patch.object(main, 'ActionChains', return_value=chain):
            main.abrir_sidebar_com_mouse(driver)
        chain.w3c_actions.pointer_action.move_to_location.assert_any_call(600,400)
        chain.w3c_actions.pointer_action.move_to_location.assert_any_call(2,400)
        self.assertEqual(chain.w3c_actions.pointer_action.move_to_location.call_count, 2)
        chain.perform.assert_called_once()

    def test_return_produtos_abre_sidebar_antes_de_buscar(self):
        import main
        driver = MagicMock()
        menu = MagicMock()
        driver.execute_script.return_value = {'width':1200,'height':800}
        eventos = []
        def hover(_): eventos.append('hover')
        def encontrar(_): eventos.append('encontrar'); return menu
        def click(*args): eventos.append('click')
        with patch.object(main, 'visivel', return_value=False), \
             patch.object(main, 'abrir_sidebar_com_mouse', side_effect=hover), \
             patch.object(main, '_localizar_menu_produtos', side_effect=encontrar), \
             patch.object(main, 'clicar_elemento', side_effect=click), \
             patch.object(main, 'aguardar_visivel') as campo, \
             patch.object(main, 'WebDriverWait') as wait:
            wait.return_value.until.side_effect=lambda f: f(driver)
            main.retornar_para_produtos(driver, 30)
        self.assertEqual(eventos, ['hover','encontrar','click'])
        campo.assert_called_once()

    def test_sidebar_nao_abriu_nao_consulta_outro_cliente(self):
        import main
        driver = MagicMock()
        with patch.object(main, 'visivel', return_value=False), \
             patch.object(main, 'abrir_sidebar_com_mouse'), \
             patch.object(main, 'WebDriverWait') as wait:
            wait.return_value.until.side_effect=main.TimeoutException('sidebar ausente')
            with self.assertRaisesRegex(main.FalhaNavegacao,'sidebar não abriu'):
                main.retornar_para_produtos(driver, 30)

if __name__ == '__main__': unittest.main()
