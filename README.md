# TaskFlow Telegram Bot

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/aiogram-3.7.0-ffdd2d)](https://docs.aiogram.dev)
[![Redis](https://img.shields.io/badge/Redis-5+-red)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-ready-0db7ed)](https://www.docker.com/)

**TaskFlow Bot** — это телеграм-пульт для управления задачами через Task Manager API.  
Мы используем FSM Aiogram, инлайн-клавиатуры и презентационные хелперы, чтобы держать работу с задачами под рукой, без ввода команд.  

Проект является частью планируемой комплексной экосистемы для управления задачами, которая будет включать:  
- **REST API** — основной бэкенд для управления пользователями, задачами и категориями.  
- **Telegram-бот (этот репозиторий)** — пользовательский интерфейс для взаимодействия с задачами через мессенджер.  
- **MCP** - для взаимодействия LLM с сервисом. 
---

## 🔹 Основные возможности
- Главное меню и справка, которые позволяют управлять ботом без слеш-команд.  
- Просмотр задач с группировкой по статусу и приоритетам, фильтры, поиск и пагинация.  
- Создание и редактирование задач через инлайн-клавиатуру: приоритет, дедлайн, категория.  
- Управление категориями (создание, переименования, быстрый переход к связанным задачам).  
- Поддержка архивирования, восстановления и индикации активных фильтров.  

---

## 🔧 Технологии
- Python 3.11 + aiogram 3.7.0  
- Redis (FSM storage)  
- httpx для общения с Task Manager API  
- Pydantic settings и типизированные сервисы  
- Docker & Docker Compose для развёртывания  

---

## 🚀 Быстрый старт (локально)
1. Установите Python 3.11+, Redis 5+ и клонируйте репозиторий.  
2. Создайте виртуальное окружение и установите зависимости:  
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Скопируйте `.env.example` в `.env` и заполните переменные окружения (см. ниже).  
4. Запустите бота:  
   ```bash
   python main.py
   ```

### Переменные окружения
- `BOT_TOKEN` — токен Telegram-бота от @BotFather (обязателен).  
- `API_BASE_URL` — базовый URL Task Manager API, по умолчанию `http://localhost:8000`.  
- `REDIS_URL` — строка подключения к Redis, по умолчанию `redis://localhost:6379/0`.  
- `LOG_LEVEL` — уровень логирования (`INFO`, `DEBUG` и т.д.).  

---

## 🐳 Docker-развёртывание
1. Создайте общую сеть (нужно один раз):
   ```bash
   docker network create task_manager_network
   ```
2. Соберите и запустите контейнер:  
   ```bash
   docker compose up --build bot
   ```
3. Остановить:  
   ```bash
   docker compose down
   ```

Бот будет доступен в Telegram, используя токен из `.env`.


