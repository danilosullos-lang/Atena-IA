# ATENA Food Delivery Push Ready

App completo de delivery de comida gerado pela ATENA para ficar pronto para `git push` e validação em CI.

## O que vem pronto

- **Backend FastAPI** com restaurantes, cardápio, carrinho/cotação, pedidos, pagamento simulado e tracking.
- **Testes automatizados** de API e regras de negócio.
- **Mobile Flutter** com tela de catálogo/carrinho/checkout mockada e pronta para conectar ao backend.
- **Docker/Compose** para subir a API localmente.
- **Checklist de push/release** com passos antes de publicar.
- **CI** dentro deste pack (`.github/workflows/ci.yml`) para rodar testes do backend.

## Rodar localmente

```bash
python -m pip install -r backend/requirements.txt
pytest -q backend/tests
uvicorn backend.app.main:app --reload --app-dir .
```

API local: http://127.0.0.1:8000

## Rodar com Docker

```bash
docker compose up --build
```

## Endpoints principais

- `GET /health`
- `GET /restaurants`
- `GET /restaurants/{restaurant_id}/menu`
- `POST /cart/quote`
- `POST /orders`
- `GET /orders/{order_id}`
- `POST /orders/{order_id}/status`
- `POST /payments/webhook`

## Mobile

```bash
cd mobile
flutter pub get
flutter test
flutter run
```

## Push-ready

Antes do push final, rode:

```bash
pytest -q backend/tests
python -m py_compile backend/app/*.py
```

Depois:

```bash
git add generated/atena_food_delivery_push_ready
git commit -m "Add push-ready food delivery app"
git push
```
