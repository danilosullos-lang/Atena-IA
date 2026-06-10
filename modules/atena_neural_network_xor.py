#!/usr/bin/env python3
"""
modules/atena_neural_network_xor.py

Implementação avançada de uma Rede Neural MLP do zero usando NumPy para resolver o problema XOR.

Características:
- Arquitetura 2-4-1 (2 inputs, 4 neurônios na camada oculta, 1 neurônio na saída)
- Função de ativação sigmoid com derivada
- Treinamento com backpropagation e gradiente descendente com momentum adaptativo
- Critério de parada baseado em erro e número máximo de épocas
- Salvamento dos pesos finais e histórico de erros em JSON
- Relatório detalhado impresso após treinamento
- Testes inline demonstrando o funcionamento e assertivas para validação
"""

import numpy as np
import json
import os

class MLP_XOR:
    """
    Rede Neural Multi-Layer Perceptron para resolver o problema XOR.
    """

    def __init__(self, input_size=2, hidden_size=4, output_size=1, learning_rate=0.5, momentum=0.9, seed=None):
        """
        Inicializa a rede com pesos aleatórios e parâmetros.

        Args:
            input_size (int): Número de neurônios na camada de entrada.
            hidden_size (int): Número de neurônios na camada oculta.
            output_size (int): Número de neurônios na camada de saída.
            learning_rate (float): Taxa de aprendizado para o gradiente descendente.
            momentum (float): Coeficiente de momentum para atualização dos pesos.
            seed (int or None): Semente para geração de números aleatórios.
        """
        if seed is not None:
            np.random.seed(seed)

        # Inicialização dos pesos com valores aleatórios pequenos (Xavier initialization)
        limit_hidden = np.sqrt(6 / (input_size + hidden_size))
        self.W1 = np.random.uniform(-limit_hidden, limit_hidden, (hidden_size, input_size))
        self.b1 = np.zeros((hidden_size, 1))

        limit_output = np.sqrt(6 / (hidden_size + output_size))
        self.W2 = np.random.uniform(-limit_output, limit_output, (output_size, hidden_size))
        self.b2 = np.zeros((output_size, 1))

        self.learning_rate = learning_rate
        self.momentum = momentum

        # Para momentum:
        self.VdW1 = np.zeros_like(self.W1)
        self.Vdb1 = np.zeros_like(self.b1)
        self.VdW2 = np.zeros_like(self.W2)
        self.Vdb2 = np.zeros_like(self.b2)

    @staticmethod
    def sigmoid(z):
        """
        Função sigmoide.

        Args:
            z (np.ndarray): Entrada.

        Returns:
            np.ndarray: Saída após função sigmoide.
        """
        return 1 / (1 + np.exp(-z))

    @staticmethod
    def sigmoid_derivative(a):
        """
        Derivada da função sigmoide em relação à saída a.

        Args:
            a (np.ndarray): Saída da função sigmoide.

        Returns:
            np.ndarray: Derivada.
        """
        return a * (1 - a)

    def forward(self, X):
        """
        Propagação para frente.

        Args:
            X (np.ndarray): Entrada (n_features, n_samples).

        Returns:
            tuple: (saida_ativacao_oculta, saida_rede)
        """
        # Camada oculta
        Z1 = self.W1 @ X + self.b1  # (hidden_size, n_samples)
        A1 = self.sigmoid(Z1)

        # Camada saída
        Z2 = self.W2 @ A1 + self.b2  # (output_size, n_samples)
        A2 = self.sigmoid(Z2)

        return A1, A2

    def compute_loss(self, Y, Y_hat):
        """
        Calcula o erro quadrático médio.

        Args:
            Y (np.ndarray): Saídas verdadeiras.
            Y_hat (np.ndarray): Saídas previstas pela rede.

        Returns:
            float: Erro médio.
        """
        m = Y.shape[1]
        loss = np.sum((Y - Y_hat) ** 2) / m
        return loss

    def backward(self, X, Y, A1, A2):
        """
        Backpropagation para cálculo dos gradientes.

        Args:
            X (np.ndarray): Entrada.
            Y (np.ndarray): Saída esperada.
            A1 (np.ndarray): Ativação da camada oculta.
            A2 (np.ndarray): Ativação da camada saída.

        Returns:
            tuple: Gradientes para W1, b1, W2, b2
        """
        m = X.shape[1]

        dZ2 = (A2 - Y) * self.sigmoid_derivative(A2)  # (output_size, m)
        dW2 = (dZ2 @ A1.T) / m  # (output_size, hidden_size)
        db2 = np.sum(dZ2, axis=1, keepdims=True) / m  # (output_size, 1)

        dA1 = self.W2.T @ dZ2  # (hidden_size, m)
        dZ1 = dA1 * self.sigmoid_derivative(A1)  # (hidden_size, m)
        dW1 = (dZ1 @ X.T) / m  # (hidden_size, input_size)
        db1 = np.sum(dZ1, axis=1, keepdims=True) / m  # (hidden_size, 1)

        return dW1, db1, dW2, db2

    def update_parameters(self, dW1, db1, dW2, db2):
        """
        Atualiza os pesos usando gradiente descendente com momentum.

        Args:
            dW1, db1, dW2, db2: Gradientes calculados no backpropagation.
        """
        # Atualização com momentum
        self.VdW1 = self.momentum * self.VdW1 + (1 - self.momentum) * dW1
        self.Vdb1 = self.momentum * self.Vdb1 + (1 - self.momentum) * db1
        self.VdW2 = self.momentum * self.VdW2 + (1 - self.momentum) * dW2
        self.Vdb2 = self.momentum * self.Vdb2 + (1 - self.momentum) * db2

        self.W1 -= self.learning_rate * self.VdW1
        self.b1 -= self.learning_rate * self.Vdb1
        self.W2 -= self.learning_rate * self.VdW2
        self.b2 -= self.learning_rate * self.Vdb2

    def train(self, X, Y, epochs=10000, tol=1e-4, verbose=False):
        """
        Treina a rede neural para o problema XOR.

        Args:
            X (np.ndarray): Entradas (n_features, n_samples).
            Y (np.ndarray): Saídas esperadas (output_size, n_samples).
            epochs (int): Número máximo de épocas.
            tol (float): Tolerância para erro mínimo para parada antecipada.
            verbose (bool): Se True, imprime progresso do treinamento.

        Returns:
            dict: Histórico contendo erros por época.
        """
        history = {
            "loss": []
        }

        for epoch in range(1, epochs + 1):
            A1, A2 = self.forward(X)
            loss = self.compute_loss(Y, A2)
            history["loss"].append(loss)

            if verbose and (epoch % 1000 == 0 or epoch == 1):
                print(f"Epoch {epoch}/{epochs} - Loss: {loss:.6f}")

            if loss < tol:
                if verbose:
                    print(f"Parada antecipada no epoch {epoch} com loss {loss:.6f}")
                break

            dW1, db1, dW2, db2 = self.backward(X, Y, A1, A2)
            self.update_parameters(dW1, db1, dW2, db2)

        return history

    def predict(self, X):
        """
        Faz previsão para entradas X.

        Args:
            X (np.ndarray): Entradas.

        Returns:
            np.ndarray: Saídas previstas (valores entre 0 e 1).
        """
        _, A2 = self.forward(X)
        return A2

    def save_model(self, filepath):
        """
        Salva os pesos e biases em JSON.

        Args:
            filepath (str): Caminho do arquivo para salvar.
        """
        model_data = {
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
            "learning_rate": self.learning_rate,
            "momentum": self.momentum
        }
        with open(filepath, 'w') as f:
            json.dump(model_data, f, indent=4)

    @staticmethod
    def save_history(history, filepath):
        """
        Salva o histórico de treinamento em JSON.

        Args:
            history (dict): Histórico de treinamento.
            filepath (str): Caminho do arquivo para salvar.
        """
        with open(filepath, 'w') as f:
            json.dump(history, f, indent=4)


def run_tests_and_train():
    """
    Função para rodar testes inline, treinar e salvar resultados.
    """
    print("Iniciando testes e treinamento da MLP para XOR...")

    # Dados XOR (entradas 2x4, saídas 1x4)
    X = np.array([[0, 0, 1, 1],
                  [0, 1, 0, 1]])  # (2,4)
    Y = np.array([[0, 1, 1, 0]])  # (1,4)

    # Criação da rede
    mlp = MLP_XOR(learning_rate=0.7, momentum=0.8, seed=42)

    # Testa forward antes do treinamento - saída deve estar aleatória
    A1_init, A2_init = mlp.forward(X)
    assert A2_init.shape == (1, 4), "Shape da saída inicial incorreta."

    # Treinamento
    history = mlp.train(X, Y, epochs=20000, tol=1e-4, verbose=True)

    # Testa perda final pequena
    final_loss = history["loss"][-1]
    assert final_loss < 0.01, f"Erro final muito alto: {final_loss}"

    # Predição após treinamento
    Y_pred = mlp.predict(X)
    Y_pred_binary = (Y_pred > 0.5).astype(int)

    # Testa se rede aprendeu XOR corretamente
    assert np.array_equal(Y_pred_binary, Y), f"Rede não aprendeu XOR corretamente: {Y_pred_binary} vs {Y}"

    # Salvar modelo e histórico
    os.makedirs("modules/results", exist_ok=True)
    model_path = "modules/results/mlp_xor_model.json"
    history_path = "modules/results/mlp_xor_history.json"

    mlp.save_model(model_path)
    MLP_XOR.save_history(history, history_path)

    # Impressão do relatório detalhado
    print("\n=== RELATÓRIO FINAL ===")
    print(f"Arquivos salvos:\n - Modelo: {model_path}\n - Histórico: {history_path}")
    print(f"Erro final (MSE): {final_loss:.8f}")
    print("Predições finais (valores contínuos):")
    for i in range(X.shape[1]):
        print(f"Input: {X[:, i]} -> Saída: {Y_pred[0, i]:.6f} (binário: {Y_pred_binary[0, i]})")
    print("Rede neural MLP treinada com sucesso para resolver XOR!")

if __name__ == "__main__":
    run_tests_and_train()
