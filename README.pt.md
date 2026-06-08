# Ditoo Pro × Claude Code — mascote de status ao vivo

🌐 [English](README.md) · [Español](README.es.md)

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-Ventura+-000000?logo=apple&logoColor=white)
![Bluetooth](https://img.shields.io/badge/Bluetooth-Classic%20RFCOMM-0082FC?logo=bluetooth&logoColor=white)
![Claude Code](https://img.shields.io/badge/Claude_Code-hooks-D4A574?logo=anthropic&logoColor=white)
![Divoom](https://img.shields.io/badge/Divoom-Ditoo_Pro-FF6B35?logoColor=white)

Seu **Divoom Ditoo Pro** vira um mascote em tempo real enquanto você trabalha com o Claude Code.  
Ele mostra o que o Claude está fazendo — pensando, escrevendo, esperando — e volta ao seu relógio normal no momento em que você fecha a sessão, liberando o dispositivo como caixa de som Bluetooth do seu Mac.

![demo](demo.gif)

---

## Como fica

| Enquanto o Claude está… | O Ditoo mostra |
|-------------------------|----------------|
| Aguardando seu próximo prompt | criatura laranja, piscada ocasional |
| Pensando | pontinhos de pensamento girando acima |
| Usando uma ferramenta / escrevendo uma resposta | olhando para baixo + cursor piscando |
| Pronto com uma resposta | olhos `^^` felizes + check verde |
| Sem sessão aberta | seu relógio normal |

---

## O que você precisa

- **Divoom Ditoo Pro** (o display de pixels, não outros modelos Divoom)
- **Mac** com macOS Ventura 13 ou posterior
- **Claude Code** instalado e funcionando (`claude --version` deve responder)
- **Python 3** — já vem em todos os Macs, nada extra para instalar

---

## Instalação — 5 passos

### Passo 1 — Pareie o Ditoo Pro com o seu Mac

Abra **Configurações do Sistema → Bluetooth**, encontre `DitooPro-Audio` e conecte.  
Deixe conectado durante o restante da configuração.

---

### Passo 2 — Encontre o endereço MAC Bluetooth do Ditoo

Execute isso no Terminal:

```sh
system_profiler SPBluetoothDataType | grep -A8 -i ditoo
```

Procure a linha `Address:`. Vai parecer algo como `B1:21:81:8C:C0:B5`.  
Anote — você vai usá-lo exatamente como aparece no próximo passo.

---

### Passo 3 — Clone e faça o deploy

```sh
git clone https://github.com/linuxshark/Divoom-Ditto-Pro-Claude-Code.git
cd Divoom-Ditto-Pro-Claude-Code
sh tools/deploy.sh
```

Isso copia tudo para `~/.ditoo` e cria um ambiente virtual Python lá.  
Instala fora de `~/Documents` para evitar as restrições de privacidade do macOS.

---

### Passo 4 — Configure o endereço MAC do seu dispositivo

Adicione esta linha ao seu `~/.zshrc` (ou `~/.bash_profile` se usar bash):

```sh
export DITOO_MAC=B1:21:81:8C:C0:B5   # ← cole seu endereço do Passo 2, qualquer formato funciona
```

Depois recarregue o shell:

```sh
source ~/.zshrc
```

---

### Passo 5 — Adicione os hooks do Claude Code

Abra `~/.claude/settings.json` em qualquer editor de texto e adicione o bloco `"hooks"` abaixo.  
Se você já tem hooks para outras ferramentas, **mescle** as chaves — não substitua o objeto `"hooks"` inteiro.

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py start", "timeout": 3 }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py end", "timeout": 3 }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py thinking", "timeout": 3 }] }
    ],
    "PreToolUse": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py thinking", "timeout": 3 }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py writing", "timeout": 3 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py done", "timeout": 3 }] }
    ]
  }
}
```

**Pronto.** Abra uma sessão do Claude Code — o mascote aparece. Feche — seu relógio volta.

---

## Uma nota sobre o áudio Bluetooth

O macOS não consegue usar RFCOMM (o canal do display) e A2DP (áudio Bluetooth) no mesmo dispositivo ao mesmo tempo.  
Enquanto há uma sessão do Claude Code ativa, o Ditoo não fica disponível como caixa de som do Mac.  
No momento em que você fecha a sessão, o daemon libera o canal e seu relógio (e o áudio) voltam automaticamente.

---

## Solução de problemas

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| Nada acontece ao iniciar sessão | Hooks não adicionados | Verifique o Passo 5 — confira `~/.claude/settings.json` |
| O Ditoo mostra o relógio errado | `DITOO_MAC` não configurado ou incorreto | Revise o Passo 4, execute `echo $DITOO_MAC` em um terminal novo |
| O daemon inicia mas a tela fica em branco | Ditoo não conectado via BT | Abra o Bluetooth e reconecte |
| O relógio não volta após a sessão | Daemon ainda rodando de sessão anterior | `pkill -TERM -f "ditoo/daemon.py"` |
| Erro de permissão Bluetooth | Primeira execução precisa de contexto de terminal | Sempre inicie o Claude Code pelo Terminal, não pelo Spotlight ou Finder |

---

<details>
<summary>⚙️ Detalhes técnicos — arquitetura, protocolo, notas de hardware, personalização, testes</summary>

## Como funciona

```
Hooks do Claude Code ──(JSON em /tmp/ditoo.sock)──> daemon ──(RFCOMM/SPP)──> Ditoo Pro
```

- `hooks/notify.py` é invocado por cada hook do Claude Code com um nome de estado. Ele
  envia uma linha JSON ao socket Unix do daemon e, se o daemon não estiver rodando, o
  **inicia automaticamente** (veja a nota de Bluetooth abaixo).
- `daemon.py` controla a conexão Bluetooth. A **thread principal** roda o CFRunLoop do
  IOBluetooth e mantém o canal RFCOMM; uma thread em segundo plano atende o socket Unix.
  Conta as sessões ativas, mostra o mascote enquanto houver alguma aberta e volta ao relógio
  quando não restam mais.
- `divoom_proto.py` — codificador de protocolo puro (imagens de paleta, animações, o
  comando `SET_VIEW` do relógio). `pixels_loader.py` carrega a arte `pixels/*.json` em
  pacotes prontos para enviar. `transport.py` — o transporte RFCOMM IOBluetooth para macOS
  (+ um `MockTransport` para testes).

### Módulos

| Arquivo | Função |
|---------|--------|
| `divoom_proto.py` | Codificador de protocolo wire puro (sem I/O) |
| `transport.py` | Transporte RFCOMM IOBluetooth para macOS + mock |
| `pixels_loader.py` | `pixels/*.json` → pacotes codificados |
| `daemon.py` | Daemon com sessões (socket + runloop + retorno ao relógio) |
| `hooks/notify.py` | Hook → notificador de socket, iniciador lazy do daemon |
| `tools/gen_art.py` | Gera a arte do mascote (`pixels/*.json`) |
| `tools/png_to_pixels.py` | Converte PNG/GIF para o formato JSON de arte |
| `tools/deploy.sh` | Faz deploy do runtime autônomo em `~/.ditoo` |

### Refazer o deploy após mudanças

Após editar código ou regenerar arte, rode `sh tools/deploy.sh` novamente para atualizar
`~/.ditoo`, depois reinicie o daemon:

```sh
pkill -TERM -f "ditoo/daemon.py"
```

Ele reinicia automaticamente no próximo hook do Claude Code.

### Personalizar a arte do mascote

Edite `tools/gen_art.py` (o mascote é uma grade ASCII em `BODY_ROWS`;
`#` = corpo, `o` = olho, espaço = apagado), rode `python tools/gen_art.py`, depois refaça o deploy.

Ou converta qualquer imagem: `python tools/png_to_pixels.py art.gif thinking 6 > pixels/thinking.json`

### Mudar o relógio para o qual volta

O daemon volta ao **estilo de relógio id 9 em laranja** por padrão. Configure variáveis de
ambiente para mudar:

```sh
export DITOO_CLOCK_ID=9
export DITOO_CLOCK_COLOR=255,120,0  # RGB
```

## Por que não launchd?

Um **LaunchAgent do macOS não tem permissão de Bluetooth** (TCC), e o painel de privacidade
do Bluetooth não permite conceder isso a um binário simples — então um daemon rodado pelo
launchd falha silenciosamente ao abrir RFCOMM. Processos iniciados de um **contexto de
terminal** têm acesso ao Bluetooth, e os hooks do Claude Code rodam nesse contexto. O daemon
é iniciado de forma lazy por `hooks/notify.py` e herda a permissão. Um `flock` singleton
(`/tmp/ditoo.daemon.lock`) garante que apenas um daemon rode independentemente de quantas
sessões ou hooks disparem.

## Notas de hardware

O registro completo de engenharia reversa está em [`spike/NOTES.md`](spike/NOTES.md).
Destaques:

- O transporte é **Bluetooth Classic RFCOMM/SPP** (não BLE), canal 2, somente abertura
  assíncrona. Abertura síncrona retorna `kIOReturnError`.
- IOBluetooth entrega callbacks de RFCOMM **somente no CFRunLoop da thread principal**, e
  uma abertura deve ser iniciada fora de um loop em execução — daí o ciclo start/run_forever.
- `dev.closeConnection()` derruba o link de áudio do macOS para que RFCOMM possa abrir.
- O dispositivo **não** reverte automaticamente quando o canal fecha; voltar ao relógio
  requer um comando `SET_VIEW` (0x45) explícito. O relógio do usuário = estilo id 9, laranja.
- Nunca use SIGKILL no daemon no meio de RFCOMM (trava o servidor SPP do dispositivo;
  para recuperar: desligue e ligue o Ditoo). O daemon sempre fecha o canal limpo ao encerrar.

## Testes

```sh
.venv/bin/python -m pytest -q     # 78 testes, sem hardware necessário
```

`MockTransport` torna o protocolo, o loader e a lógica do daemon totalmente testáveis
sem um dispositivo físico.

</details>
