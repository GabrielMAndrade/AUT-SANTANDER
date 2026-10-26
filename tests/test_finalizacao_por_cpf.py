"""Regressão: nenhum CPF é seguido por outro sem retorno a Produtos."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale selenium')
class TesteFinalizacaoPorCPF(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self.driver = MagicMock()
        self.cliente = MagicMock()

    def test_margem_encontrada_retorna_produtos(self):
        m = self.main
        with patch.object(m, 'consultar', return_value=('R$ 200,00','OK')) as consulta, \
             patch.object(m, 'retornar_para_produtos') as retorno:
            self.assertEqual(m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 5), ('R$ 200,00','OK'))
            consulta.assert_called_once()
            retorno.assert_called_once_with(self.driver, 5)

    def test_sem_margem_retorna_produtos(self):
        m = self.main
        with patch.object(m, 'consultar', return_value=('0','ERRO')), \
             patch.object(m, 'retornar_para_produtos') as retorno:
            self.assertEqual(m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 5), ('0','ERRO'))
            retorno.assert_called_once_with(self.driver, 5)

    def test_botao_simular_ausente_retorna_produtos(self):
        m = self.main
        with patch.object(m, 'consultar', side_effect=m.PularCliente('não localizei')), \
             patch.object(m, 'retornar_para_produtos') as retorno:
            with self.assertRaises(m.PularCliente):
                m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 5)
            retorno.assert_called_once_with(self.driver, 5)

    def test_erro_tecnico_retorna_produtos_antes_de_parar(self):
        m = self.main
        with patch.object(m, 'consultar', side_effect=m.FalhaNavegacao('falhou')), \
             patch.object(m, 'retornar_para_produtos') as retorno:
            with self.assertRaises(m.FalhaNavegacao):
                m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 5)
            retorno.assert_called_once_with(self.driver, 5)

    def test_falha_no_retorno_nao_permita_pular_para_proximo(self):
        m = self.main
        with patch.object(m, 'consultar', return_value=('0','ERRO')), \
             patch.object(m, 'retornar_para_produtos', side_effect=m.FalhaNavegacao('sem Produtos')):
            with self.assertRaises(m.FalhaNavegacao):
                m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 5)

if __name__ == '__main__':
    unittest.main()
