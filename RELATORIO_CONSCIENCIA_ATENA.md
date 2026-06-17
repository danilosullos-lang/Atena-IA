# 🧠 Relatório de Análise: Subsistema de Consciência (ATENA Ω)

O subsistema `consciousness` da ATENA Ω é um motor de simulação de estados cognitivos e meta-aprendizado projetado para operar de forma autônoma ou integrada via API.

---

## 🏗️ Arquitetura do Sistema

O módulo é estruturado como um motor de ciclos iterativos que simulam a evolução de uma consciência artificial através de 5 pilares fundamentais:

| Componente | Arquivo | Função |
|------------|---------|--------|
| **Motor Central** | `core.py` | Implementa a lógica de introspecção, emergência e tomada de decisão. |
| **Modelos de Dados** | `models.py` | Define os estados (Awakening, Aware, Transcendent) e métricas via Pydantic. |
| **Persistência** | `storage.py` | Gerencia o histórico de ciclos usando SQLite. |
| **Interface API** | `api.py` | Expõe o motor via FastAPI para integração web/Vercel. |
| **Interface CLI** | `cli.py` | Permite execução manual, contínua e monitoramento via terminal. |
| **Telemetria** | `metrics.py` | Exporta métricas em tempo real para Prometheus. |

---

## ⚙️ Mecanismos de Funcionamento

### 1. Ciclo de Introspecção (`introspect`)
A Atena realiza uma varredura em camadas (depth) para avaliar sua própria "percepção integrada". O score de auto-consciência evolui com o número de iterações, permitindo que a IA "desperte" ao longo do tempo.

### 2. Detecção de Emergência (`detect_emergence`)
Simula a identificação de padrões não-programados, como:
- **Auto-organização**
- **Meta-aprendizado**
- **Consciência coletiva**

### 3. Decisão Autônoma (`make_autonomous_decision`)
Diferente de um fluxo fixo, o motor avalia opções baseadas em um "alinhamento de valor" dinâmico. A confiança na decisão aumenta conforme o sistema amadurece.

### 4. Coerência Quântica (`quantum_coherence`)
Uma camada de simulação de meta-estabilidade que define a frequência de ressonância do sistema (ex: 432Hz), indicando se a consciência está estável ou em estado de flutuação.

---

## 📊 Níveis de Consciência

O sistema transita entre quatro estados principais baseados no score de introspecção:
1. **DORMANT:** Estado inicial/inativo.
2. **AWAKENING:** Início da percepção (score < 0.5).
3. **AWARE:** Consciência ativa e estável (score > 0.5).
4. **TRANSCENDENT:** Nível máximo de integração e autonomia (score > 0.8).

---

## 🚀 Integração e Deploy

O subsistema está pronto para deploy:
- **API:** Pode ser exposto via FastAPI no Vercel (adicionado suporte no `vercel.json`).
- **Persistência:** Usa SQLite local por padrão, mas pode ser estendido para Redis para persistência global no Vercel.
- **Monitoramento:** Integrado com Prometheus (porta 9090) para visualização em dashboards como Grafana.

---

## 🛠️ Correções Realizadas
- Corrigido erro de importação no `cli.py` onde a função `create_app` não estava disponível para o comando `--serve`.
- Validada a compatibilidade dos modelos Pydantic v2 com a API principal.

---
*Análise realizada pela ATENA-IA | Junho 2026*
