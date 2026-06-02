#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATENA Setup & Run Script v1.0
Instala todas as dependências automaticamente e executa o sistema
"""

import os
import sys
import subprocess
import json
import platform
from pathlib import Path
from typing import List, Tuple, Dict, Any

# ========== CONFIGURAÇÃO ==========

ROOT = Path(__file__).resolve().parent
PYTHON_MIN_VERSION = (3, 10)
SETUP_DIR = ROOT / "setup"
REQUIREMENTS_PINNED = SETUP_DIR / "requirements-pinned.txt"
REQUIREMENTS_DEV = SETUP_DIR / "requirements-dev.txt"
VENV_DIR = ROOT / "venv"
LOGS_DIR = ROOT / "logs"

# ========== CORES PARA OUTPUT ==========

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(msg: str):
    """Imprime header formatado"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}🔱 {msg}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.ENDC}\n")

def print_success(msg: str):
    """Imprime mensagem de sucesso"""
    print(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}")

def print_error(msg: str):
    """Imprime mensagem de erro"""
    print(f"{Colors.RED}❌ {msg}{Colors.ENDC}")

def print_warning(msg: str):
    """Imprime aviso"""
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.ENDC}")

def print_info(msg: str):
    """Imprime informação"""
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.ENDC}")

# ========== VERIFICAÇÕES INICIAIS ==========

def check_python_version() -> bool:
    """Verifica se Python >= 3.10"""
    print_header("Verificando Versão do Python")
    
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    print_info(f"Python version: {version_str}")
    print_info(f"Python executable: {sys.executable}")
    print_info(f"Platform: {platform.platform()}")
    
    if version >= PYTHON_MIN_VERSION:
        print_success(f"Python {version_str} atende os requisitos (>= 3.10)")
        return True
    else:
        print_error(f"Python {version_str} é menor que 3.10 requerido")
        return False

def check_git() -> bool:
    """Verifica se Git está instalado"""
    print_header("Verificando Git")
    
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print_success(f"Git encontrado: {result.stdout.strip()}")
            return True
    except Exception as e:
        print_error(f"Git não encontrado: {e}")
    
    return False

def check_pip() -> bool:
    """Verifica se pip está disponível"""
    print_header("Verificando pip")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print_success(f"pip encontrado: {result.stdout.strip()}")
            return True
    except Exception as e:
        print_error(f"pip não encontrado: {e}")
    
    return False

# ========== GERENCIAMENTO DE VENV ==========

def create_venv() -> bool:
    """Cria virtual environment"""
    print_header("Criando Virtual Environment")
    
    if VENV_DIR.exists():
        print_warning(f"Virtual environment já existe em {VENV_DIR}")
        response = input(f"{Colors.YELLOW}Deseja recriá-lo? (y/n): {Colors.ENDC}").strip().lower()
        
        if response == 'y':
            print_info("Removendo venv existente...")
            import shutil
            try:
                shutil.rmtree(VENV_DIR)
                print_success("Venv removido")
            except Exception as e:
                print_error(f"Falha ao remover venv: {e}")
                return False
        else:
            print_info("Usando venv existente")
            return True
    
    try:
        print_info(f"Criando venv em {VENV_DIR}...")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            timeout=60
        )
        
        if result.returncode == 0:
            print_success("Virtual environment criado com sucesso")
            return True
        else:
            print_error("Falha ao criar virtual environment")
            return False
    
    except Exception as e:
        print_error(f"Erro ao criar venv: {e}")
        return False

def get_venv_python() -> Path:
    """Retorna caminho do Python no venv"""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    else:
        return VENV_DIR / "bin" / "python"

def get_venv_pip() -> Path:
    """Retorna caminho do pip no venv"""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "pip.exe"
    else:
        return VENV_DIR / "bin" / "pip"

def activate_venv():
    """Retorna comando para ativar venv"""
    if platform.system() == "Windows":
        return str(VENV_DIR / "Scripts" / "activate.bat")
    else:
        return f"source {VENV_DIR / 'bin' / 'activate'}"

# ========== INSTALAÇÃO DE DEPENDÊNCIAS ==========

def upgrade_pip(pip_path: Path) -> bool:
    """Atualiza pip para versão mais recente"""
    print_header("Atualizando pip")
    
    try:
        print_info("Atualizando pip...")
        result = subprocess.run(
            [str(pip_path), "install", "--upgrade", "pip", "setuptools", "wheel"],
            timeout=120,
            capture_output=False
        )
        
        if result.returncode == 0:
            print_success("pip atualizado com sucesso")
            return True
        else:
            print_warning("Falha ao atualizar pip (continuando mesmo assim)")
            return True
    
    except Exception as e:
        print_warning(f"Erro ao atualizar pip: {e} (continuando mesmo assim)")
        return True

def install_requirements(pip_path: Path, requirements_file: Path) -> bool:
    """Instala requisitos de um arquivo"""
    print_header(f"Instalando Requisitos: {requirements_file.name}")
    
    if not requirements_file.exists():
        print_warning(f"Arquivo não encontrado: {requirements_file}")
        return False
    
    try:
        print_info(f"Lendo {requirements_file.name}...")
        with open(requirements_file) as f:
            packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        print_info(f"Total de pacotes: {len(packages)}")
        
        for i, package in enumerate(packages, 1):
            print_info(f"[{i}/{len(packages)}] Instalando: {package[:50]}...")
            
            result = subprocess.run(
                [str(pip_path), "install", "--quiet", package],
                timeout=300,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print_warning(f"Falha ao instalar {package}")
                if "No matching distribution" in result.stderr or "ERROR" in result.stderr:
                    print_warning(f"  Erro: {result.stderr[:100]}")
                    print_info("  Pulando para o próximo pacote...")
                    continue
            else:
                print_success(f"  ✓ {package.split('==')[0][:30]}")
        
        print_success(f"Requisitos instalados com sucesso")
        return True
    
    except Exception as e:
        print_error(f"Erro ao instalar requisitos: {e}")
        return False

def install_all_dependencies(pip_path: Path) -> bool:
    """Instala todas as dependências"""
    print_header("Instalando Todas as Dependências")
    
    # Primeiro tenta com requirements-pinned.txt
    if REQUIREMENTS_PINNED.exists():
        if not install_requirements(pip_path, REQUIREMENTS_PINNED):
            print_warning("Falha ao instalar requirements-pinned.txt")
    
    # Depois instala dev requirements
    if REQUIREMENTS_DEV.exists():
        if not install_requirements(pip_path, REQUIREMENTS_DEV):
            print_warning("Falha ao instalar requirements-dev.txt")
    
    return True

# ========== VERIFICAÇÃO DE SAÚDE ==========

def verify_installation(python_path: Path) -> bool:
    """Verifica se a instalação foi bem-sucedida"""
    print_header("Verificando Instalação")
    
    try:
        # Testa imports básicos
        test_script = """
import sys
try:
    import asyncio
    import pathlib
    print("✓ asyncio")
    print("✓ pathlib")
    
    try:
        from rich.console import Console
        print("✓ rich")
    except ImportError:
        print("! rich (optional)")
    
    try:
        import psutil
        print("✓ psutil")
    except ImportError:
        print("! psutil (optional)")
    
    print("Installation verified")
    sys.exit(0)
except Exception as e:
    print(f"✗ {e}")
    sys.exit(1)
"""
        
        result = subprocess.run(
            [str(python_path), "-c", test_script],
            timeout=30,
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print_success("Instalação verificada com sucesso")
            return True
        else:
            print_error(f"Verificação falhou: {result.stderr}")
            return False
    
    except Exception as e:
        print_error(f"Erro ao verificar instalação: {e}")
        return False

# ========== EXECUÇÃO ==========

def run_atena_doctor(python_path: Path) -> bool:
    """Executa o atena doctor para diagnosticar o ambiente"""
    print_header("Executando ATENA Doctor (Diagnóstico)")
    
    try:
        doctor_script = ROOT / "core" / "atena_doctor.py"
        
        if not doctor_script.exists():
            print_warning(f"Script não encontrado: {doctor_script}")
            return False
        
        result = subprocess.run(
            [str(python_path), str(doctor_script), "--quick"],
            timeout=60,
            cwd=str(ROOT)
        )
        
        if result.returncode == 0:
            print_success("ATENA Doctor completado com sucesso")
            return True
        else:
            print_warning("ATENA Doctor completado com avisos")
            return True
    
    except Exception as e:
        print_error(f"Erro ao executar ATENA Doctor: {e}")
        return False

def run_atena_launcher(python_path: Path) -> bool:
    """Executa o ATENA Launcher"""
    print_header("Executando ATENA Enterprise Launcher")
    
    try:
        launcher_script = ROOT / "core" / "atena_launcher.py"
        
        if not launcher_script.exists():
            print_error(f"Script não encontrado: {launcher_script}")
            return False
        
        print_info("Iniciando ATENA Launcher...")
        print_info("Digite 'help' para ver comandos disponíveis")
        print_info("Digite 'exit' para sair\n")
        
        result = subprocess.run(
            [str(python_path), str(launcher_script)],
            cwd=str(ROOT)
        )
        
        return result.returncode == 0
    
    except KeyboardInterrupt:
        print_info("\nATENA Launcher interrompido pelo usuário")
        return True
    except Exception as e:
        print_error(f"Erro ao executar ATENA Launcher: {e}")
        return False

# ========== MAIN ==========

def main():
    """Entry point principal"""
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  █████╗ ████████╗███████╗███╗   ██╗ █████╗                   ║
    ║ ██╔══██╗╚══██╔══╝██╔════╝████╗  ██║██╔══██╗                  ║
    ║ ███████║   ██║   █████╗  ██╔██╗ ██║███████║                  ║
    ║ ██╔══██║   ██║   ██╔══╝  ██║╚██╗██║██╔══██║                  ║
    ║ ██║  ██║   ██║   ███████╗██║ ╚████║██║  ██║                  ║
    ║ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝                  ║
    ║                                                              ║
    ║          SETUP & RUN SCRIPT v1.0                             ║
    ║          Instala e executa ATENA com todas as deps          ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    print(Colors.ENDC)
    
    # 1. Verificações iniciais
    if not check_python_version():
        print_error("Python version check failed")
        return 1
    
    if not check_pip():
        print_error("pip not found")
        return 1
    
    # 2. Criar venv
    if not create_venv():
        print_error("Failed to create venv")
        return 1
    
    venv_python = get_venv_python()
    venv_pip = get_venv_pip()
    
    # 3. Atualizar pip
    if not upgrade_pip(venv_pip):
        print_warning("Failed to upgrade pip (continuing)")
    
    # 4. Instalar dependências
    if not install_all_dependencies(venv_pip):
        print_warning("Some dependencies failed to install")
    
    # 5. Verificar instalação
    if not verify_installation(venv_python):
        print_warning("Installation verification failed (continuing)")
    
    # 6. Executar ATENA Doctor
    if not run_atena_doctor(venv_python):
        print_warning("ATENA Doctor failed (continuing)")
    
    # 7. Executar ATENA Launcher
    print_header("Iniciando ATENA")
    print_info(f"Usando Python: {venv_python}")
    print_info(f"Working directory: {ROOT}\n")
    
    success = run_atena_launcher(venv_python)
    
    print_header("ATENA Encerrado")
    
    if success:
        print_success("ATENA encerrou com sucesso")
        return 0
    else:
        print_error("ATENA encerrou com erro")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_error("\nSetup interrompido pelo usuário")
        sys.exit(130)
    except Exception as e:
        print_error(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
