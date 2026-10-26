# Soma | API do robô Santander (VPS + n8n)

Esta é uma API HTTP **da automação local**, não uma API oficial do Santander. Ela recebe os dados autorizados via JSON, enfileira e realiza consultas sequenciais pela interface do portal usando o Selenium já existente. Uma sessão autenticada e autorizada do banco é obrigatória.

## 1. Instalação / arquivos

O robô por `main.py` funciona como um modo **independente de execução por TXT**: em cada início, consulta a lista novamente e cria um novo CSV em `resultados/`. A API é um modo **adicional**, com os arquivos:

- `api_santander.py`: endpoints HTTP.
- `api_store.py`: fila e resultados em SQLite privado.
- `api_worker.py`: executa uma consulta Selenium por vez.
- `abrir_chrome_vps.sh`: Chrome com interface gráfica virtual, para Linux.
- `.env.example`: modelo de configuração.
- `deploy/`: exemplos de systemd e Nginx.

Não coloque `cpf_nome.txt`, `.env`, banco SQLite ou CSV em repositórios públicos.

**Dependências:** Python 3.10+, Chrome compatível, Selenium e bibliotecas de `requirements.txt`. O servidor HTTP não faz login, não executa 2FA e não ignora bloqueios ou restrições do banco. Confirme a autorização da integração com o Santander e o tratamento dos dados pela LGPD.

### Windows (teste local)

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edite .env: SANTANDER_API_TOKEN e SANTANDER_CELULAR
# Abra abrir_chrome.cmd, acesse o portal e faça login/2FA manualmente.
python -m uvicorn api_santander:app --host 127.0.0.1 --port 6767 --workers 1
```

### Linux (VPS Ubuntu/Debian)

```bash
# Coloque os arquivos do ZIP em /opt/santander, como usuário dedicado.
cd /opt/santander
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
# Edite .env: preencha os campos acima. Token aleatório:
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Para manter o Selenium com os eventos de mouse e com login manual, **use Chrome gráfico numa tela virtual** (Xvfb), em vez de presumir que `headless=True` reproduzirá o portal. Instale `xvfb`, Chrome/Chromium e `x11vnc` opcionalmente. Execute o navegador **com o mesmo usuário Linux do serviço da API**:

```bash
cd /opt/santander
DISPLAY=:99 ./abrir_chrome_vps.sh
```

Para a sessão sobreviver ao fechamento do SSH, execute o navegador em uma sessão `tmux` ou crie um serviço gráfico dedicado. Não use o navegador com usuário `root` se a API estiver rodando como `santander`.


O script abre Chrome com depuração SOMENTE em `127.0.0.1:9222`. **Nunca** publique 9222 na rede. Para completar login/2FA, conecte-se à tela virtual usando VNC protegido por túnel SSH, ou outro desktop remoto seguro. Não publique VNC sem autenticação. Após login, inicie o servidor em outro terminal ou habilite o serviço `systemd` do diretório `deploy`:

```bash
cd /opt/santander
.venv/bin/uvicorn api_santander:app --host 127.0.0.1 --port 6767 --workers 1
```

Para iniciar o serviço automaticamente, ajuste usuário/caminhos em `deploy/santander-api.service`, copie para `/etc/systemd/system/` e rode `sudo systemctl daemon-reload && sudo systemctl enable --now santander-api`. O Chrome precisa permanecer ativo com a sessão do banco. Se reiniciar a VPS ou expirar a sessão, será necessário autenticar novamente.

**Exposição da API:** preferencialmente publique `https://api.seudominio.com.br` com Nginx e TLS (modelo em `deploy/nginx_santander.conf.example`). O Uvicorn deve continuar escutando em `127.0.0.1:6767`; não exponha `9222`, VNC, `.env` ou SQLite. Se o n8n rodar na mesma máquina mas em Docker, `localhost` dentro do contêiner é o contêiner, não o host; use hostname/rede privada própria ou o domínio HTTPS.

**Importante:** Não execute `python main.py` simultaneamente com a API sobre o mesmo navegador. Execute exatamente **um processo Uvicorn e um worker** (`--workers 1`). Várias instâncias disputariam o mesmo navegador.

## 2. Autenticação

Todas as rotas com dados requerem:

```text
Authorization: Bearer SEU_TOKEN_GERADO_NO_ENV
Content-Type: application/json
```

Só `/health` é pública; a resposta contém apenas dados de vida do serviço. `GET /docs` lista as rotas, mas não revela resultados sem o token. Use token em credencial/variável protegida do n8n, nunca em parâmetros de URL.

## 3. Consulta individual (igual ao padrão Consignet, mas assíncrona)

**POST `https://api.seudominio.com.br/margem_cpf`**

```json
{
  "cpf": "00000000000",
  "nome": "CLIENTE EXEMPLO",
  "convenio": "12345",
  "celular": "51999999999"
}
```

O `nome` é obrigatório porque o próprio portal Santander exige nome, CPF e telefone. `celular` é opcional se `SANTANDER_CELULAR` estiver configurado no `.env`. Não é necessário mandar arquivo TXT para a API.

Resposta imediata **HTTP 202**:

```json
{
  "id": "f9a1f3...",
  "status": "pendente",
  "criado": true,
  "url_resultado": "/consultas/f9a1f3...",
  "total": 1
}
```

A API **não devolve a margem no primeiro POST**. O Selenium precisa carregar telas e o n8n não deve aguardar essa operação numa única requisição.

**GET `/consultas/{id}`** para acompanhamento. Exemplo após processamento:

```json
{
  "id": "f9a1f3...",
  "status": "concluido",
  "convenio": "12345",
  "total": 1,
  "contagem": {"ok": 1},
  "resultados": [
    {"pos": 0, "nome": "CLIENTE EXEMPLO", "cpf": "00000000000",
     "status": "ok", "margem": "250,50", "detalhe": null}
  ]
}
```

Datas `criado_em`, `atualizado_em` e `erro` também são incluídos. Margem demonstrativa, não de cliente real.

## 4. Lote

**POST `/consultas`** (até 100 por lote):

```json
{
  "convenio": "12345",
  "celular": "51999999999",
  "clientes": [
    {"cpf": "00000000000", "nome": "CLIENTE 1"},
    {"cpf": "11111111111", "nome": "CLIENTE 2"}
  ]
}
```

A execução é sequencial: um CPF por vez, e o robô só avança depois de retornar para Produtos. CPF duplicado dentro do mesmo lote retorna HTTP 422.

## 5. Estados do processamento

- `pendente`: aguardando fila.
- `aguardando_sessao`: Chrome da VPS ou sessão autenticada indisponível; após login a fila é retomada automaticamente.
- `processando`: Selenium atuando no portal.
- `concluido`: todos os itens com margem positiva confirmada.
- `concluido_com_pendencias`: há CPFs pulados ou resultado sem margem positiva confirmada.
- `interrompido`: erro de navegação, sessão ou reinício. Confirme o estado do navegador antes de retomar.

Estados por CPF:

- `ok`: margem positiva encontrada.
- `erro_portal`: alerta do portal **ou** valor positivo não localizado no tempo limite. **Não significa necessariamente margem zero**.
- `pulado_timeout`: botão indisponível por timeout. **Não comprova que o produto não existe**.
- `interrompido`: falha técnica/navegação; não executar automaticamente outro CPF até restabelecer o formulário.

Para solicitar retomada explícita de consulta interrompida: `POST /consultas/{id}/retomar`. Isso poderá repetir o CPF em andamento no momento da interrupção; use apenas depois de verificar que a consulta anterior não ficou em processamento no portal.

`GET /status` devolve estado do worker e quantidades por status. `GET /health` indica apenas que a API está online, **não** que Santander está autenticado.

## 6. n8n: configuração de HTTP Request

### Node 1 — Enviar consulta

- Method: `POST`
- URL: `https://api.seudominio.com.br/margem_cpf`
- Headers: `Authorization = Bearer <seu token>`; `Content-Type = application/json`.
- Send Body: JSON:

```javascript
={{ {
  cpf: $json.cpf,
  nome: $json.nome,
  convenio: $json.convenio,
  celular: $json.celular
} }}
```

Se estiver usando a opção "Specify Body: JSON", ajuste a expressão no editor do n8n. **No payload final envie JSON válido**, não literalmente o exemplo JavaScript.

### Node 2 — Verificar resultado

- Method: `GET`
- URL: `https://api.seudominio.com.br/consultas/{{ $json.id }}`
- Header: `Authorization = Bearer <seu token>`.
- Verifique `status` (`processando`, `aguardando_sessao`, `concluido` etc.).
- Quando finalizado, use `resultados[0].margem` se `resultados[0].status == "ok"`.

Se ainda não terminou, use **Wait** no n8n e consulte novamente, com um limite máximo de tentativas. Alternativamente dispare um novo workflow para buscar resultados depois. O POST inicial responde em milissegundos independentemente da duração do Selenium.

**Opcional:** envie header `Idempotency-Key` com identificador único por operação comercial. Reenvios com a mesma chave e mesmo corpo retornam o mesmo `id`, evitando enfileirar novamente por retry do n8n. Mesma chave com dados distintos retorna HTTP 409.

## 7. Testes iniciais

1. Acesse `GET /health` e confirme `{"status":"ok"}`.
2. Faça login no Santander pelo Chrome da VPS, com 2FA, e abra o formulário Produtos.
3. Envie **um CPF de teste autorizado** em `POST /margem_cpf`.
4. Consulte `/consultas/{id}` até terminar.
5. Envie dois CPFs, confirme margem/timeout e se houve retorno a Produtos.
6. Só depois integre o webhook de produção no n8n.

**Não testado no banco real:** a lógica da API e persistência pode ser testada localmente; a automação Selenium depende de portal autenticado e permissões do banco. A API não contorna detecção de automação, restrições do site nem autenticação multifator.

## 8. Proteção de dados

O SQLite `private/consultas.sqlite3` contém nomes, CPFs e margens; dê acesso somente ao usuário do serviço (permissão 600), faça backups protegidos, defina retenção adequada e limite quem tem acesso ao Bearer token. Por padrão, não há limpeza automática. Não exponha logs, capturas do navegador ou arquivos de resultados. Evite consultas em massa sem autorização, consentimento/base legal e respeito às regras do banco.

## Execução por TXT versus API

`python main.py` percorre a lista atual **desde o primeiro CPF** e cria um **CSV novo** na pasta `resultados/` sempre que inicia (exceto `--verificar`). Use `python main.py --inicio 300` ou `--cpf-inicial 00000000001` para começar em outra posição, sem alterar a lista nem o CSV antigo.

A **API** não lê o `cpf_nome.txt` quando o serviço inicia. Ela processa os clientes enviados no corpo do POST e salva um ID por solicitação no SQLite. Reiniciar apenas o serviço **não** refaz as solicitações concluídas. Para uma nova rodada pelo n8n, faça um **novo POST**; se usar `Idempotency-Key`, escolha uma chave nova para essa rodada. Para resultados, consulte `GET /consultas/{id}`. Não execute `python main.py` em paralelo com o worker da API usando o mesmo Chrome.
