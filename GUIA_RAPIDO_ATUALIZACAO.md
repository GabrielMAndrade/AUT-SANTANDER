# Alterações — Selenium sem scripts de modificação do navegador

## Como atualizar sem perder dados

1. Faça backup do projeto original, especialmente de `cpf_nome.txt` e `resultado_margens.csv`.
2. Descompacte este ZIP em uma **nova pasta**.
3. Copie `cpf_nome.txt`. Guarde o `resultado_margens.csv` anterior apenas como histórico: o código não o utiliza mais para pular CPFs. Os novos CSVs ficam na pasta `resultados/`.
4. Abra `main.py` e confira `CELULAR`, `TEMPO_ESPERA` e `LIMITE_ERROS_SEGUIDOS`. Não há mais opção `REPROCESSAR_ERROS` no fluxo por TXT.
5. Ajuste os XPaths do dicionário `XP` somente se os elementos no portal tiverem mudado. Não altere XPaths sem verificar a tela real.
6. Instale as dependências: `python -m pip install -r requirements.txt`.
7. Abra `abrir_chrome.cmd`, faça login e o segundo fator **manualmente**.
8. Em outro terminal, teste `python main.py --verificar` e então `python main.py --limite 1`.
9. Verifique o resultado do primeiro cliente no portal e no CSV. Ao executar novamente `python main.py`, **a lista recomeça no primeiro CPF**, com outro CSV. Para seguir de outra posição, use `--inicio N` ou `--cpf-inicial CPF`.

## O que mudou

- `conexao_chrome.py`: removida a chamada `Page.addScriptToEvaluateOnNewDocument` que modificava objetos do navegador. A conexão com Chrome aberto no endereço local `127.0.0.1:9222` continua.
- `main.py`: cliques feitos por WebDriver/ActionChains, sem `arguments[0].click()` via JavaScript; preenchimento com `send_keys()` e `TAB`, verificando o valor que ficou no campo (CPF/telefone podem ter máscara).
- `main.py`: falha técnica ou campo não confirmado interrompe a execução **sem salvar `ERRO` para o cliente**; o CSV `nome;cpf;margem;status` permanece compatível.
- `main.py`: após 5 resultados `ERRO` seguidos, interrompe para investigação. Ajustável pela constante `LIMITE_ERROS_SEGUIDOS`.
- `main.py`: nova opção `--limite N` para teste seguro antes de passar à lista toda.

## O que **não** mudou

- Não há robôs externos de clique nem macros `.exe` no projeto original analisado.
- A autenticação e o 2FA continuam manuais. O navegador é iniciado pelo `.cmd` com perfil próprio.
- A navegação após login ocorre por botões do site; não há navegação por URLs diretas ou refresh no ciclo.
- O CSV é atualizado após cada consulta completada, preservando resultados existentes na pasta.
- **Não há mecanismo para esconder a automação**. `send_keys()` permite ao site receber entradas e eventos comuns, mas não impede identificação do WebDriver.

## Arquivos não incluídos no ZIP

Não são redistribuídos: `cpf_nome.txt` (CPFs e nomes reais), `resultado_margens.csv`, `.env`, diretório `.git`, perfis de navegador e screenshots. Recupere os dados do seu projeto anterior quando necessário. O `.env` não é utilizado pelo script atual.

## Testes

```powershell
python -m unittest discover -s tests -v
python main.py --verificar
python main.py --limite 1
```

Não foi possível validar a interação real com o portal Santander sem uma sessão autenticada; os XPaths continuam os originais enviados.

## Correção adicional: botão Simular (tela csg-home)

O XPath fornecido para o botão **Simular** foi preservado em
`XP["simular_proposta"]`. Após selecionar o produto, o robô agora chama
`avancar_ate_convenio()` para:

1. Reconhecer e tratar o diálogo SRCC, quando exibido.
2. Aguardar e clicar o botão **Simular** de `csg-home` por Selenium.
3. Confirmar que o dropdown de convênio apareceu antes de pesquisar o código.
4. Interromper a execução sem registrar o CPF como ERRO se a navegação falhar.

O terminal informa `[Simular] clicando...` e `[Simular] tela de convênio confirmada.`
Não é necessário alterar os XPaths para essa correção se a página mantiver sua estrutura atual.

**Teste inicial:** execute `python main.py --limite 1` e verifique essas mensagens no terminal.
Se a tela não avançar, verifique se o XPath corresponde ao botão visível na sessão autenticada.


## Versão 3 — Botão por texto e dropdown do convênio

- Na etapa `csg-home`, encontra o botão pelo texto visível `Simular Proposta` (ou `Simular`), `aria-label` ou `title` dentro do componente, sem XPath absoluto. Espera até **10 segundos** para localizá-lo. Se não aparecer, deixa o CPF pendente no CSV e tenta iniciar o próximo pelo menu Produtos. Depois de **3 pulos consecutivos**, interrompe a execução para evitar repetir uma falha sistêmica.
- No dropdown de busca, escolhe `Código do convênio` pelo **texto do item**, clicando no ancestral interativo `<a>` em vez do `<option>` aninhado. Confirma seleção e fechamento antes de digitar. Se o menu persistir aberto, tenta ESC uma vez; caso continue aberto ou a seleção não se confirme, para sem gravar ERRO.
- Aplica pausas de **1 segundo entre todas as ações da janela de convênio** (abrir, selecionar, focar, limpar, preencher, TAB, buscar). Não existem macros externas.
- O botão `Buscar` é procurado primeiro pelo texto no formulário, com XPath antigo como reserva.
- `TEMPO_SIMULAR`, `INTERVALO_CONVENIO` e `LIMITE_PULOS_SEGUIDOS` ficam no topo de `main.py`.

**Caso pare na seleção de Código do convênio:** envie a captura/HTML do componente `dss-dropdown` **depois de clicar na opção**, com CPF, tokens e demais dados removidos. O sistema pode ter rótulos ou comportamentos diferentes, não verificáveis sem a sessão do Santander.

## Versão 4 — 5 segundos antes de Simular Proposta e retorno obrigatório

**Novo comportamento da consulta**

1. O Selenium identifica o botão **Simular Proposta** pelo texto, aguardando até 10 segundos para o botão aparecer.
2. Quando aparece, espera **5 segundos completos** (`DELAY_ANTES_SIMULAR = 5.0`). Depois procura o botão outra vez no DOM, porque a aplicação pode recriá-lo, e só então clica.
3. Conclui a pesquisa do convênio e tenta ler a margem. Os atrasos de **1 segundo** na tela de convênio foram preservados.
4. Seja margem encontrada, status ERRO, Simular indisponível ou falha de consulta, **sempre tenta voltar pelo menu lateral Produtos**, sem alterar a URL diretamente.
5. Aguarda o formulário de nome, CPF e celular aparecer antes de iniciar o CPF seguinte. Se esse retorno falhar, interrompe a execução para não misturar dados de clientes.

**Configurações no topo de `main.py`:**

- `DELAY_ANTES_SIMULAR = 5.0` — tempo de espera fixo antes do clique.
- `TEMPO_SIMULAR = 10` — máximo de segundos para achar o botão pelo texto.
- `TEMPO_ESPERA = 35` — máximo para carregar margem, voltar a Produtos etc.
- `LIMITE_PULOS_SEGUIDOS = 0` e `LIMITE_ERROS_SEGUIDOS = 0` — zero significa **não interromper por contagem** de CPFs sem botão/sem margem. Uma falha técnica ou falha no retorno a Produtos continua interrompendo imediatamente.

**Terminal esperado:**

```text
[Simular] localizado. Aguardando 5 segundos antes do clique...
[Simular] botão estável e habilitado. Clicando...
[Simular] formulário de convênio confirmado.
...
[Produtos] retornando ao menu Produtos...
[Produtos] tela inicial confirmada. Próximo CPF liberado.
```

**Testar inicialmente:** `python main.py --limite 2` com CPFs autorizados. No CSV, o CPF pulado por indisponibilidade de Simular continuará pendente (não será salvo como ERRO). Se não aparecer a mensagem de Produtos, o XPath do menu pode ter mudado: envie o HTML do item lateral Produtos com dados privados removidos.

**Validação:** os testes locais utilizam mocks e não fazem requisições ao portal; uma sessão autenticada será necessária para confirmar o funcionamento real.


## Versão 5 — sidebar por hover e convênio mais rápido

- **Produtos:** antes de procurar o item, Selenium move o ponteiro da metade da janela para `(2, metade da altura)`; aguarda até 8 s para o menu aparecer, clica em **Produtos** e confirma que o formulário de Nome/CPF/Celular reapareceu. Se não confirmar, não inicia o próximo CPF.
- **Convênio:** substituídas as pausas de 1 s após cada tecla por **cinco pausas de 0,4 s**, somando aproximadamente **2 segundos fixos** durante o fluxo normal. Esperas condicionais para dropdown e confirmação do valor continuam existindo.
- **Simular Proposta:** preservada a espera de **5 segundos** antes do clique.
- Não há uso de headless, alteração de propriedades do navegador ou scripts para ocultar Selenium.

**Teste recomendado:** após autenticação manual, execute `python main.py --limite 2` e confirme que a sidebar abriu ao término do primeiro CPF e que o segundo começa no formulário correto.

## Timeout de botões: seguir para o próximo CPF

- `TEMPO_BOTAO = 10` no `main.py` limita a espera para **Ver Produtos** e **Simular (seleção do produto)**. Se um deles não aparecer ou permanecer desabilitado, o CPF é **PULADO**, sem gravar `ERRO` no CSV desta execução.
- O botão **Simular Proposta** mantém a busca por texto (10 s), com atraso de 5 s antes do clique, e também pula o CPF se não ficar disponível.
- O botão **Buscar** passa a pular após no máximo 10 s; o seletor do convênio também pula o CPF se não aparecer durante a espera da etapa.
- Depois de um pulo, o robô **tenta voltar ao menu Produtos**, com hover na lateral, e só então inicia o próximo CPF. Se o retorno falhar, **interrompe** para não misturar clientes.
- O CPF pulado fica **pendente** para outra execução, porque timeout de botão **não comprova** que o produto é realmente indisponível. O terminal mostra a etapa ausente.
- A pausa de 5 s antes de **Simular Proposta** e as pausas totais de aproximadamente 2 s no convênio foram preservadas.

Teste recomendado: `python main.py --limite 2` após abrir o Chrome e concluir o login manual. O primeiro CPF pode ser pulado; o robô deve retornar a Produtos e iniciar o segundo. Consulte apenas clientes para os quais exista autorização.

## Atualização: novo CSV e início manual da lista

O programa **não usa o CSV de execuções anteriores** para decidir quais clientes consultar. Cada `python main.py` cria um `resultados/resultado_margens_*.csv` novo e começa do início do `cpf_nome.txt`, inclusive se você acabou de fazer um teste `--limite 1`. Os CSVs anteriores permanecem disponíveis para conferência; nenhum é reescrito. O CSV novo é salvo após cada cliente com resultado, mesmo em execução parcial.

```powershell
python main.py                        # lista inteira
python main.py --inicio 300           # começa pelo 300º CPF válido do TXT
python main.py --cpf-inicial 00000000001  # começa pelo CPF indicado
python main.py --inicio 300 --limite 2    # consulta apenas duas posições
```

No **modo API da VPS**, reiniciar o servidor não percorre `cpf_nome.txt`: cada envio do n8n é independente e possui ID próprio na fila SQLite. Para criar outra consulta, envie outro POST, usando uma chave de idempotência diferente caso esse cabeçalho seja utilizado.
