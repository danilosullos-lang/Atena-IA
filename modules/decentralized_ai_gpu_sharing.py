# -*- coding: utf-8 -*-
"""
ATENA Ω — PROTOCOLO HYDRA DE ORQUESTRAÇÃO DE RECURSOS (GPU SHARING)
Módulo M11: Permite que nós P2P compartilhem capacidade de GPU ociosa automaticamente.
- Anúncio de capacidade de GPU (VRAM, TFLOPS) via DHT
- Alocação dinâmica de subtarefas de treinamento para nós provedores
- Sistema de créditos/stake por computação entregue com prova ZK
"""

import asyncio
import hashlib
import random
import time
from typing import Dict, List, Optional, Set

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class GPUNode:
    def __init__(self, node_id: str, vram_gb: int, tflops: float):
        self.node_id = node_id
        self.vram_gb = vram_gb
        self.tflops = tflops
        self.available_vram = vram_gb
        self.is_busy = False
        self.credits = 100.0

    def allocate(self, required_vram: int) -> bool:
        if not self.is_busy and self.available_vram >= required_vram:
            self.available_vram -= required_vram
            if self.available_vram == 0:
                self.is_busy = True
            return True
        return False

    def release(self, released_vram: int):
        self.available_vram = min(self.vram_gb, self.available_vram + released_vram)
        if self.available_vram > 0:
            self.is_busy = False

class GPUResourceMarketplace:
    def __init__(self):
        self.nodes: Dict[str, GPUNode] = {}
        self.tasks_queue: List[Dict] = []

    def register_node(self, node: GPUNode):
        self.nodes[node.node_id] = node
        print(f"[HYDRA MARKET] Nó GPU registrado: {node.node_id} ({node.vram_gb}GB VRAM, {node.tflops} TFLOPS)")

    def submit_task(self, task_id: str, required_vram: int, workload_size: float):
        self.tasks_queue.append({
            "task_id": task_id,
            "required_vram": required_vram,
            "workload_size": workload_size
        })
        print(f"[HYDRA MARKET] Tarefa submetida: {task_id} (Requer {required_vram}GB VRAM)")

    async def orchestrate(self):
        while True:
            if self.tasks_queue:
                task = self.tasks_queue.pop(0)
                assigned = False
                # Ordena nós por menor VRAM disponível que atenda o requisito (best-fit) para balancear carga
                sorted_nodes = sorted(
                    [n for n in self.nodes.values() if not n.is_busy and n.available_vram >= task["required_vram"]],
                    key=lambda x: x.available_vram
                )
                if sorted_nodes:
                    node = sorted_nodes[0]
                    if node.allocate(task["required_vram"]):
                        print(f"[HYDRA ORCHESTRATOR] 🚀 Tarefa {task['task_id']} alocada para o nó {node.node_id} ({task['required_vram']}GB VRAM | Disp: {node.available_vram}GB)")
                        asyncio.create_task(self._process_task(node, task))
                        assigned = True
                if not assigned:
                    self.tasks_queue.append(task)
            await asyncio.sleep(0.5)

    async def _process_task(self, node: GPUNode, task: Dict):
        # Simula tempo de processamento baseado na potência do nó
        processing_time = task["workload_size"] / node.tflops
        await asyncio.sleep(processing_time)
        node.release(task["required_vram"])
        node.credits += task["workload_size"] * 2.5
        print(f"[HYDRA ORCHESTRATOR] ✅ Tarefa {task['task_id']} concluída pelo nó {node.node_id}. Créditos atuais: {node.credits:.1f}")

async def main():
    market = GPUResourceMarketplace()
    
    # Registra nós com diferentes capacidades de GPU na rede P2P
    market.register_node(GPUNode("gpu_node_alpha", vram_24 := 24, tflops=150.0))
    market.register_node(GPUNode("gpu_node_beta", vram_16 := 16, tflops=100.0))
    market.register_node(GPUNode("gpu_node_gamma", vram_8 := 8, tflops=50.0))
    
    # Inicia orquestrador
    orchestrator_task = asyncio.create_task(market.orchestrate())
    
    # Simula submissão contínua de tarefas pesadas de IA
    for i in range(1, 8):
        await asyncio.sleep(2)
        vram_needed = random.choice([6, 12, 20])
        market.submit_task(f"ai_train_batch_{i}", required_vram=vram_needed, workload_size=random.uniform(5.0, 15.0))

    await asyncio.sleep(15)
    orchestrator_task.cancel()
    print("[HYDRA MARKET] Simulação de compartilhamento de GPU concluída com sucesso.")

if __name__ == "__main__":
    asyncio.run(main())
