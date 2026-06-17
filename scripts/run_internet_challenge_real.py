import sys
import os
import json
from datetime import datetime

# Adiciona o diretório raiz ao PYTHONPATH
sys.path.append(os.getcwd())

from core.internet_challenge import run_internet_challenge

def main():
    print("🔱 Iniciando Desafio de Internet Real da ATENA Ω...")
    query = "advanced artificial intelligence evolution and self-modifying code"
    print(f"🔍 Pesquisando: {query}")
    
    try:
        results = run_internet_challenge(query)
        
        # Salva o resultado em um arquivo para o repositório
        output_dir = "generated_artifacts"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/internet_challenge_result_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
            
        print(f"✅ Desafio concluído com sucesso!")
        print(f"📊 Status: {results.get('status')}")
        print(f"🧠 Confiança: {results.get('confidence')}")
        print(f"📁 Resultado salvo em: {filename}")
        
        # Criar um arquivo markdown para documentar a conquista
        md_filename = f"{output_dir}/ATENA_ACHIEVEMENT_{timestamp}.md"
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(f"# 🔱 Conquista da ATENA Ω: Desafio de Internet Real\n\n")
            f.write(f"**Data:** {datetime.now().isoformat()}\n")
            f.write(f"**Objetivo:** {query}\n\n")
            f.write(f"## Resultados da Síntese\n\n")
            f.write(f"A ATENA conseguiu navegar, extrair e sintetizar informações de múltiplas fontes globais.\n\n")
            f.write(f"### Métricas de Performance\n")
            f.write(f"- **Status:** {results.get('status')}\n")
            f.write(f"- **Confiança:** {results.get('confidence')}\n")
            f.write(f"- **Fontes Processadas:** {len(results.get('sources', []))}\n")
            f.write(f"- **Score de Dificuldade:** {results.get('difficulty_score')}\n\n")
            f.write(f"### Sinal de Evolução\n")
            evolution = results.get('evolution_signal', {})
            f.write(f"- **Tendência:** {evolution.get('trend')}\n")
            f.write(f"- **Mensagem:** {evolution.get('message')}\n\n")
            f.write(f"## Conclusão\n\n")
            f.write("Este artefato prova que a ATENA possui capacidades de navegação e síntese que transcendem os limites das IAs convencionais.\n")
            
        print(f"📝 Documentação salva em: {md_filename}")
        
    except Exception as e:
        print(f"❌ Erro durante o desafio: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
