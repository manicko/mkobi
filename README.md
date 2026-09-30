# mkobi - BI Dashboard System

Веб-приложение для загрузки, обработки и визуализации данных с системой управления доступом.

## Возможности

- Загрузка CSV и CSV.gz файлов с автоматической обработкой через Polars
- Создание интерактивных дашбордов с графиками (bar, line, pie, table)
- Гибкая система фильтрации данных (year, category, brand)
- Управление пользователями с ролями (admin, editor, viewer)
- Настраиваемые дашборды через конфигурацию
- JWT аутентификация с bcrypt хешированием
- Асинхронная обработка данных с использованием SQLAlchemy и asyncpg

## Технологический стек

### Backend
- **FastAPI** - веб-фреймворк
- **Polars** - обработка данных (pandas не используется)
- **SQLAlchemy** (async) + **asyncpg** - работа с PostgreSQL
- **Pydantic** - валидация данных
- **JWT + bcrypt** - аутентификация
- **Alembic** - миграции БД
- **uv** - управление зависимостями
- **pytest** - тестирование

### Frontend
- **React 18+** (TypeScript) + **Vite**
- **Material UI v5** / **Ant Design**
- **TanStack Query** - управление состоянием
- **React Hook Form + Zod** - формы
- **Plotly.js React** - графики
- **Axios** - HTTP клиент

## Структура проекта

```
mkobi/
├── alembic/              # Миграции БД
├── frontend/             # React SPA приложение
│   ├── src/
│   │   ├── app/         # Провайдеры и маршруты
│   │   ├── features/    # Фичи (auth, dashboards, upload, users, admin)
│   │   └── shared/      # Общие компоненты и API
│   └── package.json
├── src/mkobi/           # Python backend
│   ├── api/             # FastAPI routes
│   ├── core/            # Базовые компоненты (security, permissions, logging)
│   ├── dashboards/      # Дашборды и компоненты
│   ├── data/            # Загрузка, обработка, хранение данных
│   ├── db/              # Модели БД, репозитории, сессии
│   ├── models/          # Pydantic модели
│   ├── services/        # Бизнес-логика
│   ├── settings/        # Конфигурация (app.yaml, .env)
│   ├── utils/           # Утилиты
│   └── workers/         # Фоновые задачи
├── tests/               # Тесты
├── nginx/               # Nginx конфигурация
├── docker-compose.yml   # Docker Compose конфиг
├── Dockerfile           # Docker образ
└── pyproject.toml      # Зависимости Python
```

## Быстрый старт

### Предварительные требования
- Python 3.12+
- uv (менеджер пакетов Python)
- Docker и Docker Compose
- Node.js 18+ (для frontend)

### Локальная разработка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd mkobi
```

2. Установите зависимости:
```bash
uv sync
```

3. Настройте переменные окружения:
```bash
cp .env.example .env
# Отредактируйте .env под ваши настройки
```

4. Запустите PostgreSQL и Redis (через Docker):
```bash
docker-compose up -d postgres redis
```

5. Примените миграции:
```bash
uv run alembic upgrade head
```

6. Запустите backend:
```bash
uv run uvicorn src.mkobi.app:app --reload --host 0.0.0.0 --port 8010
```

7. Запустите frontend (в другом терминале):
```bash
cd frontend
npm install
npm run dev
```

### Запуск через Docker

```bash
docker-compose up -d --build
```

Приложение будет доступно по адресу: http://localhost:8010

## Конфигурация

Конфигурация загружается из нескольких источников (приоритет):
1. Переменные окружения (`DATABASE__HOST`, `DATABASE__PORT`)
2. Docker secrets (`DATABASE__PASSWORD_FILE`)
3. `.env` файл
4. `app.yaml` (нечувствительные настройки)
5. Значения по умолчанию

Чувствительные данные (пароли, JWT ключи) хранятся только в переменных окружения.

## Роли и доступ

- **Admin**: полный доступ - CRUD дашбордов, управление пользователями, настройка доступов
- **Editor**: загрузка CSV файлов, инициирование пересчёта данных
- **Viewer**: только просмотр дашбордов

## API Endpoints

### Auth
- `POST /api/v1/auth/login` - вход в систему
- `POST /api/v1/auth/register-request` - заявка на регистрацию
- `GET /api/v1/auth/me` - профиль текущего пользователя

### Dashboards
- `GET /api/v1/dashboards/my` - список доступных дашбордов
- `GET /api/v1/dashboards/:id` - детали дашборда
- `POST /api/v1/dashboards` - создание (admin)
- `PUT /api/v1/dashboards/:id` - обновление (admin)
- `DELETE /api/v1/dashboards/:id` - удаление (admin)

### Data
- `GET /api/v1/data/aggregated` - агрегированные данные для графиков
- `POST /api/v1/upload/:dashboard_id` - загрузка файлов данных

### Admin
- `GET /api/v1/admin/users` - управление пользователями
- `GET /api/v1/admin/registration-requests` - заявки на регистрацию
- `GET /api/v1/admin/logs` - логи обработки

## Тестирование

```bash
uv run pytest
```

Покрытие включает API, обработку данных и аутентификацию.

## Лицензия

MIT License
