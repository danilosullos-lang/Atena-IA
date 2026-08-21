# Worker persistente do Telegram da Atena

## Diagnóstico

O workflow `ATENA CI and controlled updates` executava `scripts/atena_telegram_chat.py` em background durante apenas 300 segundos. Ao terminar o job, o processo era encerrado. Além disso, iniciar long polling no GitHub Actions enquanto outro processo estivesse ativo poderia produzir o erro `Conflict: terminated by other getUpdates request`, pois o Telegram permite apenas um consumidor de `getUpdates` por bot.

O Vercel não é o destino apropriado para esse processo: Functions são executadas sob demanda e não devem manter um loop Python de long polling indefinidamente. Os checks do Vercel vistos no repositório também apresentaram `build-rate-limit`; isso é um limite de build/deploy e não prova que exista um bot persistente ativo.

## Render

O arquivo `render.yaml` define um **Background Worker** chamado `atena-telegram-worker`. Esse worker executa continuamente:

```bash
python scripts/atena_telegram_chat.py --poll-timeout 25
```

No painel do Render, crie o serviço a partir do Blueprint do repositório e preencha os secrets:

```text
ATENA_TELEGRAM_BOT_TOKEN
ATENA_TELEGRAM_CHAT_ID
ATENA_OLLAMA_CHAT_URL
```

`ATENA_OLLAMA_CHAT_URL` deve apontar para um endpoint Ollama realmente acessível pelo worker. `127.0.0.1` no Render aponta para o próprio container, portanto não funcionará se o Ollama estiver em outro computador. O token nunca deve ser colocado no Git.

O worker usa o long polling contínuo e reinicia conforme a política da plataforma quando o processo encerra. Não é necessário abrir uma porta HTTP para um Background Worker.

## GitHub Actions

O workflow agendado continua responsável pelo ciclo de aprendizagem e pelas notificações HTTP, mas deixou de iniciar um segundo consumidor de `getUpdates` por cinco minutos. Dessa forma, o worker persistente é o único processo responsável por responder mensagens interativas no Telegram.

## Verificação operacional

Depois de configurar o serviço, confirme no log do Render:

```text
ponte Telegram iniciada; modelo=qwen2.5:3b-instruct
```

E teste no Telegram:

```text
/status
```

Se houver `Conflict: terminated by other getUpdates request`, procure outro serviço, execução manual ou job do GitHub Actions que ainda esteja rodando `atena_telegram_chat.py` e desligue-o. Apenas uma instância deve usar long polling.

## Limites

O worker mantém a Atena disponível para conversar e processar comandos autorizados, mas não transforma qualquer mensagem em ação irrestrita. A allowlist, as confirmações para ações sensíveis, o sandbox e os gates de código continuam obrigatórios. Para acessar Ollama local, Android/Tasker ou arquivos privados, o endpoint precisa estar acessível de forma segura; não se deve expor uma porta Ollama pública sem autenticação e firewall.
