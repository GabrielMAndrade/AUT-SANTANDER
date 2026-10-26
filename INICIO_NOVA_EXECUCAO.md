# Execução Santander — nova rodada, novo CSV

O robô **não lê nenhum CSV anterior para decidir quais clientes consultar**. Cada execução de `python main.py` parte do primeiro CPF do `cpf_nome.txt`, exceto quando você escolhe outro ponto de início. Cada execução gera automaticamente um arquivo exclusivo em `resultados/`, por exemplo:

`resultados/resultado_margens_20261026_140500_123456_ab12cd34.csv`

## Comandos

```powershell
python main.py                             # Consulta a lista inteira a partir do primeiro
python main.py --inicio 350                # Começa pelo 350º cliente válido do TXT
python main.py --cpf-inicial 00000000001   # Começa nesse CPF, inclusive
python main.py --inicio 350 --limite 10    # Consulta dez clientes a partir do 350º
python main.py --limite 2                 # Testa os dois primeiros, com CSV próprio
python main.py --verificar                # Apenas valida o TXT, sem gerar CSV
```

O programa continua salvando o CSV após **cada cliente com resultado**. Se for interrompido, o CSV parcial fica salvo para conferência. Uma nova execução nunca modifica esse arquivo e consulta novamente os CPFs do trecho solicitado, inclusive os já vistos antes. Um CPF pulado por timeout não gera uma linha de margem confirmada.

### Migração

- Guarde `cpf_nome.txt` na pasta `AUT-SANTANDER` ao lado de `main.py`.
- Guarde os CSVs antigos, se desejar. Eles não são usados pelo programa novo.
- Não é necessário apagar linhas do TXT para começar do meio: use `--inicio` ou `--cpf-inicial`.
- O ZIP não inclui listas reais de clientes, resultados, senhas, sessão do Chrome nem banco de consultas.

### Modo API (VPS/n8n)

`uvicorn api_santander:app` é o servidor da API. Iniciar ou reiniciar esse servidor **não** percorre `cpf_nome.txt` nem gera o CSV da rotina `main.py`. Cada POST ` /margem_cpf` ou `/consultas` cria uma solicitação identificada por ID no SQLite, e os resultados ficam disponíveis por `GET /consultas/{id}`. Para uma nova rodada via n8n, envie um novo POST com os clientes desejados e uma nova `Idempotency-Key` (se utilizar o cabeçalho). Não rode `main.py` simultaneamente com o worker API no mesmo Chrome.
