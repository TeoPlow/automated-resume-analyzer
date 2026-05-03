# automated-resume-analyzer

Репозиторий ВКР на тему:
**Система автоматизированной обработки потока резюме для вакансий в IT-компании**

Создание системы автоматизированной обработки потока резюме для вакансий
в IT-компании, а также API для взаимодействия с ней. Система позволяет:

- принимать резюме из разных источников (веб-интерфейс, боты, email-адаптеры, job-порталы);
- автоматически извлекать ключевую информацию из резюме с помощью локальной LLM;
- дедуплицировать кандидатов по контактным данным;
- классифицировать и ранжировать кандидатов по степени соответствия требованиям вакансий
  (многофакторная модель с семантическим сравнением навыков);
- предоставлять API для просмотра и фильтрации резюме специалистами по подбору персонала.

---
## **Запуск:**
```
make run
```

`make run` всегда поднимает проект с чистого состояния:
- останавливает текущий стек;
- удаляет docker volumes;
- запускает сервисы заново.

## **Запуск с демо-данными:**
```
make demo
```

`make demo`:
- очищает volumes;
- запускает стек в фоне;
- заполняет БД примерами кандидатов и вакансий.

Если стек уже запущен и нужно только перезаполнить примеры:
```
make seed-demo
```

Зайти на фронт:
```
127.0.0.1:3000
```
---
## Микросервисная архитектура (MVP)

### Обзор сервисов

| Сервис      | Порт  | Назначение                                                        |
| ----------- | ----- | ----------------------------------------------------------------- |
| **Gateway** | 8000  | Единая точка входа: внешний REST API, аутентификация, rate-limit   |
| **Profile** | 8001  | Приём/загрузка резюме, LLM-парсинг, дедупликация, профили         |
| **Vacancy** | 8002  | CRUD вакансий, нормализация требований                            |
| **Matching**| 8003  | Расчёт релевантности (многофакторный scoring), ранжирование       |
| **Search**  | 8004  | Поисковые запросы, фильтрация, агрегированная выдача для HR       |

### Стек технологий

| Технология                | Роль                                      | Обоснование                                                              |
| ------------------------- | ----------------------------------------- | ------------------------------------------------------------------------ |
| **FastAPI**               | Все сервисы                               | Async, автогенерация OpenAPI, Pydantic-валидация, dependency injection   |
| **PostgreSQL 16**         | Транзакционные данные                     | JSONB, полнотекстовый поиск (`tsvector`), GIN-индексы, зрелая экосистема |
| **MinIO**                 | Хранение файлов резюме                    | S3-совместимый, self-hosted, не требует внешнего облака                   |
| **RabbitMQ**              | Асинхронные события между сервисами       | Topic exchange, dead-letter queues, подтверждения доставки               |
| **Redis**                 | Rate-limit, blacklist токенов             | In-memory, атомарные операции, TTL (в MVP — in-memory хранилище)  |
| **Ollama**                | Языковая модель по API для парсинга резюме | По умолчанию локальный запуск, но возможен и удалённый доступ к модели по API                |
| **sentence-transformers** | Семантическое сравнение навыков            | Cosine similarity через предобученные эмбеддинги                         |

### Обоснование технологических решений

#### Границы применения машинного обучения в MVP

В текущем проекте машинное обучение используется как прикладной компонент, а основной фокус сделан на серверной архитектуре и надёжной интеграции сервисов.

- Используются готовые предобученные модели.
- Обучение и дообучение собственных моделей в рамках проекта не выполняется.
- Для извлечения данных из резюме используется языковая модель через API.
- Языковая модель может быть как локальной (запущенной в своей инфраструктуре), так и удалённой (доступной по API).
- Для семантического сравнения навыков используется готовая embedding-модель.
- Для повышения устойчивости предусмотрены валидация структуры ответа, повторные попытки при ошибках и fallback на точное сравнение навыков.

### Схема взаимодействия сервисов

Все бизнес-сервисы (Profile, Vacancy, Matching, Search) взаимодействуют с PostgreSQL —
каждый со своей схемой. Gateway — единственный сервис, который **не** работает
с PostgreSQL: его хранилище — in-memory (rate-limit, blacklist токенов;
в продакшене можно переключить на Redis).

Search **взаимодействует только с PostgreSQL** (read-only доступ ко всем схемам).
Он не ходит в другие сервисы, не шлёт и не получает события — это чисто read-сервис.

| Сервис      | PostgreSQL       | MinIO | Ollama | RabbitMQ         | Redis | Internal API          |
| ----------- | ---------------- | ----- | ------ | ---------------- | ----- | --------------------- |
| **Gateway** | —                | —     | —      | —                | in-memory | → все сервисы (proxy) |
| **Profile** | R/W (своя схема) | R/W   | запрос | pub + consume    | —     | принимает от Gateway, Matching |
| **Vacancy** | R/W (своя схема) | —     | —      | pub              | —     | принимает от Gateway, Matching |
| **Matching**| R/W (своя схема) | —     | —      | pub + consume    | —     | → Profile, Vacancy    |
| **Search**  | R/O (все схемы)  | —     | —      | —                | —     | принимает от Gateway  |

```
┌──────────────────┐     ┌──────────────────┐
│  HR-специалист   │     │ Внешние источники│
│  (JWT Bearer)    │     │ (API Key)        │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         └───────────┬────────────┘
                     ▼
              ┌─────────────┐
              │   Gateway   │◄──── in-memory (rate-limit, token blacklist)
              │   :8000     │
              └──────┬──────┘
                     │  proxy + заголовки:
                     │  X-Request-Id, X-Actor-Id,
                     │  X-Actor-Type, X-Permissions
        ┌────────────┼────────────┬────────────┐
        ▼            ▼            ▼            ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ Profile  │ │ Vacancy  │ │ Matching │ │  Search  │
  │  :8001   │ │  :8002   │ │  :8003   │ │  :8004   │
  └──┬──┬──┬─┘ └──┬──┬────┘ └──┬──┬────┘ └──┬───────┘
     │  │  │      │  │         │  │          │
     │  │  │      │  │         │  │          │ read-only
     │  │  └──────┼──┼─────────┼──┼──────────┼──────▶ PostgreSQL
     │  │         │  │         │  │
     │  ├────▶ MinIO │         │  │
     │  └────▶ Ollama│         │  │ internal API
     │                │        │  ├──────▶ Profile
     │    events      │        │  └──────▶ Vacancy
     ├────────▶ RabbitMQ ◄─────┘
     │         ▲       │
     │         │       └──────▶ Matching (consume)
     └─────────┘
```

---

## Роли и доступ

### Внешние клиенты

| Клиент                | Способ аутентификации | Описание                                         |
| --------------------- | --------------------- | ------------------------------------------------ |
| **HR-специалист**     | JWT Bearer            | Веб-интерфейс, полный доступ к API               |
| **Внешние источники** | API Key               | Боты, email-адаптеры, job-порталы — только upload |

### Авторизация

- Внешние запросы идут **только через Gateway**.
- Gateway проверяет токен/ключ и прокидывает в downstream-сервисы технические заголовки:
  - `X-Request-Id` — уникальный ID запроса для сквозной трассировки
  - `X-Actor-Id` — ID пользователя или интеграции
  - `X-Actor-Type` — **категория** актора: `hr` | `integration` | `system`
  - `X-Permissions` — **конкретные разрешения** пользователя (через запятую)
- Downstream-сервисы **не проверяют** JWT/API Key самостоятельно — они доверяют заголовкам от Gateway.
- Между собой сервисы используют `X-Internal-Token` — общий секрет, подтверждающий,
  что запрос пришёл из внутренней сети.

**Разница между `X-Actor-Type` и `X-Permissions`:**

- `X-Actor-Type` — **кто** делает запрос. Определяет общий контекст (HR-пользователь,
  автоматическая интеграция или внутренний системный вызов). Используется для логирования,
  аудита и общих проверок (например, интеграция не может менять свои собственные ключи).
- `X-Permissions` — **что конкретно** этот актор может делать. Гранулярные права,
  позволяющие одному HR-специалисту дать полный доступ, а стажёру-HR — только просмотр
  и загрузку резюме без возможности управлять вакансиями.

### Ролевая модель

#### Типы акторов (`X-Actor-Type`)

| Тип           | Описание                                                       |
| ------------- | -------------------------------------------------------------- |
| `hr`          | HR-специалист, авторизован через JWT                           |
| `integration` | Внешний бот/адаптер, авторизован через API Key                 |
| `system`      | Внутренний системный вызов (например, автоматический matching)  |

#### Гранулярные разрешения (`X-Permissions`)

| Разрешение             | Описание                                         | Роли по умолчанию      |
| ---------------------- | ------------------------------------------------ | ---------------------- |
| `resumes:upload`       | Загрузка резюме                                  | admin, hr, integration |
| `candidates:read`      | Просмотр профилей кандидатов                     | admin, hr              |
| `candidates:write`     | Ручная правка профиля кандидата                  | admin, hr              |
| `vacancies:read`       | Просмотр вакансий                                | admin, hr              |
| `vacancies:write`      | Создание, редактирование, смена статуса вакансий | admin, hr              |
| `matching:run`         | Запуск matching                                  | admin, hr              |
| `matching:read`        | Просмотр результатов matching                    | admin, hr              |
| `search:use`           | Поиск и фильтрация                               | admin, hr              |
| `integrations:manage`  | CRUD API-ключей для интеграций                    | admin                  |

#### Пример: HR-стажёр с ограниченными правами

```
X-Actor-Type: hr
X-Permissions: resumes:upload,candidates:read,search:use
```

Такой пользователь может загружать резюме, просматривать кандидатов и пользоваться поиском,
но **не может** создавать вакансии, запускать matching или управлять API-ключами.

---

## Границы ответственности сервисов

### 1) Gateway

**Назначение:** единый внешний API, authentication/authorization, rate-limiting, маршрутизация.

Функции:
- Проверка JWT Bearer / API Key
- Rate-limit по методу скользящего окна (sliding window) — ограничение
  количества запросов от одного клиента за фиксированный промежуток времени.
  Например, не более 120 запросов в минуту. При превышении лимита возвращается
  HTTP 429 Too Many Requests. В MVP счётчики хранятся в оперативной памяти
  (можно переключить на Redis для продакшена)
- Проксирование запросов в downstream-сервисы с обогащением заголовков
- Управление сессиями: login, refresh, logout
- CRUD API-ключей для интеграций (только admin)

**Не хранит** бизнес-данные кандидатов, вакансий, матчинга.

**Хранит** (в оперативной памяти, в продакшене — Redis):
- Счётчики rate-limit (deque на клиента)
- Blacklist отозванных refresh-токенов (InMemoryAuthStore)

### 2) Profile

**Назначение:** полный цикл от приёма файла резюме до готового профиля кандидата.

Функции:
- Приём и валидация файла резюме (формат, размер, magic bytes)
- Загрузка файла в MinIO
- Извлечение текста из PDF/DOCX/TXT
- Гибридный парсинг резюме: предобработка regex-правилами + LLM (Ollama) для сложных полей
- Дедупликация кандидатов по email/телефону
- Создание/обновление `candidate_profile` (merge данных из нескольких резюме)
- Публикация событий `resume.uploaded`, `candidate.profile.updated`

**Хранит** (PostgreSQL):
- `candidates` — базовые данные кандидата
- `resumes` — метаданные каждого загруженного файла + извлечённый текст
- `candidate_profiles` — структурированный профиль (JSONB), агрегированный из всех резюме кандидата

**Хранит** (MinIO):
- bucket `resumes-raw` — оригиналы PDF/DOCX/TXT

### 3) Vacancy

**Назначение:** управление вакансиями и нормализация требований.

Функции:
- CRUD вакансий с жизненным циклом (lifecycle)
- Нормализация требований (lowercase, trim)
- Публикация событий `vacancy.created`, `vacancy.updated`

**Жизненный цикл вакансии (lifecycle):**

```
draft → open → closed → archived
```

| Статус     | Описание                                                                    | Переходы            |
| ---------- | ----------------------------------------------------------------------- | -------------------- |
| `draft`    | Черновик. Вакансия создана, но ещё не активна. Не участвует в matching, не видна в поиске по умолчанию. HR может редактировать требования и описание. | → `open`            |
| `open`     | Активная вакансия. Участвует в matching (автоматическом и ручном), видна в поиске. При переходе в `open` публикуется событие `vacancy.created`, которое запускает scoring всех кандидатов. | → `closed`          |
| `closed`   | Набор завершён. Вакансия не участвует в новых matching, результаты сохраняются для просмотра. | → `archived`        |
| `archived` | Архивная. Не отображается в списках по умолчанию. Хранится для истории и аналитики.           | конечный статус, но вакансию можно заново переместить в `draft`       |

**Хранит** (PostgreSQL):
- `vacancies` — данные вакансии
- `vacancy_requirements` — требуемые навыки с категорией и приоритетом

### 4) Matching

**Назначение:** расчёт релевантности кандидатов к вакансиям, ранжирование, объяснение score.

Функции:
- Многофакторная оценка: skills (семантическая), experience, grade, location, salary
- Семантическое сравнение навыков через sentence-transformers (cosine similarity)
- Fallback на точное совпадение, если embedding-модель недоступна
- Ранжирование кандидатов по вакансии
- Хранение результатов с детальным объяснением каждого фактора
- Публикация события `matching.completed`

**Хранит** (PostgreSQL):
- `match_runs` — запуски matching с конфигурацией и статусом
- `match_results` — покомпонентные scores и итоговый ранг
- `match_explanations` — человекочитаемые объяснения по каждому фактору

**Загружает при старте:**
- sentence-transformers модель `paraphrase-multilingual-MiniLM-L12-v2` (~120 MB, ~300 MB RAM)

**Почему именно `paraphrase-multilingual-MiniLM-L12-v2`?**
- Поддержка 50+ языков, включая русский — важно, так как навыки могут быть
  на русском («управление проектами») и английском («project management»)
- Компактность: 120 MB весов, 300 MB RAM — работает на любом сервере
- Одна из наиболее популярных мультиязычных embedding-моделей с хорошей документацией

### 5) Search

**Назначение:** поисковые запросы и агрегированная выдача для HR.

Функции:
- Полнотекстовый поиск по кандидатам (PostgreSQL `tsvector`)
- Фильтрация по навыкам (GIN-индекс), грейду, локации, стажу, зарплате, статусу
- Объединённая выдача: кандидат + вакансия + результаты matching (SQL JOIN)
- Агрегированная статистика (summary)

> **Примечание.** В MVP Search читает данные напрямую из PostgreSQL (один кластер,
> разные схемы). В продакшене можно вынести в Elasticsearch или отдельную read-реплику.

---

## Схема данных

### MinIO

| Bucket        | Содержимое                    |
| ------------- | ----------------------------- |
| `resumes-raw` | Оригиналы файлов PDF/DOCX/TXT |

### PostgreSQL — Profile

#### Таблица `candidates`

| Поле         | Тип          | Описание                          |
| ------------ | ------------ | --------------------------------- |
| `id`         | UUID PK      | Идентификатор кандидата           |
| `full_name`  | VARCHAR(255) | ФИО                              |
| `email`      | VARCHAR(255) | Email (UNIQUE, nullable)          |
| `phone`      | VARCHAR(50)  | Телефон (UNIQUE, nullable)        |
| `created_at` | TIMESTAMPTZ  | Дата создания                    |
| `updated_at` | TIMESTAMPTZ  | Дата обновления                  |

#### Таблица `resumes`

| Поле          | Тип          | Описание                                 |
| ------------- | ------------ | ---------------------------------------- |
| `id`          | UUID PK      | Идентификатор резюме                     |
| `candidate_id`| UUID FK      | Связь с кандидатом                       |
| `file_key`    | VARCHAR(512) | Ключ файла в MinIO                       |
| `source`      | VARCHAR(50)  | Источник: `web`, `bot`, `email`, `portal` |
| `external_id` | VARCHAR(255) | Внешний ID из источника (nullable)        |
| `status`      | VARCHAR(20)  | Статус: `uploaded` → `processing` → `parsed` / `failed` |
| `raw_text`    | TEXT         | Извлечённый текст (после text extraction) |
| `parsed_data` | JSONB        | Результат LLM-парсинга (структура ниже)  |
| `error_detail`| TEXT         | Причина ошибки, если status = `failed`    |
| `created_at`  | TIMESTAMPTZ  | Дата загрузки                            |

#### Таблица `candidate_profiles`

| Поле               | Тип          | Описание                                      |
| ------------------ | ------------ | --------------------------------------------- |
| `id`               | UUID PK      | Идентификатор профиля                         |
| `candidate_id`     | UUID FK UQ   | Связь с кандидатом (1:1)                      |
| `data`             | JSONB        | Агрегированный профиль (merge из всех резюме) |
| `skills`           | TEXT[]       | Массив навыков (для GIN-индекса)              |
| `grade`            | VARCHAR(20)  | Выведенный грейд: `intern`/`junior`/`middle`/`senior`/`lead` |
| `location`         | VARCHAR(255) | Локация кандидата                             |
| `experience_years` | NUMERIC(4,1) | Общий стаж (в годах)                          |
| `salary_expectation` | INTEGER    | Ожидания по зарплате (nullable)               |
| `updated_at`       | TIMESTAMPTZ  | Дата последнего обновления                    |

### PostgreSQL — Vacancy

#### Таблица `vacancies`

| Поле          | Тип          | Описание                                          |
| ------------- | ------------ | ------------------------------------------------- |
| `id`          | UUID PK      | Идентификатор вакансии                            |
| `title`       | VARCHAR(255) | Название вакансии                                 |
| `description` | TEXT         | Подробное описание                                |
| `department`  | VARCHAR(100) | Отдел/команда                                     |
| `location`    | VARCHAR(255) | Локация (или `remote`)                            |
| `grade`       | TEXT[]       | Требуемые грейды (1+ значений, напр. `["junior","middle"]`) |
| `salary_min`  | INTEGER      | Нижняя граница зарплатной вилки (nullable)        |
| `salary_max`  | INTEGER      | Верхняя граница зарплатной вилки (nullable)        |
| `status`      | VARCHAR(20)  | Lifecycle: `draft` → `open` → `closed` → `archived` |
| `created_at`  | TIMESTAMPTZ  | Дата создания                                     |
| `updated_at`  | TIMESTAMPTZ  | Дата обновления                                   |

#### Таблица `vacancy_requirements`

| Поле                  | Тип          | Описание                                    |
| --------------------- | ------------ | ------------------------------------------- |
| `id`                  | UUID PK      | Идентификатор требования                    |
| `vacancy_id`          | UUID FK      | Связь с вакансией                           |
| `skill`               | VARCHAR(100) | Навык (нормализованный: lowercase, trimmed) |
| `category`            | VARCHAR(50)  | Категория: `hard`, `soft`, `tool`, `language` |
| `priority`            | VARCHAR(20)  | Приоритет: `required`, `preferred`, `nice_to_have` |
| `min_experience_years`| NUMERIC(4,1) | Мин. стаж по этому навыку (nullable)        |

### PostgreSQL — Matching

#### Таблица `match_runs`

| Поле              | Тип          | Описание                                     |
| ----------------- | ------------ | -------------------------------------------- |
| `id`              | UUID PK      | Идентификатор запуска                        |
| `vacancy_id`      | UUID         | Вакансия, для которой запущен matching        |
| `status`          | VARCHAR(20)  | Статус: `running` → `completed` / `failed`  |
| `config`          | JSONB        | Конфигурация: веса факторов, пороги          |
| `total_candidates`| INTEGER      | Кол-во оценённых кандидатов                  |
| `started_at`      | TIMESTAMPTZ  | Время начала                                 |
| `completed_at`    | TIMESTAMPTZ  | Время завершения (nullable)                  |

#### Таблица `match_results`

| Поле               | Тип          | Описание                          |
| ------------------ | ------------ | --------------------------------- |
| `id`               | UUID PK      | Идентификатор результата          |
| `run_id`           | UUID FK      | Связь с запуском                  |
| `candidate_id`     | UUID         | Кандидат                          |
| `vacancy_id`       | UUID         | Вакансия                          |
| `final_score`      | NUMERIC(5,2) | Итоговый score (0–100)            |
| `skill_score`      | NUMERIC(5,2) | Компонент: навыки (0–100)         |
| `experience_score` | NUMERIC(5,2) | Компонент: опыт (0–100)          |
| `grade_score`      | NUMERIC(5,2) | Компонент: грейд (0–100)         |
| `location_score`   | NUMERIC(5,2) | Компонент: локация (0–100)       |
| `salary_score`     | NUMERIC(5,2) | Компонент: зарплата (0–100)      |
| `rank`             | INTEGER      | Позиция в рейтинге по вакансии   |

#### Таблица `match_explanations`

| Поле        | Тип          | Описание                                         |
| ----------- | ------------ | ------------------------------------------------ |
| `id`        | UUID PK      | Идентификатор                                    |
| `result_id` | UUID FK      | Связь с `match_results`                          |
| `factor`    | VARCHAR(50)  | Фактор: `skills`, `experience`, `grade`, `location`, `salary` |
| `detail`    | TEXT         | Человекочитаемое объяснение                      |
| `score`     | NUMERIC(5,2) | Score этого фактора                              |
| `weight`    | NUMERIC(3,2) | Вес этого фактора в формуле                      |
| `impact`    | NUMERIC(5,2) | Вклад в итоговый score (score × weight)          |

> **Для MVP** — один PostgreSQL-кластер с разными схемами на сервис. Каждый сервис
> владеет своими таблицами и не пишет в чужие. Search имеет read-only доступ ко всем схемам.

---

## Pipeline обработки резюме

Ключевая подсистема проекта. Полный путь от загрузки файла до готового профиля кандидата.

### Обзор этапов

```
1. Upload        2. Text Extract     3a. Regex         3b. LLM Parse     4. Dedup        5. Profile
─────────────    ──────────────────   ──────────────    ────────────────   ───────────    ──────────────
  HTTP POST  →    PyMuPDF / docx  →    email, phone →    Ollama qwen2.5 →  email/phone → merge + save
  validate       → raw_text            telegram        → parsed JSON       → find/create  → event
  → MinIO                               linkedin                             candidate
  → resume record
  → event resume.uploaded
```

### Этап 1 — Загрузка файла

Клиент отправляет `POST /api/v1/profiles/resumes/upload` (multipart).

Profile HTTP-handler:
1. Валидирует файл:
   - Допустимые форматы: PDF, DOCX, DOC, TXT
   - Максимальный размер: 10 MB
   - Проверка magic bytes (сигнатуры файла), а не только расширения
2. Загружает оригинал в MinIO (`resumes-raw/{uuid}.{ext}`)
3. Создаёт запись `resume` со статусом `uploaded`
4. Публикует событие `resume.uploaded` в RabbitMQ
5. Возвращает клиенту `resume_id` и статус `uploaded`

> Загрузка возвращает ответ мгновенно. Тяжёлый парсинг выполняется асинхронно.

### Этап 2 — Извлечение текста

Profile-worker (consumer `resume.uploaded`) забирает событие и:
1. Скачивает файл из MinIO
2. Определяет формат по magic bytes
3. Извлекает текст:
   - **PDF** → `PyMuPDF` (fitz): `page.get_text()` для каждой страницы
   - **DOCX** → `python-docx`: итерация по параграфам
   - **DOC** → `python-docx` (через промежуточную конвертацию) или antiword
   - **TXT** → прямое чтение с определением кодировки (UTF-8, CP1251)
4. Сохраняет `raw_text` в запись `resume`
5. Обновляет статус на `processing`

### Этап 3 — Структурный парсинг (гибридный подход: правила + LLM)

Парсинг разделён на два этапа для повышения точности и надёжности:

#### Этап 3a — Предобработка regex-правилами

Из текста резюме извлекаются поля, которые имеют **предсказуемый формат** и надёжно
достаются регулярными выражениями:

| Поле       | Метод извлечения                                          |
| ---------- | ---------------------------------------------------------- |
| `email`    | regex: `[\w.-]+@[\w.-]+\.\w+`                              |
| `phone`    | regex: `+7|8` + цифры, скобки, дефисы                   |
| `telegram` | regex: `@[\w]+`                                            |
| `linkedin` | regex: `linkedin\.com/in/[\w-]+`                           |
| `github`   | regex: `github\.com/[\w-]+`                                |

Эти поля извлекаются до LLM и передаются в промпт как «уже известные». Это:
1. Повышает точность — LLM иногда «галлюцинирует» контакты (меняет цифры телефона),
   regex даёт точное значение.
2. Служит fallback — если LLM вернёт невалидный JSON, контакты всё равно будут
   извлечены для дедупликации.
3. Снижает нагрузку на LLM — модель концентрируется на сложных полях.

#### Этап 3b — LLM-парсинг (Ollama)

Profile-worker отправляет извлечённый текст в Ollama для извлечения сложных
структурированных полей (опыт, навыки, образование, summary).

**System prompt:**
```
You are a resume parser. Extract structured information from the resume text below.
Return ONLY valid JSON, no extra text. If a field cannot be determined, use null.
```

**User prompt:**
```
Parse this resume and extract the following fields:
- full_name (string)
- contacts: { email, phone, telegram, linkedin } (strings or null)
- location (string or null)
- summary (string — brief professional summary, 1-2 sentences)
- skills (array of strings — ALL technical and soft skills mentioned)
- experience (array of objects, each with: company, position, start_date, end_date,
  description, technologies)
- education (array of objects: institution, degree, field, graduation_year)
- languages (array of objects: language, level)
- total_experience_years (number — total professional experience)
- desired_salary (number or null)
- desired_position (string or null)

Resume text:
---
{raw_text}
---
```

**Пример результата LLM:**
```json
{
  "full_name": "Иванов Иван Сергеевич",
  "contacts": {
    "email": "ivanov@example.com",
    "phone": "+7 999 123-45-67",
    "telegram": "@ivanov_dev",
    "linkedin": null
  },
  "location": "Москва",
  "summary": "Backend-разработчик с 4-летним опытом в Python и микросервисной архитектуре",
  "skills": ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes", "Git", "REST API", "asyncio"],
  "experience": [
    {
      "company": "ООО Технологии",
      "position": "Backend-разработчик",
      "start_date": "2022-03",
      "end_date": "2026-01",
      "description": "Разработка микросервисов на FastAPI, проектирование API, оптимизация SQL-запросов",
      "technologies": ["Python", "FastAPI", "PostgreSQL", "Docker"]
    },
    {
      "company": "Стартап X",
      "position": "Junior Python Developer",
      "start_date": "2021-06",
      "end_date": "2022-02",
      "description": "Разработка REST API на Django, написание юнит-тестов",
      "technologies": ["Python", "Django", "SQLite"]
    }
  ],
  "education": [
    {
      "institution": "МГТУ им. Баумана",
      "degree": "Бакалавр",
      "field": "Информатика и вычислительная техника",
      "graduation_year": 2021
    }
  ],
  "languages": [
    { "language": "Русский", "level": "родной" },
    { "language": "Английский", "level": "B2" }
  ],
  "total_experience_years": 4.5,
  "desired_salary": 250000,
  "desired_position": "Senior Backend Developer"
}
```

Profile-worker:
1. Объединяет regex-поля (контакты) с LLM-полями (опыт, навыки и т.д.) в единый `parsed_data`
2. При конфликте (напр. LLM и regex дали разные email) — приоритет у regex-извлечения
3. Валидирует итоговый JSON по Pydantic-схеме
4. Если LLM вернула невалидный ответ — повторная попытка (до 2 retry)
5. Сохраняет `parsed_data` в запись `resume`

### Этап 4 — Дедупликация кандидатов

После успешного парсинга Profile-worker ищет существующего кандидата:

1. Извлекает `email` и `phone` из `parsed_data.contacts`
2. Если `email != null` → `SELECT * FROM candidates WHERE email = :email`
3. Если не найден и `phone != null` → `SELECT * FROM candidates WHERE phone = :phone`
4. **Найден** → привязывает новое резюме к существующему кандидату
5. **Не найден** → создаёт нового кандидата (`INSERT INTO candidates`)

### Этап 5 — Формирование/обновление профиля

Profile-worker формирует агрегированный профиль на основе **всех** резюме кандидата:

1. Получает все резюме кандидата со статусом `parsed`
2. **Merge-логика:**
   - `skills` — объединение (union) всех навыков из всех резюме
   - `experience` — объединение, с дедупликацией по `company + position + start_date`
   - `education` — объединение, дедупликация по `institution + degree`
   - `location`, `desired_salary`, `desired_position`, `summary` — берутся из **последнего** загруженного резюме
   - `total_experience_years` — максимум из всех резюме
   - `grade` — берётся из последнего или выводится из стажа
3. Сохраняет/обновляет `candidate_profiles`
4. Обновляет статус резюме на `parsed`
5. Публикует событие `candidate.profile.updated`

### Статусы резюме

```
uploaded → processing → parsed
                     ↘ failed
```

| Статус       | Описание                                        |
| ------------ | ----------------------------------------------- |
| `uploaded`   | Файл принят, сохранён в MinIO                  |
| `processing` | Извлечение текста и/или LLM-парсинг в процессе  |
| `parsed`     | Успешно распарсено, профиль обновлён            |
| `failed`     | Ошибка на любом этапе (причина в `error_detail`) |

---

## Алгоритм матчинга

### Многофакторная модель оценки

Итоговый score кандидата по вакансии вычисляется как взвешенная сумма пяти факторов:

$$S_{final} = w_1 \cdot S_{skills} + w_2 \cdot S_{experience} + w_3 \cdot S_{grade} + w_4 \cdot S_{location} + w_5 \cdot S_{salary}$$

Где каждый компонент $S_i \in [0, 100]$, а веса $w_i$ суммируются до 1.0.

**Веса по умолчанию** (настраиваемые при запуске matching):

| Фактор     | Вес   | Обоснование                                |
| ---------- | ----- | ------------------------------------------ |
| Skills     | 0.40  | Ключевой фактор соответствия в IT          |
| Experience | 0.25  | Стаж определяет уровень владения           |
| Grade      | 0.15  | Соответствие по уровню должности           |
| Location   | 0.10  | Совместимость по локации/удалёнке          |
| Salary     | 0.10  | Совпадение зарплатных ожиданий             |

HR может переопределить веса при запуске `POST /api/v1/matching/run` через параметр `weights`.

### Компонент 1 — Skills Score

Самый сложный и важный компонент. Работает в два уровня.

#### Уровень 1 — Семантическое сравнение (sentence-transformers)

Основной метод сравнения навыков через **cosine similarity** между эмбеддингами:

1. Matching-сервис лениво загружает модель `paraphrase-multilingual-MiniLM-L12-v2` при первом запросе
2. Кодирует все требования вакансии и навыки кандидата в векторы через `model.encode()`
3. Вычисляет матрицу cosine similarity (скалярное произведение нормализованных векторов)
4. Для каждого требования находит максимально похожий навык кандидата
5. Если `similarity ≥ 0.6` → навык считается покрытым
6. Если `similarity < 0.6` → навык не покрыт

**Пример:**
- Требование: `FastAPI`, кандидат знает `Starlette` → similarity ≈ 0.82 → учитывается
- Требование: `Kubernetes`, кандидат знает `Java` → similarity ≈ 0.15 → не учитывается

#### Уровень 2 — Fallback на точное совпадение

Если embedding-модель недоступна (ошибка загрузки, нехватка памяти), система автоматически
переключается на exact match: сравнение навыков в lowercase без эмбеддингов.

#### Формула Skill Score

$$S_{skills} = \frac{\text{matched}}{\text{total\_requirements}} \times 100$$

Где `matched` — количество требований вакансии с similarity ≥ 0.6 (или точным совпадением в fallback-режиме).

| Условие | Score |
|---|---|
| Нет требований к навыкам | 100 |
| Нет навыков у кандидата | 0 |

### Компонент 2 — Experience Score

$$S_{experience} = \min\left(\frac{Y_{candidate}}{Y_{required}}, 1.0\right) \times 100$$

Где $Y_{required}$ — среднее значение `min_experience_years` из требований вакансии.

| Условие                                | Score |
| --------------------------------------- | ----- |
| `experience ≥ required`                 | 100   |
| `experience < required`                 | пропорционально (`ratio × 100`) |
| Опыт кандидата не указан                | 50    |
| Требования к опыту не указаны            | 80    |

### Компонент 3 — Grade Score

У вакансии может быть указано несколько допустимых грейдов (например, `["junior", "middle"]`).
Берётся минимальное расстояние до ближайшего допустимого грейда.

$$S_{grade} = \max(100 - \text{min\_dist} \times 30, \ 0)$$

| Соответствие                                  | Score |
| --------------------------------------------- | ----- |
| Грейд кандидата входит в список допустимых      | 100   |
| Разница в 1 уровень                             | 70    |
| Разница в 2 уровня                             | 40    |
| Разница в 3 уровня                             | 10    |
| Разница ≥ 4 уровней                            | 0     |
| Грейд вакансии не указан                        | 80    |
| Грейд кандидата не определён                    | 50    |

### Компонент 4 — Location Score

| Условие                                    | Score |
| ------------------------------------------ | ----- |
| Вакансия remote или локация не указана  | 100   |
| Города совпали                              | 100   |
| Локация кандидата не указана            | 50    |
| Разные города                                | 30    |

### Компонент 5 — Salary Score

| Условие                                              | Score |
| ---------------------------------------------------- | ----- |
| Ожидания в пределах вилки `[salary_min, salary_max]` | 100   |
| Ожидания ниже вилки                                | 90    |
| Ожидания выше вилки                                | $\max(100 - \text{overshoot} \times 100, \ 0)$ |
| Нет данных о зарплате у кандидата              | 70    |
| Нет вилки у вакансии                              | 80    |

Где `overshoot = (salary - salary_max) / salary_max`.
Например: ожидания 300 000, вилка до 250 000 → overshoot = 0.2 → score = 80.

### Explainability

Для каждого `match_result` формируются записи `match_explanations`, содержащие
человекочитаемое объяснение по каждому фактору. Пример:

```json
[
  {
    "factor": "skills",
    "score": 78.50,
    "weight": 0.40,
    "impact": 31.40,
    "detail": "Совпадение: 5/7. Python ≈ Python (100%); FastAPI ≈ FastAPI (100%); PostgreSQL ≈ PostgreSQL (100%); Docker ≈ Docker (100%); Redis ≈ Redis (100%)"
  },
  {
    "factor": "experience",
    "score": 100.00,
    "weight": 0.25,
    "impact": 25.00,
    "detail": "4.5 лет ≥ требуемых 3.0"
  },
  {
    "factor": "grade",
    "score": 70.00,
    "weight": 0.15,
    "impact": 10.50,
    "detail": "Грейд middle, ожидается ['senior']"
  },
  {
    "factor": "location",
    "score": 100.00,
    "weight": 0.10,
    "impact": 10.00,
    "detail": "Удалённая работа или локация не указана"
  },
  {
    "factor": "salary",
    "score": 80.00,
    "weight": 0.10,
    "impact": 8.00,
    "detail": "Ожидания 250000 выше вилки [180000–220000]"
  }
]
```

**Итоговый score:** $31.40 + 25.00 + 10.50 + 10.00 + 8.00 = 84.90$

### Автоматический и ручной matching

| Триггер                                | Действие                                          |
| --------------------------------------- | ------------------------------------------------- |
| `POST /api/v1/matching/run`            | HR вручную запускает matching по вакансии          |
| Событие `candidate.profile.updated`     | Автоматический scoring кандидата по всем open-вакансиям |
| Событие `vacancy.created`               | Автоматический scoring всех active кандидатов по новой вакансии |
| Событие `vacancy.updated`               | Инвалидация существующих scores по вакансии        |

---

## Внешние REST API (через Gateway)

Все внешние запросы идут через Gateway. Ниже — полный внешний контракт.

### Gateway API

- `GET /api/v1/health` — healthcheck gateway
- `GET /api/v1/me` — данные текущего пользователя (на основе JWT)
- `POST /api/v1/auth/login` — логин HR, выдача `access_token` + `refresh_token`
- `POST /api/v1/auth/refresh` — обновление access token по refresh token
- `POST /api/v1/auth/logout` — инвалидировать refresh token (добавить в blacklist)

> Далее — только роль `admin`
- `POST /api/v1/integrations/keys` — создать API Key для бота/интеграции
- `GET /api/v1/integrations/keys` — список ключей
- `POST /api/v1/integrations/keys/{key_id}/rotate` — ротация (плановая замена ключа)
- `DELETE /api/v1/integrations/keys/{key_id}` — отозвать ключ

### Profile API

- `POST /api/v1/profiles/resumes/upload`
  - multipart: `file` (обязательно), `source` (обязательно), `external_id` (опционально)
  - результат: `resume_id`, `candidate_id`, `status: "uploaded"`
  - роли: `hr`, `integration`
- `GET /api/v1/profiles/candidates/{candidate_id}`
  - результат: полный профиль кандидата
- `PATCH /api/v1/profiles/candidates/{candidate_id}`
  - ручная корректировка профиля HR-специалистом
- `GET /api/v1/profiles/candidates/{candidate_id}/resumes`
  - список всех резюме кандидата с их статусами

### Vacancy API

- `POST /api/v1/vacancies` — создать вакансию (статус `draft`)
  - body: `title`, `description`, `department`, `location`, `grade[]` (массив допустимых грейдов), `salary_min`, `salary_max`, `requirements[]`
- `GET /api/v1/vacancies/{vacancy_id}` — получить вакансию с требованиями
- `PATCH /api/v1/vacancies/{vacancy_id}` — обновить вакансию (включая смену статуса)
- `GET /api/v1/vacancies` — список вакансий с пагинацией и фильтрами

### Matching API

- `POST /api/v1/matching/run` — запустить matching по вакансии
  - body: `vacancy_id` (обязательно), `candidate_ids?` (опционально — если не указано, берутся все active), `top_k?` (макс. кол-во результатов), `force_recompute?` (пересчитать, даже если есть актуальные результаты), `weights?` (переопределение весов факторов)
- `GET /api/v1/matching/results/{run_id}` — результаты конкретного запуска
- `GET /api/v1/matching/vacancies/{vacancy_id}` — лучшие кандидаты по вакансии (последний run)
- `GET /api/v1/matching/candidates/{candidate_id}/vacancies` — подходящие вакансии для кандидата

### Search API

- `GET /api/v1/search/candidates`
  - фильтры: `skills`, `grade`, `location`, `experience_years_min`, `experience_years_max`, `salary_min`, `salary_max`, `status`
  - полнотекстовый поиск: `q` (по ФИО, навыкам, описанию опыта)
- `GET /api/v1/search/vacancies`
  - фильтры: `status`, `department`, `grade`, `location`
- `GET /api/v1/search/matches`
  - фильтры: `vacancy_id`, `min_score`, `grade`
  - объединённая выдача: кандидат + его score + объяснение
- `GET /api/v1/search/summary`
  - агрегированная статистика: количество кандидатов по грейдам, навыкам, локациям

---

## Внутренние API между сервисами

Формат URL: `http://{service}:{port}/internal/v1/...`

Все internal-запросы содержат заголовок `X-Internal-Token` для верификации.

### Profile internal

| Метод | Endpoint                               | Описание                              |
| ----- | -------------------------------------- | ------------------------------------- |
| GET   | `/internal/v1/candidates/{id}`         | Данные кандидата + профиль            |
| POST  | `/internal/v1/candidates/bulk-get`     | Данные нескольких кандидатов (по ids)  |

### Vacancy internal

| Метод | Endpoint                               | Описание                              |
| ----- | -------------------------------------- | ------------------------------------- |
| GET   | `/internal/v1/vacancies/{id}`          | Вакансия + требования                 |
| POST  | `/internal/v1/vacancies/bulk-get`      | Несколько вакансий (по ids)           |

### Matching internal

| Метод | Endpoint                                      | Описание                                         |
| ----- | --------------------------------------------- | ------------------------------------------------ |
| POST  | `/internal/v1/run-for-vacancy/{vacancy_id}`   | Запустить matching по вакансии (триггер из событий) |
| GET   | `/internal/v1/results/by-vacancy/{vacancy_id}` | Результаты последнего run по вакансии           |

---

## События и асинхронное взаимодействие

### Инфраструктура

- **Exchange:** `ara.events` (topic, durable)
- **Routing key:** совпадает с `event_type` (напр. `resume.uploaded`, `candidate.profile.updated`)
- Каждый consumer создаёт свою **durable queue** с binding по routing key
- **Dead-letter exchange:** `ara.events.dlx` — для необработанных сообщений

### Контракт событий

| Событие                         | Producer | Consumers                | Routing Key                    |
| -------------------------------- | -------- | ----------------------- | ------------------------------ |
| `resume.uploaded`                | Profile  | Profile (parser worker) | `resume.uploaded`              |
| `candidate.profile.updated`     | Profile  | Matching                | `candidate.profile.updated`    |
| `vacancy.created`               | Vacancy  | Matching                | `vacancy.created`              |
| `vacancy.updated`               | Vacancy  | Matching                | `vacancy.updated`              |
| `matching.completed`            | Matching | (аудит/уведомления)     | `matching.completed`           |

### Формат события (envelope)

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "candidate.profile.updated",
  "event_version": 1,
  "occurred_at": "2026-04-05T10:00:00Z",
  "producer": "profile-service",
  "request_id": "req-abc-123",
  "payload": {
    "candidate_id": "...",
    "skills": ["Python", "FastAPI", "PostgreSQL"],
    "grade": "middle",
    "experience_years": 4.5
  }
}
```

### Payload по типам событий

**`resume.uploaded`:**
```json
{
  "resume_id": "uuid",
  "candidate_id": "uuid (null если новый)",
  "file_key": "resumes-raw/abc123.pdf",
  "source": "web"
}
```

**`candidate.profile.updated`:**
```json
{
  "candidate_id": "uuid",
  "skills": ["Python", "FastAPI", "PostgreSQL"],
  "grade": "middle",
  "experience_years": 4.5
}
```

**`vacancy.created` / `vacancy.updated`:**
```json
{
  "vacancy_id": "uuid",
  "status": "open",
  "changed_fields": ["requirements", "grade"]
}
```

**`matching.completed`:**
```json
{
  "run_id": "uuid",
  "vacancy_id": "uuid",
  "total_scored": 42,
  "top_score": 94.50
}
```

---

## Сквозные бизнес-потоки

### Поток A — Приём резюме и формирование профиля кандидата

**Синхронная часть** (клиент ждёт ответ):

1. Клиент отправляет `POST /api/v1/profiles/resumes/upload` с файлом резюме.
2. **Gateway** проверяет JWT/API Key, добавляет заголовки (`X-Actor-Id`, `X-Permissions`, ...),
   проксирует в Profile.
3. **Profile HTTP** валидирует файл (формат, размер, magic bytes).
4. **Profile HTTP** загружает файл в **MinIO** (`resumes-raw/{uuid}.{ext}`).
5. **Profile HTTP** создаёт запись `resume` в **PostgreSQL** со статусом `uploaded`.
6. **Profile HTTP** публикует событие `resume.uploaded` в **RabbitMQ**.
7. Клиент получает ответ: `{ resume_id, status: "uploaded" }`.

**Асинхронная часть** (выполняется в фоне через Profile-worker):

8. **Profile Worker** получает событие `resume.uploaded` из RabbitMQ.
9. **Profile Worker** скачивает файл из **MinIO**.
10. **Profile Worker** извлекает текст (PyMuPDF / python-docx / plain text).
11. **Profile Worker** извлекает контакты regex-правилами (email, phone, telegram, linkedin).
12. **Profile Worker** отправляет текст в **Ollama** для извлечения сложных полей
    (опыт, навыки, образование, summary). Получает структурированный JSON.
13. **Profile Worker** объединяет regex-поля и LLM-поля в единый `parsed_data`.
14. **Profile Worker** выполняет дедупликацию: ищет кандидата по email/телефону
    в **PostgreSQL**. Если найден — привязывает резюме. Если нет — создаёт нового.
15. **Profile Worker** формирует/обновляет `candidate_profile` (merge данных из всех резюме).
16. **Profile Worker** обновляет статус резюме на `parsed`.
17. **Profile Worker** публикует событие `candidate.profile.updated` в **RabbitMQ**.
18. **Matching** получает событие → запускает автоматический scoring кандидата
    по всем open-вакансиям.

### Поток B — Создание вакансии

1. HR отправляет `POST /api/v1/vacancies` с данными вакансии и требованиями.
2. Gateway валидирует JWT, проксирует в Vacancy.
3. Vacancy нормализует требования (lowercase, trim), сохраняет в PostgreSQL.
4. Vacancy публикует `vacancy.created`.
5. Matching получает событие → запускает автоматический scoring всех active-кандидатов.

### Поток C — Ручной matching

1. HR запускает `POST /api/v1/matching/run` с `vacancy_id` и опциональными `weights`.
2. Gateway валидирует JWT, проксирует в Matching.
3. Matching создаёт `match_run` со статусом `running`.
4. Matching получает данные вакансии через `GET /internal/v1/vacancies/{id}`.
5. Matching получает кандидатов через `POST /internal/v1/candidates/bulk-get`.
6. Для каждого кандидата:
   a. Семантическое сравнение навыков (sentence-transformers) с fallback на exact match
   b. Расчёт всех 5 компонентов ($S_{skills}$, $S_{experience}$, $S_{grade}$, $S_{location}$, $S_{salary}$)
   c. Вычисление $S_{final}$ по формуле с весами
   d. Генерация объяснений по каждому фактору
7. Matching ранжирует результаты по $S_{final}$, присваивает `rank`.
8. Сохраняет `match_results` + `match_explanations`.
9. Обновляет `match_run` на `completed`.
10. Публикует `matching.completed`.

### Поток D — Просмотр и фильтрация

1. HR вызывает `GET /api/v1/search/candidates` или `/matches` с фильтрами.
2. Gateway валидирует JWT, проксирует в Search.
3. Search выполняет SQL-запрос с JOIN по таблицам candidates, candidate_profiles,
   vacancies, match_results.
4. Используются индексы: GIN на `skills`, tsvector на полнотекстовых полях,
   btree на salary/experience.
5. Результат возвращается с пагинацией.

---

## Правила взаимодействия сервисов

1. Внешние клиенты **не ходят** напрямую во внутренние сервисы — только через Gateway.
2. Все изменяющие операции (create/update/run) — через свои доменные сервисы.
3. Межсервисные синхронные вызовы — только для необходимых данных в runtime
   (Matching → Profile/Vacancy).
4. Тяжёлые и массовые операции — через события RabbitMQ (парсинг, авто-matching).
5. Все сервисы поддерживают `X-Request-Id` для сквозной трассировки.
6. В MVP Search читает данные напрямую из PostgreSQL (один кластер, разные схемы).
7. Каждый сервис **владеет** своими таблицами — другие сервисы не пишут в чужие данные.
8. Internal API защищён `X-Internal-Token` — общий секрет для inter-service вызовов.

---

## Инфраструктура (Docker Compose)

| Сервис           | Image / Build                      | Зависимости                        |
| ---------------- | ---------------------------------- | ---------------------------------- |
| `gateway`        | build: .                           | redis                              |
| `profile`        | build: .                           | postgresql, minio, rabbitmq, ollama |
| `vacancy`        | build: .                           | postgresql, rabbitmq               |
| `matching`       | build: .                           | postgresql, rabbitmq               |
| `search`         | build: .                           | postgresql                         |
| `postgresql`     | postgres:16-alpine                 | —                                  |
| `redis`          | redis:7-alpine                     | —                                  |
| `minio`          | minio/minio                        | —                                  |
| `rabbitmq`       | rabbitmq:4.0-management-alpine     | —                                  |
| `ollama`         | ollama/ollama                      | —                                  |

> Ollama запускается как отдельный сервис. При первом запуске нужно скачать модель:
> `docker exec ara-ollama ollama pull qwen2.5:7b`

> **Примечание.** Конкретная модель настраивается через переменную окружения `LLM_MODEL`
> в конфигурации Profile-сервиса. Можно заменить без изменения кода.

---

## Минимальные требования к API-контракту

- **Версионирование URI:** `/api/v1/...`

- **Единый формат ошибок:**
  ```json
  {
    "status": "error",
    "error": {
      "code": "validation_error",
      "message": "Описание ошибки",
      "details": { "field": "email", "reason": "invalid format" },
      "request_id": "req-abc-123"
    }
  }
  ```

- **Пагинация списков:**
  - Параметры запроса: `limit` (default 20, max 100), `offset` (default 0)
  - В ответе: `"pagination": { "limit": 20, "offset": 0, "total": 142 }`

- **Формат успешного ответа:**
  ```json
  {
    "status": "ok",
    "data": { ... },
    "pagination": { ... }
  }
  ```
