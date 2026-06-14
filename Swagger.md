# Swagger / OpenAPI — автоматическая генерация для ChironAI

## Проблема

Swagger **не генерирует документацию автоматически**. Все эндпоинты нужно описывать вручную. В проекте ~140+ route'ов — ручное описание займёт дни.

## Что нужно сделать для авто-генерации

### Вариант 1: `flask-restx` (рекомендуется)

**Плюсы:** генерирует Swagger UI автоматически из кода моделей и декораторов.
**Минусы:** требует рефакторинга всех route'ов с `@bp.route` на `@api.route` + модели.

```bash
pip install flask-restx
```

**Что меняется в коде:**

```python
# Было:
@bp.route("/rag/status", methods=["GET"])
def rag_status():
    return jsonify({"status": "ok"})

# Стало:
from flask_restx import Api, Resource, fields, Namespace

api = Namespace("rag", description="RAG operations")

status_model = api.model("RagStatus", {
    "status": fields.String(required=True, description="Service status"),
    "collections": fields.Integer(description="Number of collections"),
})

@api.route("/status")
class RagStatus(Resource):
    @api.marshal_with(status_model)
    def get(self):
        return {"status": "ok", "collections": 5}
```

**Объём работы:** переписать ~140 route'ов, создать модели для каждого ответа.

---

### Вариант 2: `flasgger` + docstrings (компромисс)

**Плюсы:** не требует рефакторинга route'ов, Swagger UI из docstrings.
**Минусы:** docstrings всё равно надо писать вручную.

```bash
pip install flasgger
```

**Что меняется в коде:**

```python
from flasgger import Swagger

# В app.py:
swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {
        "title": "ChironAI API",
        "version": "0.2.0"
    }
})

# В route:
@bp.route("/rag/status", methods=["GET"])
def rag_status():
    """
    Get RAG service status.
    ---
    tags:
      - RAG
    responses:
      200:
        description: Service status
        schema:
          type: object
          properties:
            status:
              type: string
            collections:
              type: integer
    """
    return jsonify({"status": "ok", "collections": 5})
```

**Объём работы:** добавить docstrings к ~140 route'ам.

---

### Вариант 3: `spectree` (Pydantic-based, самый чистый)

**Плюсы:** использует Pydantic модели (type-safe), генерирует OpenAPI 3.0.
**Минусы:** требует Pydantic (в проекте его нет), рефакторинг route'ов.

```bash
pip install spectree
```

```python
from pydantic import BaseModel
from spectree import SpecTree

api = SpecTree("flask")

class RagStatusResponse(BaseModel):
    status: str
    collections: int

@bp.route("/rag/status", methods=["GET"])
@api.validate(resp=Response(HTTP_200=RagStatusResponse))
def rag_status():
    return jsonify({"status": "ok", "collections": 5})

# В app.py:
api.register(app)
```

---

### Вариант 4: `apispec` + `flask-smorest` (Marshmallow-based)

**Плюсы:** Marshmallow схемы, авто-генерация OpenAPI.
**Минусы:** требует Marshmallow, рефакторинг.

---

## Итог

| Вариант | Авто-генерация | Рефакторинг | Зависимости |
|---------|---------------|-------------|-------------|
| flask-restx | Да (из кода) | Полный | flask-restx |
| flasgger | Нет (из docstrings) | Docstrings | flasgger, PyYAML |
| spectree | Да (из Pydantic) | Полный | spectree, pydantic |
| flask-smorest | Да (из Marshmallow) | Полный | apispec, marshmallow |

**Ни один вариант не даёт Swagger «из коробки» без ручной работы.** Минимальный путь — `flasgger` с docstrings, но писать их всё равно придётся для каждого эндпоинта.

## Быстрый старт с flasgger (минимальные изменения)

1. `pip install flasgger`
2. В `modules/webui_backend/webui_backend/app.py` добавить:
   ```python
   from flasgger import Swagger
   swagger = Swagger(app)
   ```
3. Swagger UI будет доступен по `/apidocs`
4. Добавлять YAML docstrings к эндпоинтам по мере необходимости
