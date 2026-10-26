import csv
import tempfile
import unittest
from pathlib import Path

from dados import Cliente, ResultadoCSV, ler_clientes


class TestarDados(unittest.TestCase):
    def test_clientes_em_ambas_ordens_e_deduplicados(self):
        with tempfile.TemporaryDirectory() as base:
            arquivo = Path(base) / "cpf_nome.txt"
            arquivo.write_text(
                'CPF,NOME\n00000000001,Ana Silva\nJoão Souza,00000000002\n'
                '00000000003,"Souza, Joana"\n00000000001,Ana Silva\n',
                encoding="utf-8",
            )
            self.assertEqual(
                ler_clientes(arquivo),
                [Cliente('Ana Silva', '00000000001'),
                 Cliente('João Souza', '00000000002'),
                 Cliente('Souza, Joana', '00000000003')],
            )

    def test_entrada_invalida(self):
        with tempfile.TemporaryDirectory() as base:
            arquivo = Path(base) / "cpf_nome.txt"
            arquivo.write_text('123,Fulano\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, "CPF com 11 dígitos"):
                ler_clientes(arquivo)

    def test_csv_ao_vivo_retomada_e_sem_duplicacao(self):
        with tempfile.TemporaryDirectory() as base:
            caminho = Path(base) / "resultado_margens.csv"
            clientes = [Cliente("Ana", "00000000001"), Cliente("Beto", "00000000002")]
            resultado = ResultadoCSV(caminho, clientes)
            self.assertEqual(caminho.read_text(encoding="utf-8-sig"), 'nome;cpf;margem;status\n')
            resultado.registrar(clientes[0], "R$ 1.234,56", "OK")
            with caminho.open(encoding="utf-8-sig", newline="") as f:
                linhas = list(csv.DictReader(f, delimiter=';'))
            self.assertEqual(len(linhas), 1)
            self.assertEqual(linhas[0]['margem'], 'R$ 1.234,56')
            resultado.registrar(clientes[1], "nada", "ERRO")
            self.assertEqual(resultado.registros[clientes[1].cpf]['margem'], '0')
            segunda = ResultadoCSV(caminho, clientes)
            self.assertTrue(segunda.ja_processado('00000000001', False))
            self.assertFalse(segunda.ja_processado('00000000002', True))
            segunda.registrar(clientes[1], '12,34', 'OK')
            with caminho.open(encoding="utf-8-sig", newline="") as f:
                linhas = list(csv.DictReader(f, delimiter=';'))
            self.assertEqual(len(linhas), 2)
            self.assertEqual(linhas[1]['margem'], '12,34')


if __name__ == '__main__':
    unittest.main()
