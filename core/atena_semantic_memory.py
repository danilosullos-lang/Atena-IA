.*?
rt os
import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from pathlib import Path

class AtenaSemanticMemory:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.documents = []
        self.index_path = "atena_evolution/knowledge/semantic_index.faiss"
        self.docs_path = "atena_evolution/knowledge/semantic_docs.json"
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.load_index()

    def index_reports(self, directory="atena_evolution"):
        texts = []
        for path in Path(directory).rglob('*'):
            if path.suffix in ['.md', '.json'] and path.is_file():
                try:
                    content = path.read_text(encoding='utf-8')
                    texts.append({"path": str(path), "content": content[:1000]})
                except: continue
        
        if not texts: return
        
        embeddings = self.model.encode([t['content'] for t in texts])
        dimension = embeddings.shape[1]
        
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
        self.documents = texts
        self.save_index()

    def save_index(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.docs_path, 'w') as f:
            json.dump(self.documents, f)

    def load_index(self):
        if os.path.exists(self.index_path) and os.path.exists(self.docs_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.docs_path, 'r') as f:
                self.documents = json.load(f)

    def search(self, query, k=3):
        if self.index is None: return []
        query_vector = self.model.encode([query])
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), k)
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx < len(self.documents):
                results.append(self.documents[idx])
        return results

if __name__ == "__main__":
    memory = AtenaSemanticMemory()
    memory.index_reports()
    print("Memória Semântica Indexada.")
