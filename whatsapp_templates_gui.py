import os
import sys
import json
import re
import subprocess
import webbrowser
import urllib.parse
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# Controle de Versão e Auto-Updater
from version import __version__, APP_NAME, DEFAULT_GITHUB_REPO
from updater import (
    check_for_updates,
    download_and_apply_update,
    restart_application,
)

# Módulo de IA com modelos gratuitos do OpenRouter
from ai_service import (
    FREE_MODELS,
    test_api_connection,
    extract_variables_from_context,
    adapt_message_tone,
    generate_template_from_prompt,
    detect_and_parametrize_variables,
)

# Caminhos dos arquivos de dados na mesma pasta do script
BASE_DIR = Path(__file__).resolve().parent
STORAGE_FILE = BASE_DIR / "templates.json"
CONFIG_FILE = BASE_DIR / "config.json"


def load_config() -> dict:
    """Carrega as configurações locais (API Key, Modelo do OpenRouter e Repositório GitHub)."""
    default_config = {
        "openrouter_api_key": "",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "temperature": 0.7,
        "github_repo": DEFAULT_GITHUB_REPO,
    }
    if not CONFIG_FILE.exists():
        save_config(default_config)
        return default_config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_config.update(data)
            return default_config
    except Exception:
        return default_config


def save_config(config: dict):
    """Salva as configurações locais em config.json."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_templates() -> list:
    """Carrega os templates do JSON ou inicializa com exemplos úteis."""
    if not STORAGE_FILE.exists():
        seed_data = [
            {
                "id": 1,
                "titulo": "Aviso de Cobrança / Vencimento",
                "template": (
                    "Olá, *{cliente}*! Tudo bem?\n\n"
                    "Passando para avisar que a fatura do serviço *{servico}* "
                    "vence em *{vencimento}* no valor de *R$ {valor}*.\n\n"
                    "Chave Pix para pagamento: `{pix}`\n\n"
                    "Qualquer dúvida, estamos à disposição!"
                ),
                "campos": ["cliente", "servico", "vencimento", "valor", "pix"],
            },
            {
                "id": 2,
                "titulo": "Confirmação de Agendamento",
                "template": (
                    "Olá, *{cliente}*!\n\n"
                    "Seu agendamento para *{servico}* está confirmado para o dia "
                    "*{data}* às *{horario}*.\n\n"
                    "📍 Endereço: {endereco}\n\n"
                    "Pedimos a gentileza de chegar com 10 minutos de antecedência. "
                    "Se precisar reagendar, nos avise com antecedência!"
                ),
                "campos": ["cliente", "servico", "data", "horario", "endereco"],
            },
            {
                "id": 3,
                "titulo": "Agradecimento e Feedback",
                "template": (
                    "Olá, *{cliente}*!\n\n"
                    "Agradecemos pela preferência pelo nosso serviço *{servico}*! "
                    "Esperamos que tenha gostado da experiência.\n\n"
                    "Poderia nos avaliar brevemente respondendo a esta mensagem? "
                    "Sua opinião é fundamental para melhorarmos sempre!"
                ),
                "campos": ["cliente", "servico"],
            },
        ]
        save_templates(seed_data)
        return seed_data

    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_templates(templates: list):
    """Salva a lista de templates no arquivo JSON."""
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


def extract_placeholders(text: str) -> list:
    """Extrai todas as tags {nome_campo} preservando a ordem sem duplicações."""
    matches = re.findall(r"\{([a-zA-Z0-9_]+)\}", text)
    return list(dict.fromkeys(matches))


def copy_to_clipboard(text: str, root_widget: tk.Tk = None) -> bool:
    """Copia o texto para a área de transferência com suporte nativo ao Windows UTF-16."""
    success = False
    if root_widget is not None:
        try:
            root_widget.clipboard_clear()
            root_widget.clipboard_append(text)
            root_widget.update()
            success = True
        except Exception:
            pass

    if os.name == "nt":
        try:
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
            success = True
        except Exception:
            pass

    return success


class ScrollableFrame(ttk.Frame):
    """Frame rolável verticalmente para acomodar formulários com muitos campos."""

    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg="#FFFFFF")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_content = ttk.Frame(self.canvas)

        self.scrollable_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.canvas.configure(xscrollcommand=None, yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfig(self.canvas_window, width=event.width),
        )

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_content.bind("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class UpdateNoticeDialog(tk.Toplevel):
    """Janela modal para notificar e aplicar atualizações automáticas via SemVer."""

    def __init__(self, parent, update_info: dict, github_repo: str = DEFAULT_GITHUB_REPO):
        super().__init__(parent)
        self.parent = parent
        self.update_info = update_info
        self.github_repo = github_repo

        self.title("Nova Versão Disponível!")
        self.minsize(580, 440)
        self.transient(parent)
        self.grab_set()

        self.configure(bg="#F0F2F5")
        self._setup_ui()
        self._center_window(620, 480)

    def _center_window(self, width=620, height=480):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw // 2) - (width // 2))
        y = max(0, (sh // 2) - (height // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self):
        # Cabeçalho
        header_frame = tk.Frame(self, bg="#075E54", height=50)
        header_frame.pack(fill="x", side="top")
        tk.Label(
            header_frame,
            text=f"🎉 Nova Versão Encontrada: v{self.update_info.get('version', '')}",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#075E54",
            pady=12,
            padx=16,
            anchor="w",
        ).pack(fill="x")

        # Barra de Botões no Rodapé
        btn_box = tk.Frame(self, bg="#FFFFFF", padx=16, pady=12, relief="groove", bd=1)
        btn_box.pack(fill="x", side="bottom")

        btn_later = tk.Button(
            btn_box,
            text="Mais Tarde",
            font=("Segoe UI", 9),
            bg="#E0E0E0",
            fg="#333333",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
            command=self.destroy,
        )
        btn_later.pack(side="right", padx=(10, 0))

        self.btn_update = tk.Button(
            btn_box,
            text="🚀 Baixar e Atualizar Agora",
            font=("Segoe UI", 9, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            command=self._execute_update,
        )
        self.btn_update.pack(side="right")

        # Corpo
        body_frame = tk.Frame(self, bg="#FFFFFF", padx=20, pady=16)
        body_frame.pack(fill="both", expand=True, padx=14, pady=10)

        remote_ver = self.update_info.get("version", "")
        release_date = self.update_info.get("release_date", "")

        tk.Label(
            body_frame,
            text=f"Uma nova versão do aplicativo está pronta para ser instalada!\n"
                 f"Versão Atual: v{__version__}  ➔  Nova Versão: v{remote_ver}" + (f" ({release_date})" if release_date else ""),
            font=("Segoe UI", 10, "bold"),
            bg="#FFFFFF",
            fg="#075E54",
            justify="left",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body_frame,
            text="Novidades e Melhorias desta versão:",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#333333",
            anchor="w",
        ).pack(fill="x", pady=(10, 4))

        # Changelog
        changelog_frame = tk.Frame(body_frame, bg="#F9F9F9", relief="solid", bd=1, padx=10, pady=10)
        changelog_frame.pack(fill="both", expand=True, pady=(0, 10))

        changelog_list = self.update_info.get("changelog", [])
        if isinstance(changelog_list, list) and changelog_list:
            changelog_text = "\n".join([f"• {item}" for item in changelog_list])
        else:
            changelog_text = "• Melhorias de desempenho e correções gerais."

        txt_changes = tk.Text(
            changelog_frame,
            font=("Segoe UI", 9),
            bg="#F9F9F9",
            fg="#222222",
            relief="flat",
            wrap="word",
        )
        txt_changes.insert("1.0", changelog_text)
        txt_changes.config(state="disabled")
        txt_changes.pack(fill="both", expand=True)

        info_safety = tk.Label(
            body_frame,
            text="🔒 Seus templates cadastrados e chaves de API serão 100% preservados.",
            font=("Segoe UI", 8, "italic"),
            bg="#FFFFFF",
            fg="#1B5E20",
            anchor="w",
        )
        info_safety.pack(fill="x")

        self.lbl_progress = tk.Label(
            body_frame,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#075E54",
            anchor="w",
        )
        self.lbl_progress.pack(fill="x", pady=(4, 0))

    def _execute_update(self):
        self.btn_update.config(state="disabled", text="⏳ Baixando atualização...")
        self.lbl_progress.config(text="Conectando ao GitHub e baixando novos arquivos...", fg="#075E54")

        def worker():
            success, msg = download_and_apply_update(github_repo=self.github_repo)

            def on_finish():
                if success:
                    self.lbl_progress.config(text="✅ Atualização baixada com sucesso!", fg="#075E54")
                    confirm = messagebox.askyesno(
                        "Atualização Concluída",
                        "O aplicativo foi atualizado com sucesso!\nDeseja reiniciar o programa agora para aplicar as novidades?",
                        parent=self,
                    )
                    if confirm:
                        restart_application()
                    else:
                        self.destroy()
                else:
                    self.btn_update.config(state="normal", text="🚀 Tentar Novamente")
                    self.lbl_progress.config(text=f"❌ Falha: {msg}", fg="#D32F2F")
                    messagebox.showerror("Erro na Atualização", msg, parent=self)

            self.after(0, on_finish)

        threading.Thread(target=worker, daemon=True).start()


class AIConfigDialog(tk.Toplevel):
    """Janela de Configuração da Chave de API, Modelo do OpenRouter e Repositório GitHub."""

    def __init__(self, parent, on_save_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback
        self.config = load_config()

        self.title("Configurações do Sistema e IA")
        self.minsize(580, 520)
        self.transient(parent)
        self.grab_set()

        self.configure(bg="#F0F2F5")
        self._setup_ui()
        self._center_window(640, 560)

    def _center_window(self, width=640, height=560):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw // 2) - (width // 2))
        y = max(0, (sh // 2) - (height // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self):
        header_frame = tk.Frame(self, bg="#075E54", height=50)
        header_frame.pack(fill="x", side="top")
        tk.Label(
            header_frame,
            text="⚙️ Configurações da IA & Atualizações",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#075E54",
            pady=12,
            padx=16,
            anchor="w",
        ).pack(fill="x")

        btn_box = tk.Frame(self, bg="#FFFFFF", padx=16, pady=12, relief="groove", bd=1)
        btn_box.pack(fill="x", side="bottom")

        btn_cancel = tk.Button(
            btn_box,
            text="Cancelar",
            font=("Segoe UI", 9),
            bg="#E0E0E0",
            fg="#333333",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=(10, 0))

        btn_save = tk.Button(
            btn_box,
            text="Salvar Configurações",
            font=("Segoe UI", 9, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            command=self._save_config_action,
        )
        btn_save.pack(side="right")

        body_frame = tk.Frame(self, bg="#FFFFFF", padx=20, pady=16)
        body_frame.pack(fill="both", expand=True, padx=14, pady=10)

        # Informação sobre a chave gratuita
        info_card = tk.Frame(body_frame, bg="#E8F5E9", padx=12, pady=8, relief="solid", bd=1)
        info_card.pack(fill="x", pady=(0, 10))

        tk.Label(
            info_card,
            text="💡 O OpenRouter oferece modelos gratuitos de IA (terminados em ':free').",
            font=("Segoe UI", 9),
            bg="#E8F5E9",
            fg="#1B5E20",
            justify="left",
        ).pack(side="left")

        btn_open_keys = tk.Button(
            info_card,
            text="Obter Chave Gratuita ↗",
            font=("Segoe UI", 8, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=3,
            command=lambda: webbrowser.open("https://openrouter.ai/keys"),
        )
        btn_open_keys.pack(side="right")

        # Campo: OpenRouter API Key
        tk.Label(
            body_frame,
            text="Chave de API do OpenRouter (sk-or-v1-...):",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#333333",
        ).pack(anchor="w")

        key_row = tk.Frame(body_frame, bg="#FFFFFF")
        key_row.pack(fill="x", pady=(2, 10))

        self.key_var = tk.StringVar(value=self.config.get("openrouter_api_key", ""))
        self.entry_key = ttk.Entry(key_row, textvariable=self.key_var, font=("Segoe UI", 10), show="*")
        self.entry_key.pack(side="left", fill="x", expand=True)

        self.btn_show_key = tk.Button(
            key_row,
            text="👁 Mostrar",
            font=("Segoe UI", 8),
            bg="#EEEEEE",
            relief="flat",
            cursor="hand2",
            padx=6,
            command=self._toggle_show_key,
        )
        self.btn_show_key.pack(side="left", padx=(6, 0))

        # Campo: Seleção do Modelo
        tk.Label(
            body_frame,
            text="Modelo de IA (Modelos gratuitos com sufixo ':free'):",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#333333",
        ).pack(anchor="w")

        self.model_var = tk.StringVar(value=self.config.get("model", FREE_MODELS[0]))
        self.combo_model = ttk.Combobox(
            body_frame,
            textvariable=self.model_var,
            values=FREE_MODELS,
            font=("Segoe UI", 10),
            state="normal",
        )
        self.combo_model.pack(fill="x", pady=(2, 10))

        # Campo: Repositório GitHub
        tk.Label(
            body_frame,
            text="Repositório GitHub para Auto-Update (usuario/repositorio):",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#333333",
        ).pack(anchor="w")

        self.repo_var = tk.StringVar(value=self.config.get("github_repo", DEFAULT_GITHUB_REPO))
        self.entry_repo = ttk.Entry(body_frame, textvariable=self.repo_var, font=("Segoe UI", 10))
        self.entry_repo.pack(fill="x", pady=(2, 12))

        # Linha do botão Testar Conexão
        test_frame = tk.Frame(body_frame, bg="#FFFFFF")
        test_frame.pack(fill="x", pady=(2, 6))

        self.btn_test = tk.Button(
            test_frame,
            text="🔌 Testar Conexão com OpenRouter",
            font=("Segoe UI", 9, "bold"),
            bg="#128C7E",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=self._test_connection_action,
        )
        self.btn_test.pack(side="left")

        self.lbl_test_status = tk.Label(
            body_frame,
            text="",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#333333",
            wraplength=540,
            justify="left",
            anchor="w",
        )
        self.lbl_test_status.pack(fill="x", pady=(4, 0))

    def _toggle_show_key(self):
        if self.entry_key.cget("show") == "*":
            self.entry_key.config(show="")
            self.btn_show_key.config(text="🙈 Ocultar")
        else:
            self.entry_key.config(show="*")
            self.btn_show_key.config(text="👁 Mostrar")

    def _test_connection_action(self):
        key = self.key_var.get().strip()
        model = self.model_var.get().strip()

        if not key:
            messagebox.showwarning("Aviso", "Por favor, informe a Chave de API antes de testar.", parent=self)
            return

        self.btn_test.config(state="disabled", text="⏳ Testando comunicação...")
        self.lbl_test_status.config(text="Aguarde... enviando requisição de teste para o OpenRouter.", fg="#666666")

        def worker():
            success, msg = test_api_connection(key, model)

            def update_ui():
                self.btn_test.config(state="normal", text="🔌 Testar Conexão com OpenRouter")
                if success:
                    self.lbl_test_status.config(text=f"✅ {msg}", fg="#075E54")
                else:
                    self.lbl_test_status.config(text=f"❌ Falha no teste: {msg}", fg="#D32F2F")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _save_config_action(self):
        key = self.key_var.get().strip()
        model = self.model_var.get().strip()
        repo = self.repo_var.get().strip()

        if not model:
            model = FREE_MODELS[0]
        if not repo:
            repo = DEFAULT_GITHUB_REPO

        self.config["openrouter_api_key"] = key
        self.config["model"] = model
        self.config["github_repo"] = repo
        save_config(self.config)

        if self.on_save_callback:
            self.on_save_callback(self.config)

        messagebox.showinfo("Sucesso", "Configurações salvas com sucesso em config.json!", parent=self)
        self.destroy()


class SmartFillDialog(tk.Toplevel):
    """Diálogo para o Papel 1: Auto-preenchimento Inteligente de Variáveis por Contexto."""

    def __init__(self, parent, template, on_extracted_callback):
        super().__init__(parent)
        self.parent = parent
        self.template = template
        self.on_extracted_callback = on_extracted_callback
        self.config = load_config()

        self.title("🤖 Preenchimento Inteligente com IA")
        self.minsize(580, 460)
        self.transient(parent)
        self.grab_set()

        self.configure(bg="#F0F2F5")
        self._setup_ui()
        self._center_window(660, 520)

    def _center_window(self, width=660, height=520):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw // 2) - (width // 2))
        y = max(0, (sh // 2) - (height // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self):
        header_frame = tk.Frame(self, bg="#075E54", height=50)
        header_frame.pack(fill="x", side="top")
        tk.Label(
            header_frame,
            text=f"🤖 Preenchimento Automático: {self.template.get('titulo', '')}",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#075E54",
            pady=12,
            padx=16,
            anchor="w",
        ).pack(fill="x")

        btn_box = tk.Frame(self, bg="#FFFFFF", padx=16, pady=12, relief="groove", bd=1)
        btn_box.pack(fill="x", side="bottom")

        btn_cancel = tk.Button(
            btn_box,
            text="Cancelar (Esc)",
            font=("Segoe UI", 9),
            bg="#E0E0E0",
            fg="#333333",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=(10, 0))

        self.btn_extract = tk.Button(
            btn_box,
            text="🚀 Extrair e Preencher Campos",
            font=("Segoe UI", 9, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            command=self._execute_extraction,
        )
        self.btn_extract.pack(side="right")

        body_frame = tk.Frame(self, bg="#FFFFFF", padx=18, pady=14)
        body_frame.pack(fill="both", expand=True, padx=14, pady=10)

        campos = self.template.get("campos", [])
        campos_txt = ", ".join([f"{{{c}}}" for c in campos])
        tk.Label(
            body_frame,
            text=f"Variáveis que a IA tentará identificar ({len(campos)}): {campos_txt}",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#075E54",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body_frame,
            text="Cole abaixo qualquer texto, anotação, e-mail ou conversa do cliente com os dados:",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#555555",
            anchor="w",
        ).pack(fill="x", pady=(4, 6))

        text_container = tk.Frame(body_frame)
        text_container.pack(fill="both", expand=True)

        self.txt_context = tk.Text(
            text_container,
            font=("Segoe UI", 10),
            wrap="word",
            padx=10,
            pady=10,
            relief="solid",
            bd=1,
            highlightthickness=0,
        )
        self.txt_context.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_container, orient="vertical", command=self.txt_context.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_context.config(yscrollcommand=scrollbar.set)
        self.txt_context.focus_set()

        self.lbl_status = tk.Label(
            body_frame,
            text="Dica: Cole dados desorganizados ou uma mensagem do cliente e clique em Extrair.",
            font=("Segoe UI", 8, "italic"),
            bg="#FFFFFF",
            fg="#777777",
            anchor="w",
        )
        self.lbl_status.pack(fill="x", pady=(6, 0))

        self.bind("<Escape>", lambda e: self.destroy())

    def _execute_extraction(self):
        raw_text = self.txt_context.get("1.0", "end-1c").strip()
        if not raw_text:
            messagebox.showwarning("Aviso", "Por favor, cole algum texto para a IA extrair os dados.", parent=self)
            return

        api_key = self.config.get("openrouter_api_key", "").strip()
        if not api_key:
            confirm = messagebox.askyesno(
                "Chave Não Configurada",
                "Para utilizar a IA, é necessário configurar sua chave gratuita do OpenRouter.\nDeseja abrir a tela de configuração agora?",
                parent=self,
            )
            if confirm:
                AIConfigDialog(self, on_save_callback=lambda c: setattr(self, "config", c))
            return

        model = self.config.get("model", FREE_MODELS[0])
        campos = self.template.get("campos", [])
        template_text = self.template.get("template", "")

        self.btn_extract.config(state="disabled", text="⏳ Analisando dados com IA...")
        self.lbl_status.config(text=f"Conectando ao modelo gratuito '{model}'...", fg="#075E54")

        def worker():
            try:
                extracted = extract_variables_from_context(
                    raw_context=raw_text,
                    template_text=template_text,
                    campos=campos,
                    api_key=api_key,
                    model=model,
                )

                def update_ui():
                    self.on_extracted_callback(extracted)
                    self.destroy()

                self.after(0, update_ui)
            except Exception as e:
                def show_err():
                    self.btn_extract.config(state="normal", text="🚀 Extrair e Preencher Campos")
                    self.lbl_status.config(text=f"Erro: {e}", fg="#D32F2F")
                    messagebox.showerror("Erro na Extração", f"Não foi possível extrair os dados:\n{e}", parent=self)

                self.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()


class AITemplatePromptDialog(tk.Toplevel):
    """Diálogo para o Papel 3: Criação Mágica de Novos Templates por Linguagem Natural."""

    def __init__(self, parent, on_generated_callback):
        super().__init__(parent)
        self.parent = parent
        self.on_generated_callback = on_generated_callback
        self.config = load_config()

        self.title("✨ Criar Template com IA")
        self.minsize(560, 380)
        self.transient(parent)
        self.grab_set()

        self.configure(bg="#F0F2F5")
        self._setup_ui()
        self._center_window(600, 420)

    def _center_window(self, width=600, height=420):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw // 2) - (width // 2))
        y = max(0, (sh // 2) - (height // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self):
        header_frame = tk.Frame(self, bg="#075E54", height=50)
        header_frame.pack(fill="x", side="top")
        tk.Label(
            header_frame,
            text="✨ Gerador Mágico de Templates de Mensagem",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#075E54",
            pady=12,
            padx=16,
            anchor="w",
        ).pack(fill="x")

        btn_box = tk.Frame(self, bg="#FFFFFF", padx=16, pady=12, relief="groove", bd=1)
        btn_box.pack(fill="x", side="bottom")

        btn_cancel = tk.Button(
            btn_box,
            text="Cancelar",
            font=("Segoe UI", 9),
            bg="#E0E0E0",
            fg="#333333",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=(10, 0))

        self.btn_gen = tk.Button(
            btn_box,
            text="🪄 Criar Template Agora",
            font=("Segoe UI", 9, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            command=self._execute_generation,
        )
        self.btn_gen.pack(side="right")

        body_frame = tk.Frame(self, bg="#FFFFFF", padx=18, pady=14)
        body_frame.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(
            body_frame,
            text="Descreva o que este novo template deve fazer:",
            font=("Segoe UI", 10, "bold"),
            bg="#FFFFFF",
            fg="#333333",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body_frame,
            text="Exemplo: 'Confirmação de consulta médica com data, hora, nome do doutor e lembrete de jejum.'",
            font=("Segoe UI", 8),
            bg="#FFFFFF",
            fg="#666666",
            anchor="w",
        ).pack(fill="x", pady=(2, 6))

        self.txt_prompt = tk.Text(
            body_frame,
            font=("Segoe UI", 10),
            wrap="word",
            height=6,
            padx=8,
            pady=8,
            relief="solid",
            bd=1,
            highlightthickness=0,
        )
        self.txt_prompt.pack(fill="both", expand=True, pady=(4, 6))
        self.txt_prompt.focus_set()

        self.lbl_status = tk.Label(
            body_frame,
            text="A IA definirá o título, a mensagem com formatação WhatsApp e as variáveis entre chaves.",
            font=("Segoe UI", 8, "italic"),
            bg="#FFFFFF",
            fg="#777777",
            anchor="w",
        )
        self.lbl_status.pack(fill="x")

    def _execute_generation(self):
        prompt_text = self.txt_prompt.get("1.0", "end-1c").strip()
        if not prompt_text:
            messagebox.showwarning("Aviso", "Por favor, descreva o modelo desejado.", parent=self)
            return

        api_key = self.config.get("openrouter_api_key", "").strip()
        if not api_key:
            confirm = messagebox.askyesno(
                "Chave Não Configurada",
                "Para utilizar a IA, é necessário configurar sua chave gratuita do OpenRouter.\nDeseja abrir a tela de configuração agora?",
                parent=self,
            )
            if confirm:
                AIConfigDialog(self, on_save_callback=lambda c: setattr(self, "config", c))
            return

        model = self.config.get("model", FREE_MODELS[0])

        self.btn_gen.config(state="disabled", text="⏳ Gerando template...")
        self.lbl_status.config(text=f"Consultando modelo gratuito '{model}'...", fg="#075E54")

        def worker():
            try:
                res = generate_template_from_prompt(prompt_text, api_key=api_key, model=model)

                def update_ui():
                    self.on_generated_callback(res)
                    self.destroy()

                self.after(0, update_ui)
            except Exception as e:
                def show_err():
                    self.btn_gen.config(state="normal", text="🪄 Criar Template Agora")
                    self.lbl_status.config(text=f"Erro: {e}", fg="#D32F2F")
                    messagebox.showerror("Erro ao Gerar", f"Não foi possível gerar o template:\n{e}", parent=self)

                self.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()


class TemplateEditorDialog(tk.Toplevel):
    """Janela modal para criar ou editar um template."""

    def __init__(self, parent, template_data=None):
        super().__init__(parent)
        self.parent = parent
        self.template_data = template_data
        self.result = None
        self.config = load_config()
        self.last_text_before_ai = None

        self.title("Editar Template" if template_data else "Novo Template")
        self.minsize(560, 440)
        self.transient(parent)
        self.grab_set()

        self.configure(bg="#F0F2F5")
        self._setup_ui()
        self._center_window(680, 560)

        self.bind("<Control-s>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _center_window(self, width=680, height=560):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw // 2) - (width // 2))
        y = max(0, (sh // 2) - (height // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self):
        header_frame = tk.Frame(self, bg="#075E54", height=50)
        header_frame.pack(fill="x", side="top")
        tk.Label(
            header_frame,
            text="Editar Template de Mensagem" if self.template_data else "Criar Novo Template",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#075E54",
            pady=12,
            padx=16,
            anchor="w",
        ).pack(fill="x")

        # Barra de Botões FIXA no Rodapé
        btn_box = tk.Frame(self, bg="#FFFFFF", padx=16, pady=12, relief="groove", bd=1)
        btn_box.pack(fill="x", side="bottom")

        btn_cancel = tk.Button(
            btn_box,
            text="Cancelar (Esc)",
            font=("Segoe UI", 10),
            bg="#E0E0E0",
            fg="#333333",
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=(10, 0))

        btn_save = tk.Button(
            btn_box,
            text="Salvar Template (Ctrl+S)",
            font=("Segoe UI", 10, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            activebackground="#1EBE5D",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._save,
        )
        btn_save.pack(side="right")

        # Container Principal
        body_frame = tk.Frame(self, bg="#FFFFFF", padx=16, pady=12)
        body_frame.pack(fill="both", expand=True, padx=14, pady=10)

        # Campo: Título
        lbl_title = tk.Label(
            body_frame,
            text="Título do Template:",
            font=("Segoe UI", 10, "bold"),
            bg="#FFFFFF",
            fg="#333333",
        )
        lbl_title.pack(anchor="w")

        self.title_var = tk.StringVar(value=self.template_data["titulo"] if self.template_data else "")
        self.entry_title = ttk.Entry(body_frame, textvariable=self.title_var, font=("Segoe UI", 10))
        self.entry_title.pack(fill="x", pady=(4, 10))

        # Barra de Ferramentas / Formatação + Detecção de Variáveis com IA
        lbl_msg = tk.Label(
            body_frame,
            text="Corpo da Mensagem (ou digite qualquer texto e use a IA para identificar as variáveis):",
            font=("Segoe UI", 10, "bold"),
            bg="#FFFFFF",
            fg="#333333",
        )
        lbl_msg.pack(anchor="w")

        toolbar_frame = tk.Frame(body_frame, bg="#FFFFFF")
        toolbar_frame.pack(fill="x", pady=(4, 6))

        tk.Label(toolbar_frame, text="Inserir:", font=("Segoe UI", 8), bg="#FFFFFF", fg="#666666").pack(
            side="left", padx=(0, 4)
        )

        buttons_info = [
            ("*Negrito*", "*texto*"),
            ("_Itálico_", "_texto_"),
            ("~Tachado~", "~texto~"),
            ("`Código`", "`código`"),
            ("{variável}", "{variavel}"),
        ]
        for btn_text, snippet in buttons_info:
            b = tk.Button(
                toolbar_frame,
                text=btn_text,
                font=("Segoe UI", 8),
                bg="#ECE5DD",
                relief="flat",
                cursor="hand2",
                command=lambda s=snippet: self._insert_snippet(s),
            )
            b.pack(side="left", padx=2)

        # Botão Gerar do Zero com IA
        btn_ai_create = tk.Button(
            toolbar_frame,
            text="✨ Gerar com IA",
            font=("Segoe UI", 8, "bold"),
            bg="#075E54",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=8,
            command=self._open_ai_template_generator,
        )
        btn_ai_create.pack(side="right")

        # Botão Detectar Variáveis no Texto com IA
        self.btn_detect_vars = tk.Button(
            toolbar_frame,
            text="🔍 Detectar Variáveis com IA",
            font=("Segoe UI", 8, "bold"),
            bg="#128C7E",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=8,
            command=self._detect_variables_with_ai,
        )
        self.btn_detect_vars.pack(side="right", padx=(0, 4))

        # Botão Desfazer IA (oculto por padrão)
        self.btn_undo_ai = tk.Button(
            toolbar_frame,
            text="↩️ Desfazer",
            font=("Segoe UI", 8),
            bg="#F5F5F5",
            fg="#555555",
            relief="flat",
            cursor="hand2",
            padx=6,
            command=self._undo_ai_detection,
        )

        # Editor de texto
        text_container = tk.Frame(body_frame)
        text_container.pack(fill="both", expand=True)

        self.txt_template = tk.Text(
            text_container,
            font=("Segoe UI", 10),
            wrap="word",
            height=7,
            padx=10,
            pady=8,
            relief="solid",
            bd=1,
            highlightthickness=0,
        )
        self.txt_template.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_container, orient="vertical", command=self.txt_template.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_template.config(yscrollcommand=scrollbar.set)

        if self.template_data:
            self.txt_template.insert("1.0", self.template_data.get("template", ""))

        self.lbl_vars = tk.Label(
            body_frame,
            text="Variáveis detectadas: Nenhuma",
            font=("Segoe UI", 9, "italic"),
            bg="#FFFFFF",
            fg="#075E54",
            anchor="w",
        )
        self.lbl_vars.pack(fill="x", pady=(6, 2))
        self.txt_template.bind("<KeyRelease>", self._update_detected_variables)
        self._update_detected_variables()

    def _open_ai_template_generator(self):
        def on_generated(data):
            self.title_var.set(data.get("titulo", ""))
            self.txt_template.delete("1.0", tk.END)
            self.txt_template.insert("1.0", data.get("template", ""))
            self._update_detected_variables()

        AITemplatePromptDialog(self, on_generated_callback=on_generated)

    def _detect_variables_with_ai(self):
        """Identifica e parametriza automaticamente variáveis a partir de qualquer texto digitado."""
        text = self.txt_template.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning(
                "Aviso",
                "Digite ou cole uma mensagem comum no editor para que a IA possa identificar as variáveis.",
                parent=self,
            )
            return

        api_key = self.config.get("openrouter_api_key", "").strip()
        if not api_key:
            confirm = messagebox.askyesno(
                "Chave Não Configurada",
                "Para utilizar a IA, configure sua chave do OpenRouter.\nDeseja abrir a tela de configurações agora?",
                parent=self,
            )
            if confirm:
                AIConfigDialog(self, on_save_callback=lambda c: setattr(self, "config", c))
            return

        model = self.config.get("model", FREE_MODELS[0])
        self.last_text_before_ai = text
        self.btn_detect_vars.config(state="disabled", text="⏳ Identificando variáveis...")
        self.lbl_vars.config(text=f"Analisando mensagem com modelo '{model}' e criando tags...", fg="#075E54")

        def worker():
            try:
                res = detect_and_parametrize_variables(text, api_key=api_key, model=model)

                def update_ui():
                    self.btn_detect_vars.config(state="normal", text="🔍 Detectar Variáveis com IA")
                    self.txt_template.delete("1.0", tk.END)
                    self.txt_template.insert("1.0", res.get("template", ""))

                    # Sugere título se o campo ainda estiver em branco
                    if not self.title_var.get().strip() and res.get("titulo_sugerido"):
                        self.title_var.set(res.get("titulo_sugerido"))

                    self._update_detected_variables()
                    self.btn_undo_ai.pack(side="right", padx=(0, 4))

                    campos = res.get("campos", [])
                    messagebox.showinfo(
                        "Sucesso",
                        f"Variáveis identificadas com sucesso ({len(campos)}):\n"
                        + ", ".join([f"{{{c}}}" for c in campos]),
                        parent=self,
                    )

                self.after(0, update_ui)
            except Exception as e:
                def show_err():
                    self.btn_detect_vars.config(state="normal", text="🔍 Detectar Variáveis com IA")
                    self._update_detected_variables()
                    messagebox.showerror("Erro na Identificação", f"Não foi possível identificar as variáveis:\n{e}", parent=self)

                self.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()

    def _undo_ai_detection(self):
        if hasattr(self, "last_text_before_ai") and self.last_text_before_ai:
            self.txt_template.delete("1.0", tk.END)
            self.txt_template.insert("1.0", self.last_text_before_ai)
            self._update_detected_variables()
            self.btn_undo_ai.pack_forget()

    def _insert_snippet(self, snippet):
        self.txt_template.insert(tk.INSERT, snippet)
        self.txt_template.focus_set()
        self._update_detected_variables()

    def _update_detected_variables(self, event=None):
        text = self.txt_template.get("1.0", "end-1c")
        vars_found = extract_placeholders(text)
        if vars_found:
            self.lbl_vars.config(
                text=f"Variáveis detectadas ({len(vars_found)}): {', '.join(vars_found)}",
                fg="#075E54",
            )
        else:
            self.lbl_vars.config(
                text="Variáveis detectadas: Nenhuma (Use {nome_campo} ou clique em '🔍 Detectar Variáveis com IA')",
                fg="#888888",
            )

    def _save(self):
        title = self.title_var.get().strip()
        body = self.txt_template.get("1.0", "end-1c").strip()

        if not title:
            messagebox.showwarning("Aviso", "Por favor, informe o título do template.", parent=self)
            self.entry_title.focus_set()
            return

        if not body:
            messagebox.showwarning("Aviso", "O corpo da mensagem não pode ficar vazio.", parent=self)
            self.txt_template.focus_set()
            return

        campos = extract_placeholders(body)
        self.result = {
            "titulo": title,
            "template": body,
            "campos": campos,
        }
        self.destroy()


class WhatsAppMessageGeneratorApp:
    """Aplicativo Principal com Suporte a IA Nativa do OpenRouter e Auto-Update SemVer."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} - v{__version__}")
        self.root.geometry("1100x740")
        self.root.minsize(940, 620)
        self.root.configure(bg="#F0F2F5")

        self.config = load_config()
        self.templates = load_templates()
        self.selected_template = None
        self.field_entries = {}
        self.custom_ai_message = None

        self._init_styles()
        self._create_header()
        self._create_main_content()
        self._create_status_bar()

        if self.templates:
            self.listbox_templates.selection_set(0)
            self._on_template_select()

        # Verificação automática e silenciosa de atualizações 2 segundos após inicializar
        self.root.after(2000, self._check_updates_auto)

    def _init_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScrollbar", background="#D1D7DB", arrowcolor="#54656F")

    def _create_header(self):
        header = tk.Frame(self.root, bg="#075E54", height=65)
        header.pack(fill="x", side="top")

        title_box = tk.Frame(header, bg="#075E54", padx=20, pady=12)
        title_box.pack(side="left", fill="y")

        lbl_title = tk.Label(
            title_box,
            text=f"💬 {APP_NAME}  (v{__version__})",
            font=("Segoe UI", 14, "bold"),
            fg="#FFFFFF",
            bg="#075E54",
        )
        lbl_title.pack(anchor="w")

        tk.Label(
            title_box,
            text="Preencha dados com IA gratuita do OpenRouter, padronize mensagens e envie com 1 clique!",
            font=("Segoe UI", 9),
            fg="#B2DFDB",
            bg="#075E54",
        ).pack(anchor="w")

        # Botão de Configuração de IA no topo
        btn_ai_config = tk.Button(
            header,
            text="⚙️ Configurações",
            font=("Segoe UI", 9, "bold"),
            bg="#128C7E",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=self._open_ai_config_dialog,
        )
        btn_ai_config.pack(side="right", padx=(4, 18), pady=14)

        # Botão de Verificação Manual de Atualizações
        self.btn_update_header = tk.Button(
            header,
            text="🔄 Atualizações",
            font=("Segoe UI", 9),
            bg="#0B6B60",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._check_updates_manual,
        )
        self.btn_update_header.pack(side="right", padx=4, pady=14)

    def _check_updates_auto(self):
        """Verifica atualizações em segundo plano sem travar a interface."""
        repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO)

        def worker():
            update_data = check_for_updates(repo)
            if update_data:
                def show_dialog():
                    UpdateNoticeDialog(self.root, update_data, github_repo=repo)

                self.root.after(0, show_dialog)

        threading.Thread(target=worker, daemon=True).start()

    def _check_updates_manual(self):
        """Verificação disparada manualmente pelo usuário."""
        repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO)
        self._set_status("🔄 Verificando atualizações no GitHub...")

        def worker():
            update_data = check_for_updates(repo)

            def update_ui():
                if update_data:
                    UpdateNoticeDialog(self.root, update_data, github_repo=repo)
                    self._set_status(f"Nova versão v{update_data.get('version')} encontrada!", is_success=True)
                else:
                    self._set_status(f"✅ Você já está utilizando a versão mais recente (v{__version__}).", is_success=True)
                    messagebox.showinfo(
                        "Atualizações",
                        f"Você já está na versão mais recente!\n\nVersão instalada: v{__version__}\nRepositório: {repo}",
                        parent=self.root,
                    )

            self.root.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _open_ai_config_dialog(self):
        def on_save(new_config):
            self.config = new_config
            self._set_status(f"Configurações salvas. Modelo: {new_config.get('model')}", is_success=True)

        AIConfigDialog(self.root, on_save_callback=on_save)

    def _create_main_content(self):
        content = tk.Frame(self.root, bg="#F0F2F5", padx=12, pady=12)
        content.pack(fill="both", expand=True)

        paned = tk.PanedWindow(content, orient="horizontal", bg="#E0E0E0", sashwidth=4, bd=0)
        paned.pack(fill="both", expand=True)

        # PAINEL ESQUERDO: Lista de Templates
        left_panel = tk.Frame(paned, bg="#FFFFFF", width=300)
        paned.add(left_panel, minsize=240, stretch="never")

        left_header = tk.Frame(left_panel, bg="#FFFFFF", padx=12, pady=12)
        left_header.pack(fill="x")

        tk.Label(
            left_header,
            text="Templates Cadastrados",
            font=("Segoe UI", 11, "bold"),
            bg="#FFFFFF",
            fg="#128C7E",
        ).pack(anchor="w")

        search_frame = tk.Frame(left_header, bg="#FFFFFF", pady=6)
        search_frame.pack(fill="x")
        tk.Label(search_frame, text="🔍", font=("Segoe UI", 10), bg="#FFFFFF").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._filter_templates())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=("Segoe UI", 9))
        search_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        list_container = tk.Frame(left_panel, bg="#FFFFFF", padx=12)
        list_container.pack(fill="both", expand=True)

        self.listbox_templates = tk.Listbox(
            list_container,
            font=("Segoe UI", 10),
            selectbackground="#128C7E",
            selectforeground="#FFFFFF",
            activestyle="none",
            relief="solid",
            bd=1,
            highlightthickness=0,
        )
        list_scroll = ttk.Scrollbar(list_container, orient="vertical", command=self.listbox_templates.yview)
        self.listbox_templates.config(yscrollcommand=list_scroll.set)

        self.listbox_templates.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        self.listbox_templates.bind("<<ListboxSelect>>", self._on_template_select)

        btn_mgmt = tk.Frame(left_panel, bg="#FFFFFF", padx=12, pady=10)
        btn_mgmt.pack(fill="x")

        btn_new = tk.Button(
            btn_mgmt,
            text="➕ Novo Template",
            font=("Segoe UI", 9, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            pady=6,
            command=self._btn_new_template,
        )
        btn_new.pack(fill="x", pady=(0, 6))

        mgmt_row = tk.Frame(btn_mgmt, bg="#FFFFFF")
        mgmt_row.pack(fill="x")

        btn_edit = tk.Button(
            mgmt_row,
            text="✏️ Editar",
            font=("Segoe UI", 9),
            bg="#EFEFEF",
            fg="#333333",
            relief="flat",
            cursor="hand2",
            pady=4,
            command=self._btn_edit_template,
        )
        btn_edit.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_del = tk.Button(
            mgmt_row,
            text="🗑️ Excluir",
            font=("Segoe UI", 9),
            bg="#FFEBEE",
            fg="#C62828",
            relief="flat",
            cursor="hand2",
            pady=4,
            command=self._btn_delete_template,
        )
        btn_del.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # PAINEL CENTRAL E DIREITO
        right_panel = tk.Frame(paned, bg="#F0F2F5")
        paned.add(right_panel, minsize=620, stretch="always")

        work_paned = tk.PanedWindow(right_panel, orient="horizontal", bg="#E0E0E0", sashwidth=4, bd=0)
        work_paned.pack(fill="both", expand=True)

        # --- FORMULÁRIO DE PREENCHIMENTO ---
        form_card = tk.Frame(work_paned, bg="#FFFFFF", padx=14, pady=14)
        work_paned.add(form_card, minsize=310, stretch="always")

        self.lbl_selected_title = tk.Label(
            form_card,
            text="Preencha as Variáveis",
            font=("Segoe UI", 11, "bold"),
            bg="#FFFFFF",
            fg="#075E54",
            anchor="w",
        )
        self.lbl_selected_title.pack(fill="x", side="top")

        lbl_desc = tk.Label(
            form_card,
            text="Digite manualmente ou use a IA para preencher a partir de uma conversa:",
            font=("Segoe UI", 8),
            bg="#FFFFFF",
            fg="#666666",
            anchor="w",
        )
        lbl_desc.pack(fill="x", side="top", pady=(2, 8))

        form_bottom_row = tk.Frame(form_card, bg="#FFFFFF", pady=6)
        form_bottom_row.pack(fill="x", side="bottom")

        btn_clear = tk.Button(
            form_bottom_row,
            text="🧹 Limpar",
            font=("Segoe UI", 8),
            bg="#F5F5F5",
            fg="#666666",
            relief="flat",
            cursor="hand2",
            padx=8,
            command=self._clear_all_fields,
        )
        btn_clear.pack(side="left")

        self.btn_smart_fill = tk.Button(
            form_bottom_row,
            text="🤖 Preencher com IA",
            font=("Segoe UI", 8, "bold"),
            bg="#075E54",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=10,
            command=self._open_smart_fill_dialog,
        )
        self.btn_smart_fill.pack(side="right")

        self.scroll_form = ScrollableFrame(form_card)
        self.scroll_form.pack(fill="both", expand=True)

        # --- PRÉVIA ESTILO WHATSAPP E AÇÕES ---
        preview_card = tk.Frame(work_paned, bg="#FFFFFF", padx=14, pady=14)
        work_paned.add(preview_card, minsize=330, stretch="always")

        preview_header = tk.Frame(preview_card, bg="#FFFFFF")
        preview_header.pack(fill="x", side="top")

        tk.Label(
            preview_header,
            text="📱 Prévia da Mensagem (WhatsApp)",
            font=("Segoe UI", 11, "bold"),
            bg="#FFFFFF",
            fg="#075E54",
        ).pack(side="left")

        # Barra de Adaptação de Tom com IA
        tone_frame = tk.Frame(preview_card, bg="#FFFFFF", pady=4)
        tone_frame.pack(fill="x", side="top", pady=(2, 6))

        tk.Label(
            tone_frame,
            text="Tom:",
            font=("Segoe UI", 8, "bold"),
            bg="#FFFFFF",
            fg="#555555",
        ).pack(side="left", padx=(0, 4))

        tones = [
            ("👔 Formal", "formal"),
            ("😊 Amigável", "amigavel"),
            ("⏳ Cobrança Suave", "cobranca_suave"),
            ("⚡ Direto", "direto"),
        ]
        for label, tone_key in tones:
            btn_tone = tk.Button(
                tone_frame,
                text=label,
                font=("Segoe UI", 8),
                bg="#ECE5DD",
                relief="flat",
                cursor="hand2",
                command=lambda t=tone_key: self._apply_ai_tone(t),
            )
            btn_tone.pack(side="left", padx=2)

        self.btn_restore = tk.Button(
            tone_frame,
            text="↩️ Original",
            font=("Segoe UI", 8),
            bg="#F5F5F5",
            fg="#777777",
            relief="flat",
            cursor="hand2",
            command=self._restore_original_preview,
        )
        self.btn_restore.pack(side="right", padx=(4, 0))

        # Ações no Rodapé
        self.btn_copy = tk.Button(
            preview_card,
            text="📋 COPIAR MENSAGEM (PRONTO PARA COLAR)",
            font=("Segoe UI", 10, "bold"),
            bg="#25D366",
            fg="#FFFFFF",
            activebackground="#1EBE5D",
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            pady=10,
            command=self._btn_copy_message,
        )
        self.btn_copy.pack(fill="x", side="bottom", pady=(8, 0))

        direct_frame = tk.Frame(preview_card, bg="#FFFFFF", pady=4)
        direct_frame.pack(fill="x", side="bottom")

        tk.Label(
            direct_frame,
            text="WhatsApp do Destinatário (opcional, com DDD):",
            font=("Segoe UI", 8, "bold"),
            bg="#FFFFFF",
            fg="#555555",
        ).pack(anchor="w")

        phone_row = tk.Frame(direct_frame, bg="#FFFFFF")
        phone_row.pack(fill="x", pady=2)

        self.phone_var = tk.StringVar()
        entry_phone = ttk.Entry(phone_row, textvariable=self.phone_var, font=("Segoe UI", 9))
        entry_phone.pack(side="left", fill="x", expand=True)

        btn_open_wa = tk.Button(
            phone_row,
            text="📲 Abrir no WhatsApp",
            font=("Segoe UI", 8, "bold"),
            bg="#128C7E",
            fg="#FFFFFF",
            relief="flat",
            cursor="hand2",
            padx=8,
            command=self._btn_open_whatsapp,
        )
        btn_open_wa.pack(side="left", padx=(6, 0))

        bubble_outer = tk.Frame(preview_card, bg="#EFEAE2", padx=10, pady=10, relief="solid", bd=1)
        bubble_outer.pack(fill="both", expand=True, pady=4)

        bubble_inner = tk.Frame(bubble_outer, bg="#DCF8C6", padx=8, pady=8, relief="flat")
        bubble_inner.pack(fill="both", expand=True)

        self.txt_preview = tk.Text(
            bubble_inner,
            font=("Segoe UI", 10),
            bg="#DCF8C6",
            fg="#111B21",
            relief="flat",
            wrap="word",
            padx=6,
            pady=6,
            highlightthickness=0,
        )
        preview_scroll = ttk.Scrollbar(bubble_inner, orient="vertical", command=self.txt_preview.yview)
        self.txt_preview.config(yscrollcommand=preview_scroll.set)

        self.txt_preview.pack(side="left", fill="both", expand=True)
        preview_scroll.pack(side="right", fill="y")

        self._reload_template_list()

    def _create_status_bar(self):
        self.status_frame = tk.Frame(self.root, bg="#ECE5DD", height=30, padx=14)
        self.status_frame.pack(side="bottom", fill="x")

        self.lbl_status = tk.Label(
            self.status_frame,
            text=f"Pronto. {APP_NAME} v{__version__}.",
            font=("Segoe UI", 9),
            bg="#ECE5DD",
            fg="#333333",
            anchor="w",
        )
        self.lbl_status.pack(side="left", fill="x", pady=4)

    def _set_status(self, text: str, is_success: bool = False, is_error: bool = False):
        color = "#075E54" if is_success else ("#D32F2F" if is_error else "#333333")
        self.lbl_status.config(text=text, fg=color)

    def _reload_template_list(self):
        query = self.search_var.get().strip().lower()
        self.filtered_templates = [
            t for t in self.templates if query in t.get("titulo", "").lower()
        ]

        self.listbox_templates.delete(0, tk.END)
        for t in self.filtered_templates:
            campos_count = len(t.get("campos", []))
            self.listbox_templates.insert(tk.END, f"{t['titulo']} ({campos_count} var)")

    def _filter_templates(self):
        self._reload_template_list()
        if self.filtered_templates:
            self.listbox_templates.selection_set(0)
            self._on_template_select()
        else:
            self._clear_form()
            self._update_preview()

    def _on_template_select(self, event=None):
        selected_indices = self.listbox_templates.curselection()
        if not selected_indices:
            return

        idx = selected_indices[0]
        if idx >= len(self.filtered_templates):
            return

        self.selected_template = self.filtered_templates[idx]
        self.custom_ai_message = None
        self.lbl_selected_title.config(text=f"Template: {self.selected_template['titulo']}")
        self._rebuild_fields_form()
        self._update_preview()
        self._set_status(f"Template '{self.selected_template['titulo']}' selecionado.")

    def _rebuild_fields_form(self):
        for widget in self.scroll_form.scrollable_content.winfo_children():
            widget.destroy()

        self.field_entries.clear()

        if not self.selected_template:
            return

        campos = self.selected_template.get("campos", [])
        if not campos:
            lbl_no_vars = tk.Label(
                self.scroll_form.scrollable_content,
                text="Este template não possui variáveis entre chaves.\nA mensagem está pronta para ser copiada diretamente!",
                font=("Segoe UI", 9, "italic"),
                bg="#FFFFFF",
                fg="#666666",
                justify="left",
                pady=10,
            )
            lbl_no_vars.pack(fill="x", anchor="w")
            self.btn_smart_fill.config(state="disabled")
            return

        self.btn_smart_fill.config(state="normal")
        first_entry = None
        for campo in campos:
            row_frame = tk.Frame(self.scroll_form.scrollable_content, bg="#FFFFFF", pady=4)
            row_frame.pack(fill="x", expand=True)

            label_name = campo.replace("_", " ").capitalize()
            tk.Label(
                row_frame,
                text=f"{label_name} ({campo}):",
                font=("Segoe UI", 9, "bold"),
                bg="#FFFFFF",
                fg="#333333",
                anchor="w",
            ).pack(fill="x")

            var = tk.StringVar()
            var.trace_add("write", lambda *args: self._on_field_typing())
            self.field_entries[campo] = var

            entry = ttk.Entry(row_frame, textvariable=var, font=("Segoe UI", 10))
            entry.pack(fill="x", pady=(2, 6))

            if first_entry is None:
                first_entry = entry

        if first_entry:
            first_entry.focus_set()

    def _on_field_typing(self):
        self.custom_ai_message = None
        self._update_preview()

    def _clear_all_fields(self):
        for var in self.field_entries.values():
            var.set("")
        self.custom_ai_message = None
        self._update_preview()
        self._set_status("Campos limpos.")

    def _clear_form(self):
        for widget in self.scroll_form.scrollable_content.winfo_children():
            widget.destroy()
        self.field_entries.clear()
        self.selected_template = None
        self.custom_ai_message = None
        self.lbl_selected_title.config(text="Nenhum template selecionado")

    def _open_smart_fill_dialog(self):
        if not self.selected_template:
            messagebox.showinfo("Aviso", "Selecione um template antes de preencher com IA.")
            return

        def on_extracted(extracted_dict):
            filled_count = 0
            for campo, val in extracted_dict.items():
                if campo in self.field_entries and val:
                    self.field_entries[campo].set(val)
                    filled_count += 1
            self.custom_ai_message = None
            self._update_preview()
            self._set_status(f"✅ Sucesso! {filled_count} campos foram preenchidos pela IA.", is_success=True)

        SmartFillDialog(self.root, self.selected_template, on_extracted_callback=on_extracted)

    def _apply_ai_tone(self, target_tone: str):
        if not self.selected_template:
            messagebox.showinfo("Aviso", "Selecione um template primeiro.")
            return

        current_msg = self._get_raw_copy_message()
        if not current_msg.strip():
            messagebox.showinfo("Aviso", "A mensagem está vazia.")
            return

        api_key = self.config.get("openrouter_api_key", "").strip()
        if not api_key:
            confirm = messagebox.askyesno(
                "Chave Não Configurada",
                "Para utilizar a adaptação de tom com IA, configure sua chave do OpenRouter.\nDeseja abrir a tela de configurações agora?",
            )
            if confirm:
                self._open_ai_config_dialog()
            return

        model = self.config.get("model", FREE_MODELS[0])
        self._set_status(f"🤖 IA adaptando tom ({target_tone}) com o modelo '{model}'... aguarde.")

        def worker():
            try:
                adapted = adapt_message_tone(current_msg, target_tone, api_key=api_key, model=model)

                def update_ui():
                    self.custom_ai_message = adapted
                    self.txt_preview.config(state="normal")
                    self.txt_preview.delete("1.0", tk.END)
                    self.txt_preview.insert("1.0", adapted)
                    self.txt_preview.config(state="disabled")
                    self._set_status(f"✅ Tom adaptado para '{target_tone}' com sucesso!", is_success=True)

                self.root.after(0, update_ui)
            except Exception as e:
                def show_err():
                    self._set_status(f"Erro ao adaptar tom: {e}", is_error=True)
                    messagebox.showerror("Erro de IA", f"Não foi possível adaptar o tom da mensagem:\n{e}")

                self.root.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()

    def _restore_original_preview(self):
        self.custom_ai_message = None
        self._update_preview()
        self._set_status("Mensagem restaurada para o template padrão.")

    def _get_formatted_message(self) -> str:
        if self.custom_ai_message:
            return self.custom_ai_message

        if not self.selected_template:
            return ""

        body = self.selected_template.get("template", "")
        for campo, var in self.field_entries.items():
            val = var.get().strip()
            substitute = val if val else f"[{campo}]"
            body = body.replace(f"{{{campo}}}", substitute)

        return body

    def _get_raw_copy_message(self) -> str:
        if self.custom_ai_message:
            return self.custom_ai_message

        if not self.selected_template:
            return ""

        body = self.selected_template.get("template", "")
        for campo, var in self.field_entries.items():
            val = var.get().strip()
            body = body.replace(f"{{{campo}}}", val)

        return body

    def _update_preview(self):
        self.txt_preview.config(state="normal")
        self.txt_preview.delete("1.0", tk.END)

        if not self.selected_template:
            self.txt_preview.insert("1.0", "Selecione ou crie um template para visualizar a prévia aqui.")
            self.txt_preview.config(state="disabled")
            return

        msg = self._get_formatted_message()
        self.txt_preview.insert("1.0", msg)
        self.txt_preview.config(state="disabled")

    def _btn_copy_message(self):
        if not self.selected_template:
            messagebox.showinfo("Aviso", "Selecione um template primeiro!")
            return

        final_msg = self._get_raw_copy_message()
        success = copy_to_clipboard(final_msg, self.root)

        if success:
            self._set_status("✅ SUCESSO: Mensagem copiada! Basta ir ao WhatsApp e pressionar Ctrl + V.", is_success=True)
            original_bg = self.btn_copy.cget("bg")
            original_text = self.btn_copy.cget("text")
            self.btn_copy.config(bg="#128C7E", text="✅ COPIADO COM SUCESSO!")
            self.root.after(1500, lambda: self.btn_copy.config(bg=original_bg, text=original_text))
        else:
            self._set_status("❌ Não foi possível copiar para o clipboard automaticamente.", is_error=True)

    def _btn_open_whatsapp(self):
        if not self.selected_template:
            messagebox.showinfo("Aviso", "Selecione um template primeiro!")
            return

        final_msg = self._get_raw_copy_message()
        phone_raw = self.phone_var.get().strip()
        clean_phone = re.sub(r"\D", "", phone_raw)

        encoded_text = urllib.parse.quote(final_msg)

        if clean_phone:
            if len(clean_phone) in (10, 11) and not clean_phone.startswith("55"):
                clean_phone = "55" + clean_phone
            url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_text}"
        else:
            url = f"https://api.whatsapp.com/send?text={encoded_text}"

        try:
            webbrowser.open(url)
            self._set_status("🚀 WhatsApp iniciado no navegador / aplicativo!", is_success=True)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o navegador: {e}")

    def _btn_new_template(self):
        dialog = TemplateEditorDialog(self.root)
        self.root.wait_window(dialog)

        if dialog.result:
            new_id = (max([t.get("id", 0) for t in self.templates], default=0) + 1)
            new_item = {
                "id": new_id,
                "titulo": dialog.result["titulo"],
                "template": dialog.result["template"],
                "campos": dialog.result["campos"],
            }
            self.templates.append(new_item)
            save_templates(self.templates)
            self._reload_template_list()

            for i, t in enumerate(self.filtered_templates):
                if t["id"] == new_id:
                    self.listbox_templates.selection_clear(0, tk.END)
                    self.listbox_templates.selection_set(i)
                    self._on_template_select()
                    break

            self._set_status(f"Template '{new_item['titulo']}' adicionado com sucesso!", is_success=True)

    def _btn_edit_template(self):
        if not self.selected_template:
            messagebox.showinfo("Aviso", "Selecione um template na lista para editar.")
            return

        dialog = TemplateEditorDialog(self.root, template_data=self.selected_template)
        self.root.wait_window(dialog)

        if dialog.result:
            self.selected_template["titulo"] = dialog.result["titulo"]
            self.selected_template["template"] = dialog.result["template"]
            self.selected_template["campos"] = dialog.result["campos"]

            save_templates(self.templates)
            self._reload_template_list()
            self._rebuild_fields_form()
            self._update_preview()
            self._set_status(f"Template '{self.selected_template['titulo']}' atualizado com sucesso!", is_success=True)

    def _btn_delete_template(self):
        if not self.selected_template:
            messagebox.showinfo("Aviso", "Selecione um template na lista para excluir.")
            return

        confirm = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o template:\n'{self.selected_template['titulo']}'?",
            parent=self.root,
        )
        if confirm:
            self.templates = [t for t in self.templates if t["id"] != self.selected_template["id"]]
            save_templates(self.templates)
            self.selected_template = None
            self._reload_template_list()
            if self.filtered_templates:
                self.listbox_templates.selection_set(0)
                self._on_template_select()
            else:
                self._clear_form()
                self._update_preview()
            self._set_status("Template excluído.", is_success=True)


def main():
    root = tk.Tk()
    app = WhatsAppMessageGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
