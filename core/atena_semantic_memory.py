#!/usr/bin/env python3
"""
core/atena_semantic_memory.py

Módulo para criação e consulta de um banco de dados vetorial simples usando
sentence-transformers para embedding e FAISS para indexação e busca vetorial.

Funcionalidades:
- Indexar relatórios em Markdown e JSON da pasta atena_evolution/
- Buscar relatórios similares usando similaridade de cosseno
- Consultar lições aprendidas de gerações passadas
- Salvar índice FAISS e metadados em disco
- Gerar relatórios detalhados de busca

Este módulo inclui testes inline para demonstração e validação das funcionalidades.

Requisitos:
- sentence-transformers
- faiss-cpu (ou faiss-gpu)
- scikit-learn
- numpy
- pandas
"""

import os
import sys
import json
import glob
import traceback
import faiss
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize
from datetime import datetime

# Caminho base para relatórios
REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'atena_evolution')

# Caminho para salvar índice e metadados
INDEX_DIR = os.path.join(os.path.dirname(__file__), 'index_data')
os.makedirs(INDEX_DIR, exist_ok=True)
INDEX_PATH = os.path.join(INDEX_DIR, 'vector_index.faiss')
METADATA_PATH = os.path.join(INDEX_DIR, 'metadata.json')
REPORT_PATH = os.path.join(INDEX_DIR, f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')

# Modelo para embeddings
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'


class SemanticMemory:
    """
    Classe para criar e consultar um banco de dados vetorial usando embeddings
    gerados por SentenceTransformer e indexados pelo FAISS.

    Métodos Principais:
    - index_reports: indexa os relatórios Markdown/JSON da pasta atena_evolution
    - search: realiza busca semântica por similaridade de cosseno
    - save_index: salva índice FAISS e metadados em disco
    - load_index: carrega índice FAISS e metadados de disco
    - generate_report: gera um relatório detalhado das buscas realizadas
    """

    def __init__(self, embedding_model_name: str = EMBEDDING_MODEL_NAME):
        """
        Inicializa o SemanticMemory carregando o modelo de embeddings e preparando
        estruturas para indexação e metadados.
        """
        try:
            self.model = SentenceTransformer(embedding_model_name)
        except Exception as e:
            print(f'Erro ao carregar modelo {embedding_model_name}: {e}')
            raise

        self.embeddings = None  # np.ndarray shape=(N, dim)
        self.metadata = []      # Lista de dicts com informações dos documentos
        self.index = None       # FAISS index
        self.dimension = self.model.get_sentence_embedding_dimension()

        # Controle para relatório detalhado
        self.search_history = []

    def _load_reports(self, directory: str) -> List[Dict]:
        """
        Carrega e extrai textos dos relatórios Markdown e JSON da pasta especificada.

        Retorna uma lista de dicionários com:
        - 'id': id único (caminho relativo)
        - 'text': conteúdo textual concatenado do relatório
        - 'type': 'md' ou 'json'
        - 'filename': nome do arquivo
        - 'generation': extraído do nome/pasta do arquivo se possível
        """
        reports = []
        md_files = glob.glob(os.path.join(directory, '**/*.md'), recursive=True)
        json_files = glob.glob(os.path.join(directory, '**/*.json'), recursive=True)

        # Função interna para extrair texto de JSON (tenta extrair campos textuais relevantes)
        def extract_text_from_json(filepath: str) -> str:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                texts = []

                def recurse_extract(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            recurse_extract(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            recurse_extract(item)
                    elif isinstance(obj, str):
                        texts.append(obj)
                    else:
                        pass

                recurse_extract(data)
                return ' '.join(texts)
            except Exception:
                # fallback para leitura crua
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    return ''

        # Carregar MD
        for filepath in md_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                rel_path = os.path.relpath(filepath, directory)
                gen = self._extract_generation_from_path(rel_path)
                reports.append({
                    'id': rel_path,
                    'text': text,
                    'type': 'md',
                    'filename': os.path.basename(filepath),
                    'generation': gen
                })
            except Exception as e:
                print(f'Erro ao carregar arquivo MD {filepath}: {e}')
                continue

        # Carregar JSON
        for filepath in json_files:
            try:
                text = extract_text_from_json(filepath)
                rel_path = os.path.relpath(filepath, directory)
                gen = self._extract_generation_from_path(rel_path)
                reports.append({
                    'id': rel_path,
                    'text': text,
                    'type': 'json',
                    'filename': os.path.basename(filepath),
                    'generation': gen
                })
            except Exception as e:
                print(f'Erro ao carregar arquivo JSON {filepath}: {e}')
                continue

        return reports

    def _extract_generation_from_path(self, path: str) -> Optional[int]:
        """
        Tenta extrair número da geração a partir do caminho do arquivo.
        Exemplo: 'generation_345/report.md' -> 345
        """
        import re
        match = re.search(r'generation[_\-]?(\d+)', path, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
        return None

    def index_reports(self, directory: str = REPORTS_DIR) -> None:
        """
        Indexa os relatórios presentes na pasta especificada.
        Gera embeddings, normaliza-os e cria índice FAISS para busca por similaridade de cosseno.
        """
        try:
            reports = self._load_reports(directory)
            if not reports:
                raise RuntimeError(f'Nenhum relatório encontrado em {directory} para indexar.')

            texts = [r['text'] for r in reports]

            # Gera embeddings
            print('Gerando embeddings para os relatórios...')
            embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=True, batch_size=16)

            # Normaliza embeddings para similaridade de cosseno com FAISS L2
            embeddings = normalize(embeddings, norm='l2', axis=1)

            self.embeddings = embeddings.astype('float32')
            self.metadata = reports

            # Cria índice FAISS (IndexFlatIP para similaridade de cosseno com vetores normalizados)
            self.index = faiss.IndexFlatIP(self.dimension)
            self.index.add(self.embeddings)
            print(f'Indexação concluída: {self.index.ntotal} vetores indexados.')
        except Exception as e:
            print(f'Erro durante indexação: {e}')
            traceback.print_exc()
            raise

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Realiza busca semântica no índice usando similaridade de cosseno.

        Parâmetros:
        - query: string de consulta
        - top_k: número de resultados mais similares a retornar

        Retorna lista de dicts contendo:
        - 'id', 'filename', 'generation', 'text' (preview), 'score'
        """
        if self.index is None or self.embeddings is None:
            raise RuntimeError('Índice não carregado ou vazio. Execute index_reports() ou load_index() antes da busca.')

        try:
            q_emb = self.model.encode([query], convert_to_numpy=True)
            q_emb = normalize(q_emb, norm='l2', axis=1).astype('float32')

            distances, indices = self.index.search(q_emb, top_k)
            results = []
            for score, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                meta = self.metadata[idx]
                preview = meta['text'][:500].replace('\n', ' ').replace('\r', ' ')
                results.append({
                    'id': meta['id'],
                    'filename': meta['filename'],
                    'generation': meta['generation'],
                    'preview': preview,
                    'score': float(score)
                })

            # Armazena histórico de busca para relatório
            self.search_history.append({
                'query': query,
                'top_k': top_k,
                'results': results,
                'timestamp': datetime.now().isoformat()
            })

            return results
        except Exception as e:
            print(f'Erro durante busca: {e}')
            traceback.print_exc()
            raise

    def save_index(self, index_path: Optional[str] = None, metadata_path: Optional[str] = None) -> None:
        """
        Salva o índice FAISS e metadados em disco.
        """
        index_path = index_path or INDEX_PATH
        metadata_path = metadata_path or METADATA_PATH
        try:
            if self.index is None:
                raise RuntimeError('Nenhum índice para salvar.')

            faiss.write_index(self.index, index_path)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            print(f'Índice salvo em {index_path}')
            print(f'Metadados salvos em {metadata_path}')
        except Exception as e:
            print(f'Erro ao salvar índice/metadados: {e}')
            traceback.print_exc()
            raise

    def load_index(self, index_path: Optional[str] = None, metadata_path: Optional[str] = None) -> None:
        """
        Carrega índice FAISS e metadados de disco.
        """
        index_path = index_path or INDEX_PATH
        metadata_path = metadata_path or METADATA_PATH
        try:
            self.index = faiss.read_index(index_path)
            with open(metadata_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            # Verifica dimensão do índice e atualiza self.dimension
            self.dimension = self.index.d
            print(f'Índice carregado de {index_path} com {self.index.ntotal} vetores.')
        except Exception as e:
            print(f'Erro ao carregar índice/metadados: {e}')
            traceback.print_exc()
            raise

    def generate_report(self, report_path: Optional[str] = None) -> None:
        """
        Gera um relatório JSON detalhado das buscas realizadas e salva em disco.
        """
        report_path = report_path or REPORT_PATH
        try:
            report_data = {
                'generated_at': datetime.now().isoformat(),
                'embedding_model': EMBEDDING_MODEL_NAME,
                'index_size': self.index.ntotal if self.index else 0,
                'searches': self.search_history
            }
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            print(f'Relatório de buscas salvo em {report_path}')
        except Exception as e:
            print(f'Erro ao gerar relatório: {e}')
            traceback.print_exc()
            raise


def _run_tests():
    """
    Testes inline para validar funcionalidades do SemanticMemory.
    """
    print('Iniciando testes do módulo atena_semantic_memory.py')

    sm = SemanticMemory()

    # Test 1: Indexar relatórios (espera-se que existam arquivos em ./../atena_evolution)
    try:
        sm.index_reports()
        assert sm.index is not None
        assert sm.index.ntotal > 0
        print('Test 1: Indexação - OK')
    except Exception as e:
        print('Test 1: Indexação - FALHOU')
        print(e)
        sys.exit(1)

    # Test 2: Realizar busca com query simples
    query = 'lições aprendidas da geração 345'
    try:
        results = sm.search(query, top_k=3)
        assert isinstance(results, list)
        assert len(results) <= 3
        for r in results:
            assert 'id' in r and 'score' in r and 'preview' in r
        print(f'Test 2: Busca - OK - Encontrados {len(results)} resultados')
    except Exception as e:
        print('Test 2: Busca - FALHOU')
        print(e)
        sys.exit(1)

    # Test 3: Salvar índice e metadados
    try:
        sm.save_index()
        assert os.path.exists(INDEX_PATH)
        assert os.path.exists(METADATA_PATH)
        print('Test 3: Salvamento índice/metadados - OK')
    except Exception as e:
        print('Test 3: Salvamento índice/metadados - FALHOU')
        print(e)
        sys.exit(1)

    # Test 4: Carregar índice e metadados e repetir busca
    try:
        sm2 = SemanticMemory()
        sm2.load_index()
        results2 = sm2.search(query, top_k=2)
        assert len(results2) > 0
        print('Test 4: Carregamento índice/metadados e busca - OK')
    except Exception as e:
        print('Test 4: Carregamento índice/metadados - FALHOU')
        print(e)
        sys.exit(1)

    # Test 5: Gerar relatório JSON
    try:
        sm.generate_report()
        assert os.path.exists(REPORT_PATH)
        print('Test 5: Geração de relatório JSON - OK')
    except Exception as e:
        print('Test 5: Geração de relatório JSON - FALHOU')
        print(e)
        sys.exit(1)

    print('Todos os testes concluídos com sucesso.')


if __name__ == '__main__':
    _run_tests()
