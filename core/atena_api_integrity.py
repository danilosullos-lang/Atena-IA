#!/usr/bin/env python3
import os
import sys
import time
import json
import csv
import logging
import traceback
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Tuple
import requests
from requests.exceptions import RequestException
import threading
import queue
import statistics

# Configuração básica do logger para debug e erros
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

API_CATALOG_FILE = os.path.join(os.path.dirname(__file__), 'api_catalog.json')
API_TEST_RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'api_test_results.csv')

class APIIntegrityTester:
    """
    Classe para testar a integridade de APIs via smoke test simples, catalogar APIs íntegros e gerar relatórios.
    """

    def __init__(self, timeout: float = 5.0, max_retries: int = 3):
        """
        Inicializa o testador de integridade.
        :param timeout: Tempo máximo para aguardar resposta da API.
        :param max_retries: Número máximo de tentativas em caso de falha temporária.
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.catalog = self._load_catalog()
        self.test_results = []

    def _load_catalog(self) -> Dict[str, Dict[str, Any]]:
        """
        Carrega o catálogo de APIs já testadas e catalogadas.
        :return: Dicionário com URLs como chave e info como valor.
        """
        if not os.path.isfile(API_CATALOG_FILE):
            logging.debug("Arquivo de catálogo não encontrado, iniciando catálogo vazio.")
            return {}
        try:
            with open(API_CATALOG_FILE, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
                logging.debug(f"Catálogo carregado com {len(catalog)} APIs.")
                return catalog
        except Exception as e:
            logging.error(f"Erro ao carregar catálogo: {e}")
            return {}

    def _save_catalog(self) -> None:
        """
        Salva o catálogo atualizado no arquivo JSON.
        """
        try:
            with open(API_CATALOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.catalog, f, indent=2, ensure_ascii=False)
            logging.debug(f"Catálogo salvo com {len(self.catalog)} APIs.")
        except Exception as e:
            logging.error(f"Erro ao salvar catálogo: {e}")

    def _save_test_results(self) -> None:
        """
        Salva os resultados dos testes em arquivo CSV.
        """
        fieldnames = ['url', 'method', 'status_code', 'response_time_ms', 'success', 'timestamp']
        try:
            with open(API_TEST_RESULTS_FILE, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for result in self.test_results:
                    writer.writerow(result)
            logging.debug(f"Resultados dos testes salvos em {API_TEST_RESULTS_FILE}.")
        except Exception as e:
            logging.error(f"Erro ao salvar resultados dos testes: {e}")

    def _validate_url(self, url: str) -> bool:
        """
        Valida a URL da API.
        :param url: URL da API.
        :return: True se válida, False caso contrário.
        """
        try:
            parts = urlparse(url)
            valid = all([parts.scheme in ('http', 'https'), parts.netloc])
            if not valid:
                logging.warning(f"URL inválida: {url}")
            return valid
        except Exception:
            logging.warning(f"Exceção ao validar URL: {url}")
            return False

    def _perform_request(self, url: str, method: str = 'GET') -> Tuple[Optional[int], Optional[float], Optional[str]]:
        """
        Realiza o request HTTP e mede o tempo de resposta.
        :param url: URL da API.
        :param method: Método HTTP a usar.
        :return: Tuple com (status_code, tempo_resposta_ms, mensagem_erro)
        """
        for attempt in range(1, self.max_retries+1):
            try:
                start = time.perf_counter()
                if method == 'POST':
                    # Enviar POST com corpo vazio JSON para smoke test
                    response = requests.post(url, json={}, timeout=self.timeout)
                else:
                    # GET simples
                    response = requests.get(url, timeout=self.timeout)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logging.debug(f"{method} {url} responded {response.status_code} in {elapsed_ms:.2f}ms")
                return response.status_code, elapsed_ms, None
            except RequestException as e:
                logging.warning(f"Tentativa {attempt} falhou para {url} com {method}: {e}")
                if attempt == self.max_retries:
                    return None, None, str(e)
                time.sleep(0.5 * attempt)  # Backoff incremental
        return None, None, "Número máximo de tentativas excedido"

    def smoke_test_api(self, url: str) -> Dict[str, Any]:
        """
        Executa um smoke test básico na API, verificando GET e POST.
        :param url: URL da API.
        :return: Dicionário com resultado detalhado.
        """
        if not self._validate_url(url):
            result = dict(url=url, success=False, reason="URL inválida", timestamp=time.time())
            logging.error(f"Smoke test abortado: {result}")
            return result

        methods = ['GET', 'POST']
        results = []

        for method in methods:
            status_code, response_time, error = self._perform_request(url, method)
            success = (status_code is not None and 200 <= status_code < 300)
            results.append({
                'method': method,
                'status_code': status_code,
                'response_time_ms': response_time,
                'success': success,
                'error': error
            })
            if not success:
                logging.info(f"Smoke test {method} falhou para {url} com status {status_code} e erro {error}")

        # Condição de integridade: ambos GET e POST devem responder 2xx em tempo razoável (< timeout)
        all_success = all(r['success'] and (r['response_time_ms'] is not None and r['response_time_ms'] < self.timeout*1000) for r in results)

        result_summary = {
            'url': url,
            'success': all_success,
            'details': results,
            'timestamp': time.time()
        }

        # Registro para relatório CSV
        for r in results:
            self.test_results.append({
                'url': url,
                'method': r['method'],
                'status_code': r['status_code'] or 0,
                'response_time_ms': r['response_time_ms'] or 0.0,
                'success': r['success'],
                'timestamp': time.time()
            })

        # Se íntegro, adiciona ao catálogo
        if all_success and url not in self.catalog:
            self.catalog[url] = {
                'added': time.time(),
                'last_tested': time.time(),
                'methods_tested': methods,
                'average_response_time_ms': statistics.mean(r['response_time_ms'] for r in results if r['response_time_ms'] is not None)
            }
            logging.info(f"API catalogada: {url}")
            self._save_catalog()
        elif url in self.catalog:
            # Atualiza timestamp e tempos no catálogo se já existente
            self.catalog[url]['last_tested'] = time.time()
            self.catalog[url]['average_response_time_ms'] = statistics.mean(r['response_time_ms'] for r in results if r['response_time_ms'] is not None)
            self._save_catalog()

        return result_summary

    def generate_report(self) -> str:
        """
        Gera um relatório detalhado dos últimos testes realizados.
        :return: String do relatório formatado.
        """
        lines = []
        lines.append("=== Relatório de Integridade de APIs ===")
        lines.append(f"Total APIs testadas: {len(self.test_results)//2}")
        lines.append("")

        success_count = sum(1 for r in self.test_results if r['success'])
        fail_count = len(self.test_results) - success_count
        lines.append(f"Testes bem-sucedidos: {success_count}")
        lines.append(f"Testes falhos: {fail_count}")
        lines.append("")

        # Estatísticas de tempo médio por método
        times_by_method = {'GET': [], 'POST': []}
        for r in self.test_results:
            if r['response_time_ms'] > 0:
                times_by_method[r['method']].append(r['response_time_ms'])
        for method, times in times_by_method.items():
            if times:
                avg = statistics.mean(times)
                lines.append(f"Tempo médio de resposta {method}: {avg:.2f} ms")
            else:
                lines.append(f"Tempo médio de resposta {method}: N/A")

        lines.append("")
        lines.append("APIs catalogadas no momento:")
        for url, meta in self.catalog.items():
            added = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta['added']))
            last_tested = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta['last_tested']))
            art = meta.get('average_response_time_ms', 0)
            lines.append(f" - {url} (adicionado: {added}, último teste: {last_tested}, resp: {art:.2f} ms)")

        return "\n".join(lines)


def run_tests():
    """
    Testes inline para demonstrar funcionamento do módulo.
    """
    tester = APIIntegrityTester(timeout=4, max_retries=2)

    # Lista de APIs para testar (exemplos públicos)
    apis = [
        "https://jsonplaceholder.typicode.com/posts/1",   # GET válido
        "https://jsonplaceholder.typicode.com/posts",     # POST válido
        "https://httpbin.org/status/200",                  # GET com status 200
        "https://httpbin.org/status/404",                  # GET com status 404 (falha)
        "https://httpbin.org/post",                        # POST válido
        "https://invalid.api.url.example",                 # URL inválida
        "https://httpbin.org/delay/3"                      # GET com delay para testar timeout
    ]

    results = []
    # Testar em threads para paralelizar e acelerar smoke tests
    def worker(url: str, output_queue: queue.Queue):
        try:
            res = tester.smoke_test_api(url)
            output_queue.put(res)
        except Exception:
            logging.error(f"Erro inesperado no teste da API {url}:\n{traceback.format_exc()}")

    q = queue.Queue()
    threads = []
    for api_url in apis:
        t = threading.Thread(target=worker, args=(api_url, q))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    while not q.empty():
        results.append(q.get())

    # Salvar resultados CSV
    tester._save_test_results()

    # Gerar e imprimir relatório final
    report = tester.generate_report()
    print(report)

    # Testes básicos inline
    assert any(r['url'] == "https://jsonplaceholder.typicode.com/posts/1" and r['success'] for r in results), "GET API pública deveria ser bem sucedida"
    assert any(r['url'] == "https://invalid.api.url.example" and not r['success'] for r in results), "API inválida deveria falhar"

if __name__ == "__main__":
    run_tests()
