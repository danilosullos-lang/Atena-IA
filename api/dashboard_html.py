"""
Função para servir o dashboard ATENA Ω como HTML
"""
import os
from pathlib import Path

def get_dashboard_html() -> str:
    """Retorna o HTML do dashboard compilado"""
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "dist" / "public" / "index.html"
    
    if dashboard_path.exists():
        with open(dashboard_path, "r", encoding="utf-8") as f:
            html = f.read()
        
        # Corrigir caminhos dos assets
        html = html.replace('src="/assets/', 'src="/dashboard/assets/')
        html = html.replace('href="/assets/', 'href="/dashboard/assets/')
        html = html.replace('src="/__manus__/', 'src="/dashboard/__manus__/')
        
        return html
    else:
        # Fallback se o arquivo não existir
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>ATENA Ω Dashboard</title>
            <style>
                body {
                    background: #0a0a0a;
                    color: #fff;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                }
                .container {
                    text-align: center;
                }
                h1 { font-size: 2.5em; margin-bottom: 10px; }
                p { font-size: 1.1em; color: #999; }
                .spinner {
                    border: 4px solid #333;
                    border-top: 4px solid #3b82f6;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 30px auto;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>ATENA Ω</h1>
                <p>Dashboard em construção...</p>
                <div class="spinner"></div>
            </div>
        </body>
        </html>
        """
