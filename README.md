> **Nova integração VPS/n8n:** para instalar e usar a API HTTP com fila de consultas, veja primeiro [`README_API_VPS.md`](README_API_VPS.md). O restante deste README explica apenas a operação antiga por terminal (`main.py`).

# AUT-SANTANDER — Chrome aberto pelo CMD (porta 9222)

Automação assistida em Python + Selenium que **se conecta ao Google Chrome que você abriu pelo CMD**. O Python **não abre outra janela**, não pede login/senha e não interfere no código de autenticação de dois fatores (2FA). Depois que o site confirma a entrada, o script só inicia as consultas quando você pressionar **ENTER no terminal**.

**Importante:** esta versão elimina o antigo JavaScript que alterava `navigator.webdriver`, `window.chrome` e permissões. `main.py` preenche via `send_keys()` e navega via cliques nativos do Selenium, sem macros. O portal continua podendo identificar ou restringir WebDriver. Use apenas com acesso autorizado ao portal e aos CPFs. Conectar via depuração não ignora nem desativa mecanismos de proteção do Santander. Os XPaths foram fornecidos pelo operador e não foram validados em sessão autenticada real.

## 1. Requisitos

- Windows 10/11, Google Chrome e Python 3.10+.
- Ter autorização para consultar os clientes no portal Santander.
- O Chrome do projeto usa um **perfil separado** e a porta de depuração **9222, restrita ao computador (127.0.0.1)**.

## 2. Abra o Chrome pelo CMD — PRIMEIRO

**Opção recomendada:** na pasta `AUT-SANTANDER`, dê duplo clique em **`abrir_chrome.cmd`**. O arquivo procura o Chrome nos locais comuns e executa o comando correto. Não precisa escrever nada.

**Ou, manualmente**, abra o **Prompt de Comando (CMD)** do Windows e cole o comando abaixo (se o Chrome estiver instalado em `Program Files`):

```bat

@echo off

start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" ^
 --remote-debugging-port=9222 ^
 --remote-debugging-address=127.0.0.1 ^
 --user-data-dir="%LOCALAPPDATA%\SOMA_SANTANDER_DEBUG" ^
 "https://www.parceirosantander.com.br/spa-base/"


```

Se o arquivo do Chrome não existir nesse caminho, prefira `abrir_chrome.cmd`, que tenta outros caminhos automaticamente.

**Não use o Chrome já aberto normalmente.** A janela do comando usa uma sessão própria, com perfil isolado, e você precisa fazer o login nela. Mantenha essa janela aberta. Se precisar reiniciar, feche **todas as janelas desse perfil do Santander** antes de executar `abrir_chrome.cmd` novamente.

> Chrome 136+ exige `--user-data-dir` **diferente do perfil padrão** para ativar depuração. Por isso, os dois métodos acima já contêm esse parâmetro. Esse perfil pode guardar cookies e informações de sessão: mantenha-o protegido e não o envie ao GitHub.

## 3. Instale as dependências (uma vez)

Abra a pasta do projeto no VS Code, abra um **outro terminal** e execute:

```powershell
python -m pip install -r requirements.txt
```

Se `python` não for reconhecido, instale/configure o Python no PATH e reabra o VS Code.

## 4. Login + execução

Na janela Chrome aberta pelo CMD, acesse o portal Santander, informe seu login e senha, faça o 2FA normalmente. Você pode iniciar o Python antes ou depois de concluir o login, **mas a janela do CMD precisa estar aberta antes de executar o Python**.

No terminal do VS Code, dentro da pasta do projeto, execute:

```powershell
python main.py --limite 1
```

Depois de validar o fluxo autorizado, execute `python main.py` para percorrer **a lista inteira desde o primeiro CPF**, inclusive os já consultados em outras execuções. A opção `--limite N` restringe a quantidade apenas da execução atual. Cada início gera **outro CSV**, sem sobrescrever o anterior.

A automação:

1. Solicita apenas **Código do convênio** no terminal.
2. Verifica se a porta local 9222 está ativa. Se o login redirecionar para outro domínio, espera voltar ao Santander depois do 2FA.
3. Anexa o Selenium **ao Chrome já aberto**. Não cria outra janela.
4. Aguarda até **5 minutos para detectar o login + 2FA**. Caso não consiga detectar a tela autenticada, encerra **a janela de Chrome dedicada** e sai, sem consultar CPFs. O tempo é contado a partir da conexão do Python (não da abertura do CMD).
5. Ao detectar login, mostra: `Login identificado no portal.` e aguarda **ENTER** no terminal (sem limite de 5 minutos depois da detecção).
6. Só após o ENTER consulta os CPFs. **Se você já estiver na tela de consulta (campo Nome visível), o programa começa a preencher ali mesmo sem clicar no menu e sem trocar a URL.** Para voltar a consultar o próximo CPF, ele pode clicar no menu `Produtos` quando necessário. Em seguida utiliza `Ver produtos`, `Simular`, `Seguir sem consulta SRCC`, `Simular proposta`, `Código do convênio`, `Buscar`.
7. Ao iniciar, cria um arquivo exclusivo em `resultados/resultado_margens_DATA_HORA_ID.csv`; após **cada cliente**, atualiza esse CSV com `nome;cpf;margem;status`. O histórico não altera a lista de clientes desta execução.

**NUNCA há `driver.get()`, `driver.refresh()` ou carregamento automático de outra URL dentro do fluxo de consultas.** A única abertura automática de endereço ocorre no `abrir_chrome.cmd`, ao iniciar o navegador *antes* do login. Depois que o Chrome estiver aberto, alterações de página são feitas somente pelos cliques nos elementos reais do portal. O programa fixa a aba da sessão ao reconhecer o login; ele não seleciona outra aba a cada cliente.

Se, ao pressionar ENTER, não encontrar o formulário nem o menu Produtos, o script **para sem redirecionar e sem marcar o CPF atual como ERRO**. Se você deseja começar exatamente na tela de consulta, navegue manualmente até ela, mantenha-a aberta e pressione ENTER no terminal.

Na finalização normal, o Selenium se desconecta; o Chrome iniciado pelo CMD pode permanecer aberto. Feche a janela manualmente após terminar para encerrar a sessão de depuração.

## 5. Arquivos e configurações

| Arquivo | Uso |
|---|---|
| `abrir_chrome.cmd` | Abre o **Chrome correto** com porta 9222 e perfil isolado, no CMD |
| `conexao_chrome.py` | Conecta ao Chrome **já aberto**, sem criar navegador **e sem injetar scripts de modificação de propriedades** |
| `main.py` | Login manual, timeout, ENTER, consulta dos CPFs com `send_keys()` / cliques nativos e tratamento de erros |
| `dados.py` | Lê clientes e atualiza CSV a cada consulta |
| `cpf_nome.txt` | Lista com CPF e nome separados por vírgula; **copiar do seu projeto original** |
| `resultados/resultado_margens_*.csv` | Arquivo novo por execução, separado por ponto e vírgula; criado automaticamente e atualizado após cada cliente |
| `requirements.txt` | Dependências |
| `.gitignore` | Protege credenciais e dados de clientes contra commits por engano |

O arquivo `.env` **não é usado**. No início de `main.py` você pode alterar:

```python
CELULAR = "51998554621"
TEMPO_ESPERA = 35
LIMITE_LOGIN = 300
SALVAR_DIAGNOSTICO = False
LIMITE_ERROS_SEGUIDOS = 5
```

**HEADLESS não se aplica a este fluxo:** o Chrome deve ser aberto visivelmente pelo CMD para permitir o login/2FA.

## 6. Formato do TXT e CSV

Por segurança, o ZIP atualizado não redistribui os dados pessoais recebidos. Copie seu `cpf_nome.txt` do projeto anterior para a pasta atual (ou mantenha o arquivo existente no local ao atualizar). Formato (`CPF,NOME`):

```text
CPF,NOME
00000000000,NOME EXEMPLO
00000000001,OUTRO EXEMPLO
```

**Números acima são exemplos fictícios de formato.** O programa também aceita `NOME,CPF`, não exige pontuação no CPF e elimina CPFs repetidos.

A saída tem exatamente as colunas:

```csv
nome;cpf;margem;status
```

- Margem positiva identificada: valor do campo com `OK`.
- Sem margem/erro/tempo esgotado: margem `0` e status `ERRO`.
- Cada execução gera um **novo CSV** na pasta `resultados/`; ele é atualizado de forma atômica após cada CPF. CSVs anteriores não são reabertos nem modificados.
- Reiniciar `python main.py` inicia novamente **no primeiro CPF do arquivo TXT**; nenhum CPF é ignorado por constar em CSV antigo.
- Para definir onde começar sem editar a lista, use `python main.py --inicio 351` (começa na 351ª linha válida, contando de 1) ou `python main.py --cpf-inicial 00000000001` (inclui este CPF e os seguintes). As duas opções são alternativas.
- Faça o primeiro teste com `python main.py --limite 1`. Esse CPF será consultado novamente no próximo `python main.py`, por se tratar de outra execução independente.
- CPFs pulados por timeout não são registrados como margem obtida; nesta versão eles poderão ser consultados novamente em nova execução.
- **Falhas técnicas** interrompem a execução sem registrar falsos `ERRO`. **Cinco retornos `ERRO` consecutivos** pausam a rotina para revisão da tela/convênio, evitando processamento em massa diante de falha sistêmica.
- Não abra o CSV no Excel enquanto o programa estiver executando: o arquivo pode ficar bloqueado no Windows. Ao importar, trate CPF como texto para manter zeros à esquerda.

**Atenção ao substituir o projeto:** faça backup do seu antigo `resultado_margens.csv` e dos CSVs da pasta `resultados/`. O antigo CSV não é lido nem apagado. Se desejar iniciar em determinado cliente, use `--inicio N` ou `--cpf-inicial CPF`. A opção `--verificar` apenas valida o TXT e não gera um CSV.

## 7. Testes sem entrar no Santander

```powershell
python main.py --verificar
python -m unittest discover -s tests -v
```

O primeiro valida o TXT sem conectar ao Chrome. O segundo testa a leitura/gravação e o código de conexão em simulação, sem acesso ao site.

## 8. Solução de problemas

**Erro `Não encontrei o Google Chrome com depuração na porta 9222`:** abra `abrir_chrome.cmd` primeiro. No mesmo computador, visite `http://127.0.0.1:9222/json/version` para confirmar que aparece um JSON sobre o Chrome. Se não aparecer, feche as janelas desse perfil e execute novamente o CMD; verifique se a porta não está ocupada.

**Não detectou aba do Santander:** confira se a autenticação terminou e voltou ao portal na janela aberta pelo CMD (não no Chrome pessoal). Para maior previsibilidade, mantenha apenas uma aba aberta no perfil dedicado. O programa seleciona a aba do Santander uma vez ao se conectar e aguarda o formulário/menu autenticado nela, durante até 5 minutos. Não altera a URL nem recarrega a aba.

**O Chrome abriu, mas o Selenium não conecta:** confirme que Chrome e ChromeDriver estão compatíveis, atualize Selenium e verifique se alguma ferramenta de segurança bloqueia conexões locais. Com versões atuais, `webdriver.Chrome(options=...)` costuma usar Selenium Manager para configurar o driver.

**O login funciona, mas o Python não reconhece:** a aplicação pode ter mudado o menu Produtos ou a tela de consulta. Atualize os XPaths `produtos_menu` e `nome` em `main.py`, usando a tela autenticada como referência. O Python não deve apertar ENTER sem identificar o login.

**Após ENTER, foi para a tela inicial de login:** nas versões antigas do `main.py`, uma chamada `driver.get(URL_PORTAL)` podia causar isso. Esta versão corrigida não possui navegação direta, nem no primeiro CPF nem nos seguintes. Substitua também `conexao_chrome.py` para que a seleção inicial priorize a aba atual. Confira se está executando os arquivos da pasta nova, e não uma cópia antiga do repositório.

**Abre o menu Produtos mesmo com a tela correta pronta:** esse era outro problema da versão antiga. Nesta versão, o campo Nome é conferido antes de qualquer clique; se o formulário já está aberto, o clique no menu é dispensado.

**Todos os clientes retornam ERRO:** pode ser alteração dos XPaths, indisponibilidade do convênio, mensagens adicionais do banco ou ausência real de margem. Pare e valide com um cliente autorizado antes de processar a lista inteira. Não confunda erro técnico com margem indisponível.

**Operação não suportada via depuração remota:** algumas operações do ChromeDriver (por exemplo, redimensionar a janela) não são suportadas quando o Selenium se conecta a um Chrome preexistente. Este projeto evita esses comandos, mas componentes externos poderão exigir alterações.

**Privacidade e segurança:** a porta de depuração expõe capacidade de controlar a sessão no computador local. Nunca exponha a porta 9222 à internet ou a outras máquinas, nunca compartilhe a pasta de perfil, não comite `cpf_nome.txt`, `.env`, a pasta `resultados/`, `resultado_margens.csv` nem screenshots. Não execute com perfil pessoal do Chrome. Após uso, feche a janela dedicada.

## Fontes técnicas

- Chrome: [Mudanças nas opções de depuração remota](https://developer.chrome.com/blog/remote-debugging-port?hl=pt-br).
- ChromeDriver: [Conectar a uma sessão existente por debuggerAddress](https://developer.chrome.com/docs/chromedriver/help/operation-not-supported-when-using-remote-debugging).


### Atualização do fluxo de Simular e Convênio (v3)
Leia `GUIA_RAPIDO_ATUALIZACAO.md` para o comportamento do botão por texto, espera de 10 segundos, tratamento de pulos sem gravação e pausas de 1 segundo no convênio.


## Ajuste recente — retorno Produtos e redução das pausas (v5)

Ao finalizar cada CPF, o Selenium move o cursor do centro do viewport até a borda esquerda para abrir a sidebar recolhida. Confirma a opção **Produtos** antes de clicar, depois aguarda o formulário inicial. No convênio, as pausas fixas totalizam cerca de 2 segundos, sem contar o carregamento da página e eventuais esperas condicionais. Execute `python main.py --limite 2` para validar a transição entre dois registros.

## Tratamento de timeout de botões (atualização)

Botões de consulta que não ficam clicáveis dentro do prazo não encerram mais o lote: **Ver Produtos**, **Simular** na seleção de produtos, **Simular Proposta** e **Buscar** geram `PularCliente`. O seletor de tipo do convênio também é pulado se não aparecer. **Todo pulo exige retorno confirmado à tela Produtos antes do próximo CPF**. A falta do botão de retorno ou de sessão válida continua interrompendo a execução para evitar misturar dados entre clientes. Ajuste `TEMPO_BOTAO = 10` para os dois botões iniciais; `TEMPO_SIMULAR = 10` controla a localização por texto de Simular Proposta; `TEMPO_ESPERA = 35` controla as demais etapas. **Buscar** também respeita o máximo de 10 s configurado em `TEMPO_BOTAO`.

CPFs pulados não são gravados no CSV desta execução e poderão ser consultados em uma nova execução, pois ausência de botão não prova indisponibilidade de produto. Nenhum bloqueio do portal deve ser contornado pela automação.

## Execuções independentes (atualização mais recente)

Em `python main.py`, **nunca há retomada automática por CSV**. Cada início considera o conteúdo atual de `cpf_nome.txt` desde o primeiro CPF, salvo se você indicar `--inicio` ou `--cpf-inicial`. Nenhum arquivo antigo é apagado. Os CSVs são gravados em `resultados/` com data, hora e identificador no nome. A gravação acontece após cada consulta concluída; se interromper no meio, o CSV parcial daquela execução permanece disponível.

```powershell
python main.py                           # Todos os CPFs, desde o primeiro
python main.py --inicio 350              # Do 350º cliente até o final
python main.py --cpf-inicial 00000000001 # Do CPF indicado até o final
python main.py --inicio 350 --limite 10  # Apenas dez, começando no 350º
python main.py --verificar               # Valida o TXT; não cria CSV
```

**Modo API da VPS é diferente:** `uvicorn api_santander:app` não processa o TXT automaticamente ao iniciar. O n8n deve enviar um novo POST para cada execução desejada. Cada chamada cria um ID próprio, desde que você não repita uma `Idempotency-Key` já utilizada; o armazenamento da API permanece separado, em SQLite, para rastrear as consultas.
