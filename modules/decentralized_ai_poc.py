```python
"""
PoC Python para Sistema de IA Descentralizado de NÍVEL EXTREMO (2026)
- Rede P2P dinâmica com overlay híbrido (DHT + conexões diretas)
- Nó Peer que participa do treinamento colaborativo (simulado)
- Validator que verifica computação via ZK-Proofs (simulado)
- Sincronização assíncrona de gradientes
- Defesa básica contra Sybil attacks via stake simulado e reputação
- Simulação de entrada/saída dinâmica de peers
"""

import asyncio
import hashlib
import random
import time
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# --- Utilitários ---

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def simulate_zk_proof(data: bytes) -> str:
    """
    Simula a geração de uma prova de conhecimento zero para os dados.
    Na prática, isso seria uma prova criptográfica complexa.
    Aqui, retornamos um hash como 'prova'.
    """
    return sha256(data)

def verify_zk_proof(data: bytes, proof: str) -> bool:
    """
    Simula a verificação da prova ZK.
    """
    return sha256(data) == proof

# --- DHT Overlay (simples) ---

class DHT:
    """
    Simples Distributed Hash Table para roteamento de peers.
    Usa chave SHA256 do peer_id para armazenar e localizar peers.
    """

    def __init__(self):
        # chave (hash) -> peer_id
        self.table: Dict[str, 'Peer'] = {}

    def add_peer(self, peer: 'Peer'):
        key = sha256(peer.peer_id.encode())
        self.table[key] = peer
        print(f"[DHT] Peer {peer.peer_id} adicionado com chave {key[:8]}")

    def remove_peer(self, peer: 'Peer'):
        key = sha256(peer.peer_id.encode())
        if key in self.table:
            del self.table[key]
            print(f"[DHT] Peer {peer.peer_id} removido")

    def find_peer(self, key: str) -> 'Peer':
        """
        Busca o peer mais próximo da chave dada (simplesmente hash exato ou próximo).
        """
        if key in self.table:
            return self.table[key]
        # Busca o peer com chave hash mais próxima (simples)
        keys = list(self.table.keys())
        if not keys:
            return None
        keys.sort()
        # Busca chave >= key
        for k in keys:
            if k >= key:
                return self.table[k]
        # Se não achou, retorna o primeiro (circular)
        return self.table[keys[0]]

# --- Peer ---

class Peer:
    """
    Nó da rede P2P que participa do treinamento colaborativo.
    """

    def __init__(self, peer_id: str, network: 'Network', stake: int):
        self.peer_id = peer_id
        self.network = network
        self.stake = stake  # Para defesa contra Sybil (simples)
        self.reputation = 1.0  # Inicial
        self.peers_connected: Set[str] = set()  # IDs de peers conectados diretamente
        self.local_model = 0.0  # Simples valor que representa o modelo local (ex: peso)
        self.gradient_buffer: List[float] = []
        self.running = True
        self.validator = Validator(self)
        self.lock = asyncio.Lock()

    async def join_network(self):
        """
        Entrar na rede: adiciona-se ao DHT e conecta a peers próximos.
        """
        self.network.dht.add_peer(self)
        # Conecta a peers próximos (simples: conecta a N peers aleatórios)
        peers = self.network.get_random_peers(exclude_id=self.peer_id, count=3)
        for p in peers:
            self.peers_connected.add(p.peer_id)
            p.peers_connected.add(self.peer_id)
        print(f"[Peer {self.peer_id}] Entrou na rede e conectou a {len(self.peers_connected)} peers")

    async def leave_network(self):
        """
        Sai da rede, desconectando-se.
        """
        self.running = False
        self.network.dht.remove_peer(self)
        for pid in list(self.peers_connected):
            peer = self.network.get_peer(pid)
            if peer:
                peer.peers_connected.discard(self.peer_id)
        self.peers_connected.clear()
        print(f"[Peer {self.peer_id}] Saiu da rede")

    async def train_step(self):
        """
        Simula um passo local de treinamento, produzindo um gradiente.
        """
        # Simula cálculo de gradiente (ruído + direção)
        grad = random.uniform(-0.1, 0.1) + (1.0 - self.local_model) * 0.5
        async with self.lock:
            self.gradient_buffer.append(grad)
        print(f"[Peer {self.peer_id}] Calculou gradiente {grad:.4f}")

    async def share_gradients(self):
        """
        Compartilha gradientes com peers conectados assincronamente.
        """
        async with self.lock:
            if not self.gradient_buffer:
                return
            grad = sum(self.gradient_buffer) / len(self.gradient_buffer)
            self.gradient_buffer.clear()
        # Simula prova ZK da computação do gradiente
        grad_bytes = str(grad).encode()
        proof = simulate_zk_proof(grad_bytes)
        # Envia para peers conectados
        for pid in self.peers_connected:
            peer = self.network.get_peer(pid)
            if peer:
                await peer.receive_gradient(self.peer_id, grad, proof)

    async def receive_gradient(self, from_peer_id: str, grad: float, proof: str):
        """
        Recebe gradiente de outro peer, valida via Validator.
        """
        # Valida stake e reputação para defesa Sybil
        sender = self.network.get_peer(from_peer_id)
        if not sender:
            print(f"[Peer {self.peer_id}] Recebeu gradiente de peer desconhecido {from_peer_id}")
            return
        if sender.stake < self.network.min_stake:
            print(f"[Peer {self.peer_id}] Rejeitou gradiente de {from_peer_id} por stake insuficiente")
            return
        # Validação ZK
        grad_bytes = str(grad).encode()
        if not self.validator.validate_computation(grad_bytes, proof):
            print(f"[Peer {self.peer_id}] Rejeitou gradiente de {from_peer_id} por prova inválida")
            sender.reputation *= 0.9  # Penaliza reputação
            return
        # Aceita e atualiza modelo local (simples média ponderada pela reputação)
        weight = sender.reputation
        async with self.lock:
            old_model = self.local_model
            self.local_model = (self.local_model + grad * weight) / (1 + weight)
        print(f"[Peer {self.peer_id}] Atualizou modelo de