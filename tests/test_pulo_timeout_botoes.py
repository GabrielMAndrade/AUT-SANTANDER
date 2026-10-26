"""Regressão: timeout de botões de consulta pula CPF, mas exige retorno seguro."""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch


@unittest.skipUnless(importlib.util.find_spec('selenium'), 'Instale selenium')
class TestePuloTimeoutBotoes(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self.driver = MagicMock()
        self.cliente = MagicMock(nome='Cliente Teste', cpf='00000000001')

    def test_botao_nao_encontrado_em_dez_segundos_pula(self):
        m = self.main
        with patch.object(m, 'aguardar_clicavel', side_effect=m.TimeoutException) as aguardar, \
             patch.object(m, 'clicar_elemento') as clicar:
            with self.assertRaisesRegex(m.PularCliente, 'Ver Produtos'):
                m.clicar_botao_ou_pular(self.driver, '//button', 'Ver Produtos')
            aguardar.assert_called_once_with(self.driver, '//button', timeout=10)
            clicar.assert_not_called()

    def test_botao_encontrado_e_clicado(self):
        m = self.main
        botao = MagicMock()
        with patch.object(m, 'aguardar_clicavel', return_value=botao), \
             patch.object(m, 'clicar_elemento') as clicar:
            m.clicar_botao_ou_pular(self.driver, '//button', 'Simular')
            clicar.assert_called_once_with(self.driver, botao)

    def test_consulta_pula_quando_ver_produtos_nao_aparece(self):
        m = self.main
        with patch.object(m, 'abrir_consulta'), patch.object(m, 'digitar'), \
             patch.object(m, 'clicar_botao_ou_pular', side_effect=m.PularCliente('Ver Produtos')), \
             patch.object(m, 'avancar_ate_convenio') as avancar:
            with self.assertRaises(m.PularCliente):
                m.consultar(self.driver, self.cliente, '123', '51999999999', 35)
            avancar.assert_not_called()

    def test_consulta_pula_quando_simular_produto_nao_aparece(self):
        m = self.main
        with patch.object(m, 'abrir_consulta'), patch.object(m, 'digitar'), \
             patch.object(m, 'clicar_botao_ou_pular', side_effect=[None, m.PularCliente('Simular')]) as botoes, \
             patch.object(m, 'avancar_ate_convenio') as avancar:
            with self.assertRaises(m.PularCliente):
                m.consultar(self.driver, self.cliente, '123', '51999999999', 35)
            self.assertEqual(botoes.call_count, 2)
            avancar.assert_not_called()

    def test_buscar_ausente_pula_apos_preencher_codigo(self):
        m = self.main
        campo = MagicMock()
        campo.is_enabled.return_value = True
        campo.get_property.return_value = '123'
        with patch.object(m, '_dropdown_convenio_visivel', return_value=MagicMock()), \
             patch.object(m, '_codigo_selecionado', return_value=True), \
             patch.object(m, '_fechar_lista_convenio_se_aberta'), \
             patch.object(m, 'aguardar_visivel', return_value=campo), \
             patch.object(m, '_buscar_por_texto', side_effect=m.TimeoutException), \
             patch.object(m, 'WebDriverWait') as esperar, \
             patch.object(m.time, 'sleep'):
            esperar.return_value.until.return_value = True
            with self.assertRaisesRegex(m.PularCliente, 'Buscar'):
                m.escolher_codigo_convenio(self.driver, '123', 35)

    def test_timeout_seletor_convenio_pula(self):
        m = self.main
        with patch.object(m, 'WebDriverWait') as esperar:
            esperar.return_value.until.side_effect = m.TimeoutException
            with self.assertRaises(m.PularCliente):
                m.escolher_codigo_convenio(self.driver, '123', 35)

    def test_pulo_com_retorno_permanece_pulo(self):
        m = self.main
        with patch.object(m, 'consultar', side_effect=m.PularCliente('Simular não encontrado')), \
             patch.object(m, 'retornar_para_produtos') as retornar:
            with self.assertRaises(m.PularCliente):
                m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 35)
            retornar.assert_called_once_with(self.driver, 35)

    def test_falha_no_retorno_interrompe_por_seguranca(self):
        m = self.main
        with patch.object(m, 'consultar', side_effect=m.PularCliente('Simular não encontrado')), \
             patch.object(m, 'retornar_para_produtos', side_effect=m.FalhaNavegacao('sem Produtos')):
            with self.assertRaises(m.FalhaNavegacao):
                m.consultar_com_retorno(self.driver, self.cliente, '123', '51999999999', 35)

    def test_loop_segue_proximo_cpf_depois_do_timeout(self):
        m = self.main
        clientes = [m.Cliente('Cliente A', '00000000001'), m.Cliente('Cliente B', '00000000002')]
        csv = MagicMock()
        csv.ja_processado.return_value = False
        with patch.object(m, 'ler_clientes', return_value=clientes), \
             patch.object(m, 'ResultadoCSV', return_value=csv), \
             patch.object(m, 'solicitar_codigo_convenio', return_value='123'), \
             patch.object(m, 'conectar_chrome', return_value=self.driver), \
             patch.object(m, 'selecionar_aba_portal', return_value=True), \
             patch.object(m, 'aguardar_login_manual', return_value=True), \
             patch.object(m, 'sessao_autenticada', return_value=True), \
             patch.object(m, 'consultar_com_retorno', side_effect=[m.PularCliente('Simular'), ('R$ 20,00', 'OK')]) as consultar, \
             patch('builtins.input', return_value=''), \
             patch('sys.argv', ['main.py']):
            m.executar()
            self.assertEqual(consultar.call_count, 2)
            csv.registrar.assert_called_once_with(clientes[1], 'R$ 20,00', 'OK')


if __name__ == '__main__':
    unittest.main()
