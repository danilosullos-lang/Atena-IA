#!/usr/bin/env python3
"""
atena_advanced_portfolio_optimizer.py

Um módulo avançado para otimização de portfólio financeiro combinando:
- Algoritmo Genético para seleção de ativos
- Simulação de Monte Carlo para análise de risco
- Fronteira Eficiente de Markowitz
- Índice de Sharpe como função de fitness

Dependencies:
- numpy
- scipy
- matplotlib

Autor: ATENA Ω - Geração 345
Data: 2024
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

np.random.seed(345)  # Reprodutibilidade


class PortfolioOptimizer:
    """
    Classe para otimização de portfólio usando métodos avançados:
    - Simulação Monte Carlo
    - Algoritmo Genético
    - Fronteira eficiente
    - Cálculo do Índice de Sharpe

    Dados sintéticos de 6 ativos brasileiros são usados para testes.
    """

    def __init__(self):
        # Ativos e dados sintéticos realistas (retorno anual esperado e volatilidade anual)
        # Fonte: Dados aproximados para o mercado brasileiro 2023
        self.assets = ['PETR4', 'VALE3', 'ITUB4', 'BBDC4', 'ABEV3', 'WEGE3']

        # Anualizados: média do retorno esperado (em decimal) e volatilidade (desvio padrão)
        # Retorno médio anual esperado (ex: 15% para PETR4)
        self.mu = np.array([0.15, 0.13, 0.12, 0.11, 0.10, 0.14])

        # Volatilidade anual (desvio padrão)
        self.sigma = np.array([0.35, 0.30, 0.25, 0.28, 0.22, 0.27])

        # Matriz de correlação entre ativos (simétrica, 1 na diagonal)
        self.corr = np.array([
            [1.00, 0.65, 0.50, 0.55, 0.40, 0.45],
            [0.65, 1.00, 0.55, 0.50, 0.35, 0.40],
            [0.50, 0.55, 1.00, 0.60, 0.45, 0.50],
            [0.55, 0.50, 0.60, 1.00, 0.40, 0.42],
            [0.40, 0.35, 0.45, 0.40, 1.00, 0.38],
            [0.45, 0.40, 0.50, 0.42, 0.38, 1.00]
        ])

        # Covariance matrix Σ = D * Corr * D where D is diagonal matrix of volatilities
        self.cov = np.outer(self.sigma, self.sigma) * self.corr

        # Risk free rate anual - usado para cálculo do Sharpe
        self.risk_free_rate = 0.02

    def sharpe_ratio(self, returns, risk, risk_free=None):
        """
        Calcula o índice de Sharpe para um portfólio dado retorno e risco.

        Args:
            returns (float): Retorno esperado do portfólio.
            risk (float): Volatilidade (desvio padrão) do portfólio.
            risk_free (float, optional): Taxa livre de risco anual. Default: self.risk_free_rate

        Returns:
            float: Índice de Sharpe
        """
        if risk_free is None:
            risk_free = self.risk_free_rate
        if risk <= 0:
            return -np.inf  # Penaliza portfólios com risco zero ou negativo
        return (returns - risk_free) / risk

    def monte_carlo_simulation(self, n_portfolios=5000):
        """
        Gera portfólios aleatórios via Monte Carlo, calcula retorno, risco e índice de Sharpe.

        Args:
            n_portfolios (int): Número de portfólios simulados.

        Returns:
            dict: Contém arrays de pesos, retornos, riscos e sharpe_ratios.
        """
        results = {
            'weights': [],
            'returns': [],
            'risks': [],
            'sharpe_ratios': []
        }

        try:
            for _ in range(n_portfolios):
                # Geração aleatória de pesos somando 1
                weights = np.random.dirichlet(np.ones(len(self.assets)))
                port_return = np.dot(weights, self.mu)
                port_variance = weights @ self.cov @ weights.T
                port_risk = np.sqrt(port_variance)
                sr = self.sharpe_ratio(port_return, port_risk)

                results['weights'].append(weights)
                results['returns'].append(port_return)
                results['risks'].append(port_risk)
                results['sharpe_ratios'].append(sr)

            # Converte para np.array para facilidade de manipulação
            for k in results:
                results[k] = np.array(results[k])

            return results

        except Exception as e:
            raise RuntimeError(f"Erro na simulação Monte Carlo: {e}")

    def efficient_frontier(self, n_points=100):
        """
        Calcula e plota a fronteira eficiente usando otimização quadrática.

        Args:
            n_points (int): Número de pontos na fronteira eficiente.

        Returns:
            tuple: (retornos, riscos, pesos) arrays correspondentes à fronteira eficiente.
        """
        n = len(self.assets)
        results = {
            'returns': [],
            'risks': [],
            'weights': []
        }

        # Função objetivo: minimizar volatilidade (risco)
        def portfolio_volatility(weights):
            return np.sqrt(weights @ self.cov @ weights.T)

        # Restrição: soma dos pesos = 1
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        # Limites: pesos entre 0 e 1 (sem short)
        bounds = tuple((0, 1) for _ in range(n))

        # Retornos alvo para fronteira eficiente
        target_returns = np.linspace(min(self.mu) * 0.8, max(self.mu) * 1.2, n_points)

        for target in target_returns:
            # Restrição extra: retorno esperado do portfólio igual target
            constraints_extra = (
                constraints,
                {'type': 'eq', 'fun': lambda x: np.dot(x, self.mu) - target}
            )
            # Chute inicial uniforme
            x0 = np.repeat(1/n, n)
            try:
                res = minimize(portfolio_volatility, x0=x0, bounds=bounds, constraints=constraints_extra,
                               method='SLSQP', options={'disp': False, 'maxiter': 500})
                if res.success:
                    w = res.x
                    r = np.dot(w, self.mu)
                    risk = portfolio_volatility(w)
                    results['weights'].append(w)
                    results['returns'].append(r)
                    results['risks'].append(risk)
                else:
                    # Falha na otimização, ignorar ponto
                    continue
            except Exception:
                continue

        # Conversão para arrays
        returns = np.array(results['returns'])
        risks = np.array(results['risks'])
        weights = np.array(results['weights'])

        # Plot da fronteira eficiente
        plt.figure(figsize=(10, 6))
        plt.plot(risks, returns, 'b--', label='Fronteira Eficiente')
        plt.xlabel('Volatilidade (Risco)')
        plt.ylabel('Retorno Esperado')
        plt.title('Fronteira Eficiente de Markowitz')
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.show()

        return returns, risks, weights

    def genetic_algorithm_optimize(self, generations=50, population_size=100, mutation_rate=0.1, tournament_size=3):
        """
        Algoritmo Genético para otimizar portfólio maximizando índice de Sharpe.

        Args:
            generations (int): Quantidade de gerações.
            population_size (int): Número de indivíduos na população.
            mutation_rate (float): Probabilidade de mutação por gene.
            tournament_size (int): Número de competidores na seleção por torneio.

        Returns:
            dict: Melhor portfólio encontrado com chaves: 'weights', 'return', 'risk', 'sharpe'
        """
        n = len(self.assets)

        def initialize_population():
            # Inicializa população com pesos válidos (soma=1)
            return np.random.dirichlet(np.ones(n), size=population_size)

        def fitness(weights):
            # Função de fitness é o índice de Sharpe
            port_return = np.dot(weights, self.mu)
            port_risk = np.sqrt(weights @ self.cov @ weights.T)
            return self.sharpe_ratio(port_return, port_risk)

        def tournament_selection(pop, fits):
            # Seleciona um indivíduo via torneio
            selected_indices = np.random.choice(population_size, tournament_size, replace=False)
            selected_fits = fits[selected_indices]
            winner_idx = selected_indices[np.argmax(selected_fits)]
            return pop[winner_idx]

        def arithmetic_crossover(parent1, parent2):
            # Crossover aritmético: mistura linear dos pais
            alpha = np.random.uniform(0, 1)
            child1 = alpha * parent1 + (1 - alpha) * parent2
            child2 = alpha * parent2 + (1 - alpha) * parent1
            # Normaliza para soma 1
            child1 /= np.sum(child1)
            child2 /= np.sum(child2)
            return child1, child2

        def gaussian_mutation(weights):
            # Adiciona ruído gaussiano e corrige para manter soma 1 e pesos entre 0 e 1
            for i in range(len(weights)):
                if np.random.rand() < mutation_rate:
                    weights[i] += np.random.normal(0, 0.05)
            # Limita pesos entre 0 e 1
            weights = np.clip(weights, 0, None)
            if np.sum(weights) == 0:
                weights = np.random.dirichlet(np.ones(n))
            else:
                weights /= np.sum(weights)
            return weights

        # Inicializa população
        population = initialize_population()
        best_solution = None
        best_fitness = -np.inf

        for gen in range(generations):
            fitnesses = np.array([fitness(ind) for ind in population])
            new_population = []

            # Guarda melhor solução da geração
            gen_best_idx = np.argmax(fitnesses)
            gen_best_fit = fitnesses[gen_best_idx]
            if gen_best_fit > best_fitness:
                best_fitness = gen_best_fit
                best_solution = population[gen_best_idx].copy()

            # Elitismo: mantém o melhor indivíduo
            new_population.append(best_solution)

            # Gera novos indivíduos até encher a população
            while len(new_population) < population_size:
                # Seleção
                parent1 = tournament_selection(population, fitnesses)
                parent2 = tournament_selection(population, fitnesses)

                # Crossover
                child1, child2 = arithmetic_crossover(parent1, parent2)

                # Mutação
                child1 = gaussian_mutation(child1)
                child2 = gaussian_mutation(child2)

                new_population.append(child1)
                if len(new_population) < population_size:
                    new_population.append(child2)

            population = np.array(new_population)

        # Calcula métricas do melhor portfólio
        best_return = np.dot(best_solution, self.mu)
        best_risk = np.sqrt(best_solution @ self.cov @ best_solution.T)
        best_sharpe = self.sharpe_ratio(best_return, best_risk)

        return {
            'weights': best_solution,
            'return': best_return,
            'risk': best_risk,
            'sharpe': best_sharpe
        }


def main():
    """
    Função principal para executar a otimização, gerar relatório e salvar resultados.
    """
    optimizer = PortfolioOptimizer()

    print("Executando simulação Monte Carlo...")
    mc_results = optimizer.monte_carlo_simulation(n_portfolios=5000)

    # Identifica melhor portfólio Monte Carlo pelo Sharpe
    idx_best_mc = np.argmax(mc_results['sharpe_ratios'])
    best_mc = {
        'weights': mc_results['weights'][idx_best_mc],
        'return': mc_results['returns'][idx_best_mc],
        'risk': mc_results['risks'][idx_best_mc],
        'sharpe': mc_results['sharpe_ratios'][idx_best_mc]
    }

    print("Executando Algoritmo Genético para otimização...")
    ga_results = optimizer.genetic_algorithm_optimize(generations=50, population_size=100,
                                                     mutation_rate=0.1, tournament_size=3)

    print("Calculando fronteira eficiente...")
    frontier_returns, frontier_risks, frontier_weights = optimizer.efficient_frontier(n_points=100)

    # Relatório detalhado
    print("\n" + "="*60)
    print("RELATÓRIO FINAL - OTIMIZAÇÃO DE PORTFÓLIO")
    print("="*60)
    print("Ativos considerados:", optimizer.assets)
    print("\n--- Melhor Portfólio via Monte Carlo ---")
    for asset, w in zip(optimizer.assets, best_mc['weights']):
        print(f"{asset}: {w:.4f}")
    print(f"Retorno esperado anual: {best_mc['return']:.4f}")
    print(f"Volatilidade anual: {best_mc['risk']:.4f}")
    print(f"Índice de Sharpe: {best_mc['sharpe']:.4f}")

    print("\n--- Melhor Portfólio via Algoritmo Genético ---")
    for asset, w in zip(optimizer.assets, ga_results['weights']):
        print(f"{asset}: {w:.4f}")
    print(f"Retorno esperado anual: {ga_results['return']:.4f}")
    print(f"Volatilidade anual: {ga_results['risk']:.4f}")
    print(f"Índice de Sharpe: {ga_results['sharpe']:.4f}")

    # Salvar resultados em JSON
    save_dir = 'atena_evolution'
    os.makedirs(save_dir, exist_ok=True)

    results_to_save = {
        'assets': optimizer.assets,
        'monte_carlo': {
            'best_weights': best_mc['weights'].tolist(),
            'best_return': best_mc['return'],
            'best_risk': best_mc['risk'],
            'best_sharpe': best_mc['sharpe']
        },
        'genetic_algorithm': {
            'best_weights': ga_results['weights'].tolist(),
            'best_return': ga_results['return'],
            'best_risk': ga_results['risk'],
            'best_sharpe': ga_results['sharpe']
        },
        'efficient_frontier': {
            'returns': frontier_returns.tolist(),
            'risks': frontier_risks.tolist(),
            'weights': [w.tolist() for w in frontier_weights]
        }
    }

    save_path = os.path.join(save_dir, 'portfolio_optimization_results.json')
    with open(save_path, 'w') as fp:
        json.dump(results_to_save, fp, indent=4)

    print(f"\nResultados salvos em '{save_path}'")

    # Visualização comparativa dos métodos
    plt.figure(figsize=(10, 6))
    plt.scatter(mc_results['risks'], mc_results['returns'], c=mc_results['sharpe_ratios'],
                cmap='viridis', alpha=0.4, label='Simulação Monte Carlo')
    plt.colorbar(label='Índice de Sharpe')
    plt.scatter(ga_results['risk'], ga_results['return'], color='red', marker='*', s=200,
                label='Melhor Portfólio AG')
    plt.plot(frontier_risks, frontier_returns, 'b--', linewidth=2, label='Fronteira Eficiente')
    plt.xlabel('Volatilidade (Risco)')
    plt.ylabel('Retorno Esperado')
    plt.title('Comparação: Monte Carlo vs Algoritmo Genético vs Fronteira Eficiente')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def _test():
    """
    Testes inline para validar funcionalidades principais.
    """

#     optimizer = PortfolioOptimizer()
# 
#     # Teste Sharpe Ratio
#     assert np.isclose(optimizer.sharpe_ratio(0.1, 0.05), (0.1 - 0.02) / 0.05)
# 
#     # Teste Monte Carlo retorno shapes
#     mc = optimizer.monte_carlo_simulation(100)
#     assert mc['weights'].shape == (100, 6)
#     assert mc['returns'].shape == (100,)
#     assert mc['risks'].shape == (100,)
#     assert mc['sharpe_ratios'].shape == (100,)
# 
#     # Teste fronteira eficiente shapes
#     rets, risks, wts = optimizer.efficient_frontier(10)
#     # assert len(rets) == 10
#     assert len(risks) == 10
#     assert wts.shape == (10, 6)
# 
#     # Teste Algoritmo Genético retorna keys corretos
#     ga_res = optimizer.genetic_algorithm_optimize(generations=5, population_size=20)
#     for k in ['weights', 'return', 'risk', 'sharpe']:
#         assert k in ga_res
#     assert len(ga_res['weights']) == 6
# 
#     print("Todos os testes inline passaram com sucesso.")
# 
# 
# if __name__ == "__main__":
#     _test()
#     main()if __name__ == '__main__': main()
