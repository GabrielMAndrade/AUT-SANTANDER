"""Garante que cada execução parte do TXT e não reaproveita CSV anterior."""
import csv
import tempfile
import unittest
from pathlib import Path

from dados import Cliente, ResultadoCSV, novo_caminho_csv, selecionar_clientes


class TestarExecucoesIndependentes(unittest.TestCase):
    def setUp(self):
        self.clientes = [
            Cliente('Primeiro', '00000000001'),
            Cliente('Segundo', '00000000002'),
            Cliente('Terceiro', '00000000003'),
        ]

    def test_nova_execucao_comeca_do_primeiro_inclusive_se_ja_consta_em_csv(self):
        with tempfile.TemporaryDirectory() as pasta:
            antigo = novo_caminho_csv(Path(pasta) / 'resultados')
            primeira = ResultadoCSV(antigo, self.clientes)
            primeira.registrar(self.clientes[0], '12,34', 'OK')
            antigo_antes = antigo.read_bytes()

            selecionados, inicio = selecionar_clientes(self.clientes)
            self.assertEqual(inicio, 1)
            self.assertEqual(selecionados, self.clientes)
            novo = novo_caminho_csv(Path(pasta) / 'resultados')
            self.assertNotEqual(antigo, novo)
            segunda = ResultadoCSV(novo, selecionados)
            self.assertFalse(segunda.ja_processado(self.clientes[0].cpf, False))
            self.assertEqual(segunda.registros, {})
            segunda.registrar(self.clientes[0], '45,67', 'OK')
            self.assertEqual(antigo.read_bytes(), antigo_antes)
            self.assertNotEqual(antigo.read_bytes(), novo.read_bytes())

    def test_inicio_numerico_e_limite(self):
        selecionados, inicio = selecionar_clientes(self.clientes, inicio=2, limite=1)
        self.assertEqual(inicio, 2)
        self.assertEqual(selecionados, [self.clientes[1]])

    def test_inicio_por_cpf_inclui_o_proprio_cliente(self):
        selecionados, inicio = selecionar_clientes(
            self.clientes, cpf_inicial='000.000.000-02'
        )
        self.assertEqual(inicio, 2)
        self.assertEqual(selecionados, self.clientes[1:])

    def test_inicio_inexistente_falha_sem_esvaziar_o_txt(self):
        with self.assertRaisesRegex(ValueError, 'ultrapassa'):
            selecionar_clientes(self.clientes, inicio=4)
        with self.assertRaisesRegex(ValueError, 'não encontrado'):
            selecionar_clientes(self.clientes, cpf_inicial='99999999999')

    def test_arquivos_criados_no_mesmo_instante_sao_distintos(self):
        with tempfile.TemporaryDirectory() as pasta:
            destinos = {novo_caminho_csv(Path(pasta)) for _ in range(30)}
            self.assertEqual(len(destinos), 30)
            self.assertTrue(all('resultado_margens_' in p.name for p in destinos))

    def test_csv_uma_execucao_so_contem_esse_lote(self):
        with tempfile.TemporaryDirectory() as pasta:
            selecionados, _ = selecionar_clientes(self.clientes, inicio=3)
            destino = novo_caminho_csv(Path(pasta))
            r = ResultadoCSV(destino, selecionados)
            r.registrar(selecionados[0], '5,50', 'OK')
            with destino.open(encoding='utf-8-sig', newline='') as f:
                dados = list(csv.DictReader(f, delimiter=';'))
            self.assertEqual([x['cpf'] for x in dados], ['00000000003'])


if __name__ == '__main__':
    unittest.main()
