# 💬 Padronizador de Mensagens WhatsApp + IA

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![SemVer 2.0.0](https://img.shields.io/badge/semver-2.0.0-blue.svg)](https://semver.org/)
[![OpenRouter Free](https://img.shields.io/badge/AI-OpenRouter%20Free%20Models-10B981.svg)](https://openrouter.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero%20(stdlib)-brightgreen.svg)](https://docs.python.org/3/library/)

Um aplicativo desktop moderno e intuitivo para padronizar, preencher e enviar mensagens comerciais no WhatsApp, turbinado com **modelos gratuitos de Inteligência Artificial do OpenRouter** e **Auto-Update em tempo real**.

---

## 🌟 Principais Recursos

- 🖱️ **Interface Gráfica Amigável e Moderna**: Desenvolvida com `tkinter` e `ttk`, com interação 100% via mouse e visual inspirado no WhatsApp Web.
- 🤖 **Auto-Preenchimento Inteligente (*Smart Auto-Fill*)**: Cole qualquer mensagem de cliente ou anotação desestruturada; a IA identifica e preenche todas as variáveis dinamicamente.
- 🔍 **Detecção Automática de Variáveis no Editor**: Digite ou cole qualquer texto comum de mensagem e clique em **"🔍 Detectar Variáveis com IA"** para que a IA crie as tags `{cliente}`, `{data}`, `{valor}` e sugira um título automaticamente!
- 🎭 **Adaptador de Tom (*Tone Switcher*)**: Alterne o tom da mensagem com 1 clique:
  - 👔 **Mais Formal**
  - 😊 **Mais Amigável**
  - ⏳ **Cobrança Suave**
  - ⚡ **Direto ao Ponto**
- 📱 **Prévia em Tempo Real (WhatsApp Bubble)**: Veja o balão verde do WhatsApp se atualizar a cada tecla digitada.
- 📋 **Cópia em 1 Clique & Envio Direto**: Botão de cópia rápida para a área de transferência (`Ctrl + V`) e opção de abrir diretamente o WhatsApp Web/App com o número do destinatário.
- 🔄 **Auto-Update em Tempo Real (In-App)**: Quando o autor atualizar o repositório no GitHub, quem estiver com o app aberto é notificado e pode atualizar com 1 clique sem fechar o programa e **sem perder seus templates ou chaves**.
- 📦 **Zero Dependências Externas**: Utiliza apenas módulos da biblioteca padrão do Python (`tkinter`, `json`, `re`, `urllib`, `threading`). Não requer `pip install`!

---

## 🚀 Como Executar

### Pré-requisitos
- **Python 3.10 ou superior** instalado no Windows (com a opção *"Add Python to PATH"* marcada na instalação).

### Passo a Passo:
1. Baixe ou clone este repositório:
   ```bash
   git clone https://github.com/jvrtdev/whatsapp-template-generator.git
   cd whatsapp-template-generator
   ```
2. Inicie o aplicativo:
   - **Opção 1 (Recomendada)**: Dê um duplo clique no arquivo `Iniciar_Gerador_WhatsApp.bat` (não abre tela preta de terminal!).
   - **Opção 2**: Execute via terminal:
     ```bash
     python whatsapp_templates_gui.py
     ```

---

## 🔑 Configuração da Inteligência Artificial (OpenRouter Gratuito)

O aplicativo utiliza modelos de ponta gratuitos do **OpenRouter** (sufixo `:free`):
- `meta-llama/llama-3.3-70b-instruct:free` (Padrão recomendado)
- `google/gemini-2.0-flash-exp:free`
- `deepseek/deepseek-r1:free`
- `qwen/qwen-2.5-coder-32b-instruct:free`

### Como configurar em 1 minuto:
1. Acesse [openrouter.ai/keys](https://openrouter.ai/keys) e gere uma chave de API gratuita.
2. No aplicativo, clique no botão **"⚙️ Configurar IA"** no cabeçalho superior.
3. Cole sua chave e clique em **"🔌 Testar Conexão"**.
4. Clique em **"Salvar Configurações"**. A chave fica salva localmente no seu computador em `config.json` e nunca é enviada ao GitHub.

---

## 🔄 Sistema de Atualização Automática (SemVer)

O projeto segue as diretrizes do [Versionamento Semântico (SemVer)](https://semver.org/lang/pt-BR/) no formato `vMAJOR.MINOR.PATCH`:
- **MAJOR**: Alterações incompatíveis de grande porte.
- **MINOR**: Novas funcionalidades compatíveis com versões anteriores.
- **PATCH**: Correções de bugs e pequenas melhorias.

Ao iniciar o programa, ele verifica silenciosamente em segundo plano se há uma nova versão no GitHub. Caso haja, uma janela amigável exibe o que mudou e permite baixar e reiniciar com 1 clique!

---

## 📂 Estrutura do Projeto

```
whatsapp-template-generator/
│
├── Iniciar_Gerador_WhatsApp.bat   # Inicializador Windows (sem console preto)
├── whatsapp_templates_gui.py      # Aplicação desktop principal (GUI Tkinter)
├── ai_service.py                  # Integração com IA OpenRouter (urllib nativo)
├── updater.py                     # Sistema de Auto-Update assíncrono (SemVer)
├── version.py                     # Versão semântica oficial (__version__)
├── version.json                   # Manifesto remoto de atualização
├── templates.json                 # Banco de dados local de templates
├── config.json                    # Configurações do usuário (ignorado no git)
├── .gitignore                     # Proteção contra commit de chaves e caches
├── LICENSE                        # Licença MIT
└── README.md                      # Documentação do projeto
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Veja [LICENSE](LICENSE) para mais informações.
