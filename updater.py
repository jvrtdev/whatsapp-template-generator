import os
import sys
import re
import json
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from version import __version__, DEFAULT_GITHUB_REPO

# Arquivos essenciais do sistema a serem atualizados (templates.json e config.json NUNCA são sobrescritos)
CORE_UPDATE_FILES = [
    "whatsapp_templates_gui.py",
    "ai_service.py",
    "updater.py",
    "version.py",
    "version.json",
    "Iniciar_Gerador_WhatsApp.bat",
    "README.md",
]


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """
    Converte uma string de versão SemVer (ex: 'v1.2.3', '1.2.0', '2.0.1-beta')
    em uma tupla de inteiros (major, minor, patch) para comparação confiável.
    """
    cleaned = version_str.strip().lstrip("vV")
    numbers = re.findall(r"\d+", cleaned)
    major = int(numbers[0]) if len(numbers) > 0 else 0
    minor = int(numbers[1]) if len(numbers) > 1 else 0
    patch = int(numbers[2]) if len(numbers) > 2 else 0
    return (major, minor, patch)


def is_newer_version(remote_version: str, local_version: str = __version__) -> bool:
    """Verifica se a versão remota é superior à versão local conforme regras de SemVer."""
    return parse_semver(remote_version) > parse_semver(local_version)


def check_for_updates(github_repo: str = DEFAULT_GITHUB_REPO, timeout: int = 5) -> Optional[Dict[str, Any]]:
    """
    Consulta o manifesto version.json no repositório GitHub via HTTPS.
    Retorna o dicionário com dados da versão remota caso seja mais recente, ou None.
    """
    if not github_repo or "/" not in github_repo:
        return None

    repo_clean = github_repo.strip()
    manifest_url = f"https://raw.githubusercontent.com/{repo_clean}/main/version.json"

    headers = {
        "User-Agent": "WhatsApp-Template-Generator-AutoUpdater",
        "Cache-Control": "no-cache",
    }

    req = urllib.request.Request(manifest_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                data = json.loads(body)
                remote_ver = data.get("version", "")
                if remote_ver and is_newer_version(remote_ver, __version__):
                    return data
    except Exception:
        # Silencioso se o repositório ainda não existir ou se não houver internet
        pass

    return None


def download_and_apply_update(
    github_repo: str = DEFAULT_GITHUB_REPO,
    target_dir: Optional[Path] = None,
    timeout: int = 15,
) -> Tuple[bool, str]:
    """
    Baixa os arquivos atualizados do GitHub e os aplica no diretório local.
    Preserva rigorosamente 'templates.json' e 'config.json'.
    """
    if target_dir is None:
        target_dir = Path(__file__).resolve().parent

    repo_clean = github_repo.strip()
    base_raw_url = f"https://raw.githubusercontent.com/{repo_clean}/main"

    headers = {
        "User-Agent": "WhatsApp-Template-Generator-AutoUpdater",
        "Cache-Control": "no-cache",
    }

    downloaded_files = {}

    try:
        # Primeiro, baixa todos os arquivos para a memória garantindo que todos estão íntegros
        for filename in CORE_UPDATE_FILES:
            file_url = f"{base_raw_url}/{filename}"
            req = urllib.request.Request(file_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        content = resp.read()
                        downloaded_files[filename] = content
            except urllib.error.HTTPError as e:
                # Arquivos opcionais (ex: README.md ou Iniciar_Gerador_WhatsApp.bat) se não existirem no repositório
                if filename in ("whatsapp_templates_gui.py", "version.py"):
                    return False, f"Falha ao baixar arquivo essencial '{filename}': HTTP {e.code}"

        if "whatsapp_templates_gui.py" not in downloaded_files:
            return False, "O código principal não pôde ser baixado do repositório."

        # Aplica a gravação dos arquivos no disco
        for filename, content in downloaded_files.items():
            dest_path = target_dir / filename
            with open(dest_path, "wb") as f:
                f.write(content)

        return True, "Atualização aplicada com sucesso!"

    except Exception as e:
        return False, f"Erro durante a atualização: {e}"


def restart_application():
    """Reinicia o aplicativo executando o script principal em um novo processo e finalizando o atual."""
    main_script = Path(__file__).resolve().parent / "whatsapp_templates_gui.py"
    if not main_script.exists():
        main_script = Path(sys.argv[0]).resolve()

    executable = sys.executable
    # No Windows, prefere pythonw para não abrir janela preta do console
    if os.name == "nt" and executable.lower().endswith("python.exe"):
        pythonw_path = Path(executable).with_name("pythonw.exe")
        if pythonw_path.exists():
            executable = str(pythonw_path)

    subprocess.Popen([executable, str(main_script)])
    sys.exit(0)
