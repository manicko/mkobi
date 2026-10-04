---
name: Agent Guidelines
description: Обязательные правила и контекст для работы над проектом
alwaysApply: true
---

#Key links
[Project Structure](C:\py_dev\mkobi\.ai\structure\map.md)
[Full Project Structure including dependencies and semantic for audit and development)](C:\py_dev\mkobi\.ai\structure**)
[Important project specification](C:\py_dev\mkobi\docs\SPEC.md)
[Docker specification](C:\py_dev\mkobi\docs\10-deployment\deployment.md)
[Important project commands](C:\py_dev\mkobi\.ai\context\commands.md)
[Important context](C:\py_dev\mkobi\.ai\context)
[Doc Maintenance Rules](C:\py_dev\mkobi\docs/00-overview/doc-maintenance-rules.md) — **read before any doc-modifying task**


# Agent Guidelines — mkobi BI Dashboard

## 1. Основные принципы

- **Production-код — главный источник истины**.
- Предпочтение отдаётся **простоте, читаемости и поддерживаемости**.
- Соблюдать **Clean Architecture** (backend) и **Feature-Sliced Design** (frontend).
- Все комментарии, логи и docstring — **только на английском**.
- Избегать overengineering и ненужных абстракций.

## 2. Структура проекта

**Backend:**
- `src/mkobi/` — основной пакет
  - `api/` — HTTP-слой (роуты + deps)
  - `services/` — бизнес-логика
  - `db/` — модели SQLAlchemy + repositories
  - `models/` — Pydantic модели + enums
  - `data/` — загрузка, обработка (Polars) и сохранение данных
  - `core/` — security, permissions, logging, config
  - `interfaces/` — абстракции для DI
  - `utils/` — вспомогательные функции
  - `workers/` — фоновые задачи

**Frontend:**
- `frontend/src/`
  - `app/` — провайдеры и роутинг
  - `features/` — бизнес-фичи (auth, dashboards, upload, admin и т.д.)
  - `shared/` — переиспользуемый код (api, components, types)

**Другое:**
- `tests/` — все тесты (pytest)
- `alembic/` — миграции БД
- `docker-compose*.yml` + `Dockerfile`

## 3. Технологический стек (обязательно соблюдать)

- **Backend**: FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), asyncpg, Polars, StrEnum
- **Frontend**: React 18 + TypeScript, TanStack Query, React Hook Form + Zod, Plotly.js React
- **БД**: PostgreSQL + JSONB, Alembic
- **Инструменты**: uv, ruff, mypy

**Запрещено:**
- pandas
- `print()`
- raw SQL через f-strings
- русский язык в коде, логах и комментариях

## 4. Критические правила

### Backend
- Чёткое разделение слоёв: **API → Service → Repository**
- Все публичные функции и методы — с type hints
- Все константы и статусы — через `StrEnum` (`src/mkobi/models/enums.py`)
- Логирование: `logger = logging.getLogger(__name__)`
- Временные файлы после обработки **обязательно удалять**
- Access control проверяется на каждом запросе к дашборду

### Data Processing
- Использовать только **Polars**
- При загрузке файла — **полный пересчёт** агрегатов для дашборда
- Данные хранятся в `aggregated_data` (JSONB `dims` + `metrics`)

### Code Quality
- Ruff + mypy должны проходить без ошибок
- Маленькие функции, понятные имена
- Комментарии — только к нетривиальной логике

### Security
- JWT + bcrypt
- Rate limiting + MIME-type + размер файла на upload
- Secrets только через окружение (поддержка `_FILE`)

### Error Handling
- **RFC 7807 Problem Details format**: All API errors return standardized responses with `type`, `title`, `status`, `detail`, `code`, and optional `details` fields
- **ErrorCode StrEnum**: All error codes defined in `src/mkobi/models/enums.py` using `UPPER_SNAKE_CASE` convention
- **AppException**: Single error-raising mechanism in `src/mkobi/utils/exceptions.py`
- **Status code mapping**: ErrorCode values map to HTTP status codes automatically (e.g., `NOT_FOUND` → 404, `PERMISSION_DENIED` → 403)
- **Exception handlers**: Register via `add_exception_handlers(app)` in `src/mkobi/utils/exceptions.py`

**Forbidden:**
- Do NOT raise `HTTPException` directly
- Do NOT use hardcoded error code strings — always use `ErrorCode` enum
- Do NOT return non-RFC 7807 error responses

**Frontend error extraction chain** (see `frontend/src/shared/api/errorHandler.ts`):
1. Legacy FastAPI validation format (422 with errors array, no code field)
2. RFC 7807 format (with code field)
3. Validation field-level errors extraction
4. AxiosError → error.message fallback
5. Generic fallback message

**Error Layer Architecture:**
- L1: `src/mkobi/models/enums.py` — ErrorCode enum definition
- L2: `src/mkobi/utils/exceptions.py` — AppException and handlers
- L3: API routes — raise AppException with appropriate ErrorCode

**Documentation:**
- Error format specification: `docs/08-security/error-format.md`
- Error handling guide: `docs/99-reference/error-handling-guide.md`

## 5. Основной Data Flow

1. Upload (`POST /upload/{dashboard_id}`)
2. Сохранение в staging-папку через `platformdirs`: `UploadSettings.temp_dir` — `user_data_dir` (`user_data_dir("mkobi", "ZOO") / "tmp_uploads"`), а per-user дерево загрузок — `user_cache_dir` (`user_cache_dir("mkobi", appauthor=False) / "uploads" / <user_id>`); обе не являются системным temp-каталогом
3. Валидация → Parse (Polars)
4. Transform + Aggregate (по `processing_configs`)
5. Сохранение в `aggregated_data`
6. Frontend получает данные через `/data/aggregated`

## 6. Что всегда проверять

- Соответствие архитектуре (не смешивать слои)
- Использование `StrEnum`
- Корректный cleanup временных файлов
- Наличие type hints
- Английский язык в логах и комментариях
- Соответствие спецификации (`SPEC.md`)

---

**Главный девиз:**

> Пиши явно, просто и надёжно.  
> Код должен быть понятен через 6 месяцев без дополнительных объяснений.

