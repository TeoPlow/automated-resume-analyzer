# automated-resume-analyzer
Репозиторий ВКР на тему:
**Система автоматизированной обработки потока резюме для вакансий в IT-компании**

Задание:
Создание системы автоматизированной обработки потока резюме для вакансий в IT-компании, а также API для взаимодействия с ним. Система должна позволять пользователям отправлять резюме из разных источников, извлекать из резюме ключевую информацию, классифицировать и ранжировать кандидатов по степени соответствия требованиям вакансий, предоставлять интерфейс для просмотра и фильтрации резюме специалистами по подбору персонала.

---

## Целевая микросервисная архитектура (MVP)

Выбранные сервисы:

1. **Gateway** — единая точка входа (внешний REST API, авторизация, маршрутизация)
2. **Profile** — приём/загрузка резюме + создание/обновление профиля кандидата
3. **Vacancy** — загрузка и управление вакансиями
4. **Matching** — анализ соответствия и ранжирование
5. **Search** — поиск/фильтрация для HR

Технологии:

- **FastAPI** для всех сервисов
- **PostgreSQL** для транзакционных данных
- **MinIO** для хранения файлов резюме
- **RabbitMQ** для асинхронных процессов

---

## Роли и доступ

### Внешние клиенты

- **HR-специалист** (веб-интерфейс/внутренний клиент)
- **Внешние источники** (email-адаптеры, боты, job-порталы)

### Авторизация

- Внешние запросы идут **только через Gateway**.
- Внешняя аутентификация: `JWT Bearer` (для HR) и/или `API Key` (для интеграций).
- Gateway прокидывает в downstream-сервисы технические заголовки:
	- `X-Request-Id`
	- `X-Actor-Id`
	- `X-Actor-Type` (`hr` | `integration` | `system`)
	- `X-Roles`

---

## Границы ответственности сервисов

### 1) Gateway

Назначение:

- Единый внешний API
- Проверка токена/ключа
- Базовый rate-limit
- Проксирование в внутренние сервисы

Не хранит бизнес-данные кандидатов/вакансий/матчинга.

### 2) Profile

Назначение:

- Приём файла резюме
- Валидация и загрузка файла в MinIO
- Извлечение структуры из резюме
- Создание/обновление профиля кандидата

Хранит:

- метаданные резюме
- профиль кандидата
- связи `candidate <-> resumes`

### 3) Vacancy

Назначение:

- CRUD вакансий
- Нормализация требований вакансии
- Публикация событий изменения вакансии (запускает событие перерасчёта рейта по вакансии среди кандидатов)

### 4) Matching

Назначение:

- Расчёт релевантности `candidate_profile` к `vacancy`
- Ранжирование кандидатов по вакансии
- Хранение результатов анализа и объяснений score

### 5) Search

Назначение:

- Сервис поисковых запросов к PostgreSQL
- Объединённая выдача: кандидат + вакансия + результаты matching через SQL-запросы

Примечание:

- Для ускорения поиска используются индексы PostgreSQL (`btree`, `gin`, `tsvector`) на полях фильтрации и полнотекста.

---

## Схема данных по хранилищам

- **MinIO**
	- bucket `resumes-raw` — оригиналы PDF/DOCX/TXT
- **PostgreSQL - Profile DB**
	- `candidates`, `resumes`, `candidate_profiles`
- **PostgreSQL - Vacancy DB**
	- `vacancies`, `vacancy_requirements`
- **PostgreSQL - Matching DB**
	- `match_results`, `match_explanations`, `match_runs`

> Для MVP можно использовать один PostgreSQL-кластер с разными схемами/БД на сервис.

---

## Внешние REST API (через Gateway)

Ниже — внешний контракт. Gateway маршрутизирует запросы во внутренние сервисы.

### Gateway API

- `GET /api/v1/health` — healthcheck gateway
- `GET /api/v1/me` — данные текущего пользователя
- `POST /api/v1/auth/login` — логин HR, выдача access_token + refresh_token
- `POST /api/v1/auth/refresh` — обновление access token
- `POST /api/v1/auth/logout` — инвалидировать refresh token

> Далее только ADMIN
- `POST /api/v1/integrations/keys` — создать API key для бота/интеграции 
- `GET /api/v1/integrations/keys` — список ключей
- `POST /api/v1/integrations/keys/{key_id}/rotate` — ротация (плановая замена ключа)
- `DELETE /api/v1/integrations/keys/{key_id}` — отозвать ключ

### Profile API

- `POST /api/v1/profiles/resumes/upload`
	- multipart: `file`, `source`, `external_id?`
	- результат: `resume_id`, `candidate_id`, статус парсинга
- `GET /api/v1/profiles/candidates/{candidate_id}`
- `PATCH /api/v1/profiles/candidates/{candidate_id}`
- `GET /api/v1/profiles/candidates/{candidate_id}/resumes`

### Vacancy API

- `POST /api/v1/vacancies`
- `GET /api/v1/vacancies/{vacancy_id}`
- `PATCH /api/v1/vacancies/{vacancy_id}`
- `GET /api/v1/vacancies`

### Matching API

- `POST /api/v1/matching/run`
	- body: `vacancy_id`, `candidate_ids?`, `top_k?`, `force_recompute?`
- `GET /api/v1/matching/results/{run_id}`
- `GET /api/v1/matching/vacancies/{vacancy_id}`
- `GET /api/v1/matching/candidates/{candidate_id}/vacancies`

### Search API

- `GET /api/v1/search/candidates`
	- фильтры: skills, grade, location, experience_years, salary, status
- `GET /api/v1/search/vacancies`
- `GET /api/v1/search/matches`
- `GET /api/v1/search/summary`

---

## Внутренние API между сервисами

Внутренние URL можно держать в формате:

- `http://profile:8000/internal/v1/...`
- `http://vacancy:8000/internal/v1/...`
- `http://matching:8000/internal/v1/...`
- `http://search:8000/internal/v1/...`

### Profile internal

- `GET /internal/v1/candidates/{candidate_id}`
- `POST /internal/v1/candidates/bulk-get` — данные сразу нескольких кандидатов одним запросом

### Vacancy internal

- `GET /internal/v1/vacancies/{vacancy_id}`
- `POST /internal/v1/vacancies/bulk-get`

### Matching internal

- `POST /internal/v1/run-for-vacancy/{vacancy_id}`
- `POST /internal/v1/run-for-candidate/{candidate_id}`
- `GET /internal/v1/results/by-vacancy/{vacancy_id}`

---

## События и асинхронное взаимодействие

Рекомендуемый минимальный event-contract:

1. `resume.uploaded`
	 - producer: Profile
	 - consumers: Profile (parser worker)
2. `candidate.profile.updated`
	 - producer: Profile
	 - consumers: Matching
3. `vacancy.created`
	 - producer: Vacancy
	 - consumers: Matching
4. `vacancy.updated`
	 - producer: Vacancy
	 - consumers: Matching
5. `matching.completed`
	 - producer: Matching
	 - consumers: (опционально) уведомления/аудит

### Базовая структура события

```json
{
	"event_id": "uuid",
	"event_type": "candidate.profile.updated",
	"event_version": 1,
	"occurred_at": "2026-03-05T10:00:00Z",
	"producer": "profile-service",
	"payload": {}
}
```

---

## Сквозные бизнес-потоки

### Поток A — Приём резюме и формирование профиля кандидата

1. Источник отправляет резюме в `POST /api/v1/profiles/resumes/upload`.
2. Gateway валидирует доступ и проксирует в Profile.
3. Profile валидирует файл, кладёт в MinIO, создаёт `resume`.
4. Profile запускает парсинг (sync или async через событие `resume.uploaded`).
5. Profile формирует/обновляет `candidate_profile`.
6. Profile публикует `candidate.profile.updated`.

### Поток B — Создание вакансии

1. HR создаёт вакансию: `POST /api/v1/vacancies`.
2. Vacancy сохраняет вакансию и требования.
3. Vacancy публикует `vacancy.created`.

### Поток C — Анализ и ранжирование

1. HR запускает матчинг: `POST /api/v1/matching/run`.
2. Matching получает данные вакансии и кандидатов через internal API.
3. Matching считает score + explanation и сохраняет `match_results`.
4. Matching публикует `matching.completed`.

### Поток D — Просмотр и фильтрация

1. HR вызывает `GET /api/v1/search/...`.
2. Search выполняет SQL-запросы к PostgreSQL (join по D2/D3/D4) и возвращает результат.

---

## Правила взаимодействия сервисов

1. Внешние клиенты не ходят напрямую во внутренние сервисы.
2. Все изменяющие операции (create/update/run) — через свои доменные сервисы.
3. Межсервисные синхронные вызовы — только для необходимых данных в runtime.
4. Тяжёлые и массовые обновления — через события.
5. Все сервисы поддерживают `X-Request-Id` для трассировки.
6. В MVP Search читает данные напрямую из PostgreSQL.

---

## Минимальные требования к API-контракту

- Версионирование URI: `/api/v1/...`
- Единый формат ошибок:
	- `code`
	- `message`
	- `details`
	- `request_id`
- Пагинация списков:
	- `limit`, `offset`, `total`
- Сортировка:
	- `sort_by`, `sort_order`
