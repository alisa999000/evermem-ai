# LongMemEval: как запустить бенчмарк

Инструкция для воспроизведения цифр из README. Запускай из корня проекта `evermem/`.

## Подготовка (один раз)

1. Установи [Ollama](https://ollama.com/download) и Python 3.10+.
2. Скачай модели:

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
```

Для GPU 16 GB модель 7B заметно точнее 3B.

3. Положи датасеты в `bench/data/`. Если их нет, скачай:

```bash
curl -L -o bench/data/longmemeval_oracle.json https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_oracle.json
curl -L -o bench/data/longmemeval_s.json https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
```

Файл `_s` около 265 MB. Oracle около 15 MB.

## Запуск

### Локально (Ollama + 7B) - как v3

```bash
# Проверка: тесты и 10 вопросов (2-5 минут)
python -m pytest tests -q
python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json --embed-model nomic-embed-text --qa-model qwen2.5:7b --limit 10
```

### DeepSeek API (сравнение с Zep+GPT-4o)

Память и embeddings остаются **локальными** (Ollama). В облако уходит только reader/judge - как у конкурентов с GPT-4o.

```bash
# Windows
set DEEPSEEK_API_KEY=sk-...

# Linux/macOS
export DEEPSEEK_API_KEY=sk-...

# Проверка ключа
python bench/test_deepseek.py

# Smoke: 10 вопросов
python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json --embed-model nomic-embed-text --qa-backend deepseek --qa-model deepseek-chat --limit 10

# Полный oracle (500 вопросов, ~$2-5 API, несколько часов)
python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json --embed-model nomic-embed-text --qa-backend deepseek --qa-model deepseek-chat --report bench/report_oracle_deepseek_v4.json

# Стог _s (100 вопросов при --every 5)
python bench/run_longmemeval.py --data bench/data/longmemeval_s.json --embed-model nomic-embed-text --qa-backend deepseek --qa-model deepseek-chat --every 5 --report bench/report_s_deepseek_v4.json
```

Модели DeepSeek: `deepseek-chat` (быстрый, для сравнения с GPT-4o), `deepseek-reasoner` (медленнее, для сложной арифметики).

### LLM extraction at ingest (Sprint 4)

По умолчанию ingest использует rule-extractor (быстро, offline). Для максимальной QA точности:

```bash
python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json \
  --embed-model nomic-embed-text --extract-llm qwen2.5:7b \
  --qa-backend deepseek --qa-model deepseek-chat --limit 10
```

### Локальный 7B - полный прогон

```bash
# Полный oracle, 500 вопросов (на GPU 1-2 часа)
python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json --embed-model nomic-embed-text --qa-model qwen2.5:7b --report bench/report_oracle_v3.json

# Стог _s: ~40 лишних сессий на вопрос (3-5 часов; --every 5 = выборка 100)
python bench/run_longmemeval.py --data bench/data/longmemeval_s.json --embed-model nomic-embed-text --qa-model qwen2.5:7b --every 5 --report bench/report_s_v3.json
```

Разбор ошибок после прогона:

```bash
python bench/analyze_errors.py --report bench/report_s_v3.json --data bench/data/longmemeval_s.json
```

Замер задержек observe/recall (без Ollama, чистый CPU):

```bash
python bench/latency.py --turns 2000
python bench/latency.py --turns 2000 --embed-model nomic-embed-text
```

## Что изменилось в v3

- Судья не засчитывает ошибкой ответ, где gold уже есть дословно.
- Промпт судьи: другая формулировка и лишние детали не считаются провалом.
- Пак шире: `history_limit` 12, до 3 реплик на сессию.
- В timeline добавлены готовые интервалы между датами.

## Как читать результаты

| Метрика | Что значит |
|---|---|
| evidence recall | Нашла ли память нужные сессии. Цель на _s: >90%. |
| QA accuracy | Точность ответа ридера по паку. У Zep 63.8% с GPT-4o в облаке; у нас локальная 7B. |
| answer presence | Есть ли gold-ответ в MemoryPack (без участия ридера). |

Слабые типы вопросов: `multi-session`, `temporal-reasoning`. Отчёт JSON хранит `qa_answer` по каждому вопросу.

## Заметки

- Ollama: используй `127.0.0.1`, не `localhost`. На Windows через IPv6 бывает +2 с на запрос.
- Один упавший вопрос не останавливает весь прогон.
- После скачивания датасетов и моделей интернет не нужен.
