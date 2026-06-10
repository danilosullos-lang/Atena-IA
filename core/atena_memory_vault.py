#!/usr/bin/env python3
import os
import json
import glob
import datetime
import shutil
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
import threading
import tempfile
import traceback

# Diretório base para salvar os modelos
BASE_DIR = os.path.join("atena_evolution", "knowledge", "vault")

# Thread lock para garantir operações atômicas em disco
_lock = threading.Lock()


@dataclass
class ModelMetadata:
    timestamp: str
    loss: float
    accuracy: float
    extra: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp
        return d


class AtenaMemoryVault:
    """
    Gerencia a persistência e versionamento de modelos de IA.
    Modelos são salvos como diretórios contendo:
        - model.json (dados do modelo)
        - weights.bin (pesos binários)
        - metadata.json (informações da performance)
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or BASE_DIR
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_model_dirname(self, timestamp: str) -> str:
        # Pasta nomeada por timestamp para versionamento
        return os.path.join(self.base_dir, f"model_{timestamp}")

    def save_model(self,
                   model_data: Dict[str, Any],
                   weights_data: bytes,
                   loss: float,
                   accuracy: float,
                   extra_metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Salva um modelo com seus dados e pesos, versionando com timestamp e metadados.
        Retorna o path do diretório salvo.
        """
        if extra_metadata is None:
            extra_metadata = {}
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")

        model_dir = self._get_model_dirname(timestamp)

        # Lock para não ocorrer conflito em salvamentos simultâneos
        with _lock:
            if os.path.exists(model_dir):
                raise FileExistsError(f"Model directory already exists: {model_dir}")
            os.makedirs(model_dir, exist_ok=False)

            try:
                # Salva model.json
                model_json_path = os.path.join(model_dir, "model.json")
                with open(model_json_path, "w", encoding="utf-8") as f:
                    json.dump(model_data, f, indent=2)

                # Salva weights.bin
                weights_path = os.path.join(model_dir, "weights.bin")
                with open(weights_path, "wb") as f:
                    f.write(weights_data)

                # Salva metadata.json
                metadata = ModelMetadata(timestamp=timestamp,
                                         loss=loss,
                                         accuracy=accuracy,
                                         extra=extra_metadata)
                metadata_path = os.path.join(model_dir, "metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata.to_dict(), f, indent=2)

            except Exception as e:
                # Em caso de erro ao salvar, tenta remover pasta incompleta
                shutil.rmtree(model_dir, ignore_errors=True)
                raise RuntimeError(f"Erro ao salvar modelo: {e}") from e

        return model_dir

    def list_models(self) -> List[Tuple[str, ModelMetadata]]:
        """
        Lista todos os modelos disponíveis, retornando lista de tuplas (model_dir, ModelMetadata).
        Ordenado do mais recente para o mais antigo.
        """
        model_dirs = glob.glob(os.path.join(self.base_dir, "model_*"))
        models = []
        for d in model_dirs:
            metadata_path = os.path.join(d, "metadata.json")
            if not os.path.isfile(metadata_path):
                continue
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    md = json.load(f)
                metadata = ModelMetadata(timestamp=md["timestamp"],
                                         loss=float(md["loss"]),
                                         accuracy=float(md["accuracy"]),
                                         extra=md.get("extra", {}))
                models.append((d, metadata))
            except Exception:
                # Ignora modelos com metadata inválida
                continue
        # Ordena pelo timestamp decrescente
        models.sort(key=lambda x: x[1].timestamp, reverse=True)
        return models

    def load_best_model(self) -> Optional[Tuple[Dict[str, Any], bytes, ModelMetadata]]:
        """
        Carrega o modelo com a menor loss registrada.
        Retorna (model_data, weights_data, metadata) ou None se não houver modelos.
        """
        models = self.list_models()
        if not models:
            return None
        # Escolhe o modelo com menor loss
        best_dir, best_metadata = min(models, key=lambda x: x[1].loss)

        try:
            model_json_path = os.path.join(best_dir, "model.json")
            with open(model_json_path, "r", encoding="utf-8") as f:
                model_data = json.load(f)

            weights_path = os.path.join(best_dir, "weights.bin")
            with open(weights_path, "rb") as f:
                weights_data = f.read()

            return model_data, weights_data, best_metadata

        except Exception as e:
            raise RuntimeError(f"Erro ao carregar modelo {best_dir}: {e}") from e


def _run_tests():
    """
    Testes inline para verificar funcionamento do módulo.
    """

    import random
    import pprint
    import csv

    print("=== Iniciando testes do AtenaMemoryVault ===")

    vault = AtenaMemoryVault()

    # Limpa vault para testes (cuidado: apaga modelos existentes)
    dirs = glob.glob(os.path.join(vault.base_dir, "model_*"))
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)

    print("Diretório vault limpo.")

    # Cria e salva 5 modelos simulados com dados aleatórios
    print("Salvando 5 modelos simulados...")

    saved_models = []
    for i in range(5):
        model_data = {
            "layers": [
                {"type": "Dense", "units": 64, "activation": "relu"},
                {"type": "Dense", "units": 10, "activation": "softmax"}
            ],
            "description": f"Modelo simulado {i}"
        }
        weights_data = os.urandom(1024)  # 1KB de pesos aleatórios

        loss = random.uniform(0.05, 0.5)
        accuracy = random.uniform(0.5, 0.99)

        extra = {
            "epoch": i + 1,
            "notes": f"Teste modelo {i}"
        }

        model_dir = vault.save_model(model_data, weights_data, loss, accuracy, extra)
        saved_models.append((model_dir, loss, accuracy))
        print(f"Modelo {i} salvo em {model_dir} com loss={loss:.4f} accuracy={accuracy:.4f}")

    # Verifica listagem
    print("\nListando modelos disponíveis:")
    models_listed = vault.list_models()
    for d, md in models_listed:
        print(f" - {os.path.basename(d)}: loss={md.loss:.4f}, accuracy={md.accuracy:.4f}, timestamp={md.timestamp}")

    # Carrega o melhor modelo
    print("\nCarregando o melhor modelo (menor loss)...")
    best = vault.load_best_model()
    assert best is not None, "Não foi possível carregar o melhor modelo"
    best_model_data, best_weights_data, best_metadata = best
    print(f"Melhor modelo carregado: loss={best_metadata.loss:.4f}, accuracy={best_metadata.accuracy:.4f}, timestamp={best_metadata.timestamp}")
    print(f"Descrição do modelo: {best_model_data.get('description', 'N/A')}")
    print(f"Tamanho dos pesos carregados: {len(best_weights_data)} bytes")

    # Salvando relatório em CSV
    report_csv_path = os.path.join(vault.base_dir, "model_report.csv")
    with open(report_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Model Directory", "Timestamp", "Loss", "Accuracy", "Extra Metadata"])
        for d, md in models_listed:
            writer.writerow([os.path.basename(d), md.timestamp, f"{md.loss:.6f}", f"{md.accuracy:.6f}", json.dumps(md.extra)])

    print(f"\nRelatório CSV salvo em: {report_csv_path}")

    # Salvando relatório JSON
    report_json_path = os.path.join(vault.base_dir, "model_report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump([{ "model_dir": os.path.basename(d),
                     "timestamp": md.timestamp,
                     "loss": md.loss,
                     "accuracy": md.accuracy,
                     "extra": md.extra} for d, md in models_listed], f, indent=2)
    print(f"Relatório JSON salvo em: {report_json_path}")

    print("\n=== Testes concluídos com sucesso ===")


if __name__ == "__main__":
    try:
        _run_tests()
    except Exception as e:
        print("Erro durante os testes:")
        traceback.print_exc()
        exit(1)
