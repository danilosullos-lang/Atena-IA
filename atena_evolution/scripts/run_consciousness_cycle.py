#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atena_evolution.consciousness.cli import run_once

if __name__ == "__main__":
    db_path = Path("consciousness_history.db")
    result = asyncio.run(run_once(output_json=True, save_db=True, db_path=db_path))
    # O resultado JSON já é gerado internamente pelo --json, mas podemos garantir
    import json
    with open("atena_consciousness_cycle.json", "w") as f:
        json.dump(result.model_dump(mode='json'), f, indent=2)
    sys.exit(0)
