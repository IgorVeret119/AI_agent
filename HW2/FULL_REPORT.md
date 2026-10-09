# Полный отчёт: MCP-сервер расписания, выбор инструментов и агентные петли

Дата: 9 октября 2026 года. Домен: учебное расписание. Проект: `D:/lesson-02-mcp-demo/mcp-demo`.

## 1. Результат и границы отчёта

Реализованы четыре инструмента `schedule_*` на Python SDK MCP с протоколом 2026-07-28, явным handle снимка, двумя форматами ответа, закрытыми схемами и исправимыми ошибками. Сохранены реальные проверки pytest и MCP Inspector. Эксперименты выполнены локальной Qwen/Qwen3-0.6B: 720 решений о выборе инструмента и 180 агентных эпизодов. Числа взяты из сохранённых результатов, а не из моделируемых или ожидаемых исходов.

При N=100 вариант с полным каталогом дал точность 43,3%, с поиском top-5 — 0%: поиск не включил правильный инструмент ни для одного из 30 запросов. В части B все три условия дали 48,3% успеха и 0 наблюдавшихся петель. Модель завершала эпизод после одного вызова; этот эксперимент не позволяет установить преимущество guard над исправлением ответа инструмента.

Материалы лекции с реализацией LoopGuard не предоставлены. Использован явно описанный guard с окном 6 и двумя критериями из задания. Совпадение с точным кодом лекции не подтверждено. Исходный материал ДЗ 1 также не приложен; домен сохранён по имеющемуся проекту расписания. Данные расписания синтетические, а не действующее расписание учреждения.

## 2. Соответствие требованиям


| Требование | Реализация / результат | Доказательство |
| --- | --- | --- |
| MCP 2026-07-28; stateless; server/discover; _meta | MCPServer, stdio, discovery без initialize; метаданные каждого запроса | server.py, client.py, artifacts/wire-log.json |
| Не меньше четырёх инструментов одного пространства имён | schedule_search, schedule_get, schedule_day, schedule_room | tools/list; приложение со схемами |
| enum, description, additionalProperties: false | Закрытые входные и выходные объекты; enum для закрытых множеств | Схемы tools/list и pytest |
| response_format и три примера размеров | concise / detailed; шесть измерений текста и полного результата | README.md, artifacts/token-counts.json |
| Ошибки как isError: true с подсказкой | code, message, hint; без стектрейса | Ошибки четырёх инструментов в Inspector |
| Состояние явным handle, без сессий | schedule_handle=schedule-v1; в нестабильном инструменте также fault_handle | Перезапуск процесса проверен тестом |
| pytest успех и ошибка каждого инструмента; Inspector | 28 основных + 12 экспериментальных тестов; 9 запусков Inspector | pytest-all.xml и inspector-log.json |
| A: пул 100, ≥20 близких отвлекающих | 4 целевых + 96 синтетических; 28 близких | Приложение A; tools.json |
| A: 30 размеченных запросов, N=5/20/50/100, 3 повтора, A/B | 30 × 4 × 3 × 2 = 720 решений | Приложение B; selection.jsonl |
| A: точность, Recall@5, входные токены, 95% bootstrap по запросам | Все метрики; 10 000 выборок кластеров по 30 запросов | Таблицы раздела экспериментов; summary.json |
| B: 50% пустых ответов, 20 задач × 3, без/с guard, окно 6 | 60 эпизодов на условие, парная маска отказов; guard по критериям задания | loops.jsonl; точный guard лекции не подтверждён |
| B: петли, шаги, токены, успех; подсказка и сравнение | Три условия, 180 эпизодов; победитель не установлен из-за отсутствия петель | Раздел B и ограничения |


## 3. Реализация MCP и проверка сервера

Импорт сервера: `from mcp.server import MCPServer`; версия пакета `mcp==2.2.0`. Сервер читает неизменяемый снимок из четырёх записей. Инструменты имеют аннотации чтения и идемпотентности. Транспорт stdio не делает соединение источником доменного состояния.

| entry_id | course | day | start–end | room | teacher |
| --- | --- | --- | --- | --- | --- |
| agents-mon | agents | monday | 10:00–11:30 | 314 | Anna Petrova |
| python-tue | python | tuesday | 12:00–13:30 | 210 | Ivan Smirnov |
| databases-wed | databases | wednesday | 14:00–15:30 | 115 | Maria Volkova |
| agents-wed | agents | wednesday | 10:00–11:30 | 314 | Anna Petrova |

Ниже приведена документация реализации, включая измерения размеров ответов и подтверждение Inspector. Она включена в отчёт целиком, чтобы эти пункты не требовали чтения отдельного README.


### MCP: синтетическое расписание курсов

Домен сохранён из исходного примера ДЗ 1: расписание курсов. Все занятия, преподаватели и аудитории вымышлены. SDK `mcp==2.2.0`, импорт `from mcp.server import MCPServer`, протокол **2026-07-28**, транспорт stdio.

#### Запуск

Обычный Python 3.13 на Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe client.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe measure_tokens.py
```

`requirements.txt` задаёт основные зависимости; `requirements-lock.txt` фиксирует все версии проверенного окружения Windows/Python 3.13. При первом измерении tiktoken скачивает словарь `cl100k_base`. Сам сервер работает только с локальной неизменяемой фикстурой.

#### Контракт инструментов

| Инструмент | Назначение | Обязательные аргументы |
| --- | --- | --- |
| `schedule_search` | Фильтр по курсу и дню; `all` — без фильтра | `schedule_handle` |
| `schedule_get` | Занятие по идентификатору из поиска | `schedule_handle`, `entry_id` |
| `schedule_day` | Все занятия указанного дня | `schedule_handle`, `day` |
| `schedule_room` | Все занятия в аудитории | `schedule_handle`, `room` |

Каждый инструмент принимает `response_format`: enum `concise` / `detailed`, по умолчанию `concise`. Входные и выходные объекты закрыты: `additionalProperties: false`, у всех полей есть `description`. Курсы, дни, аудитории и форматы объявлены через `enum`; строка аудитории `"314"` и число `314` различаются. `entry_id` — открытый идентификатор, его нужно получать из поиска. Источник истины для аргументов — `tools/list`.

`concise` возвращает `id`, `day`, `start`, `room`. `detailed` добавляет `course`, `end`, `teacher`, источник, часовой пояс и пояснение. Оба режима сохраняют `schedule_handle` и `synthetic: true`. Отсутствие совпадений при поиске — успешный ответ с пустым `entries`.

#### Stateless и discovery

Нет `initialize`, `notifications/initialized` и состояния сессий. `server/discover` реализует SDK; клиент вызывает его для проверки `supportedVersions`, затем `tools/list` и `tools/call`. Вызов инструмента до discovery тоже разрешён и проверен тестом.

Каждый запрос клиента содержит в `params._meta`:

```json
{
  "io.modelcontextprotocol/protocolVersion": "2026-07-28",
  "io.modelcontextprotocol/clientInfo": {"name": "schedule-demo", "version": "1.0.0"},
  "io.modelcontextprotocol/clientCapabilities": {}
}
```

`schedule_handle` обязателен и равен `schedule-v1`: это handle неизменяемого снимка данных, а не идентификатор соединения. Нет скрытого «текущего расписания» и мутаций. Тот же handle работает после перезапуска процесса. Неизвестный или пропущенный handle возвращает ошибку, сервер не выбирает снимок за клиента. Пример полного обмена: [artifacts/wire-log.json](artifacts/wire-log.json).

#### Ошибки

Ошибки инструментов возвращаются как результат `tools/call` с `isError: true`. Текстовый блок содержит JSON с `code`, `message`, `hint`. Например, `schedule_get` с несуществующим `entry_id` возвращает `entry_not_found` и совет выполнить `schedule_search` с тем же handle. Неверные типы, enum, лишние и отсутствующие поля получают `invalid_arguments` и подсказку свериться с `tools/list`. Неожиданные внутренние ошибки заменяются безопасным сообщением без стектрейса. Протокольные ошибки, например некорректный JSON-RPC, остаются ошибками протокола SDK.

#### Размер ответа в токенах

Измерено `tiktoken==0.11.0`, encoding `cl100k_base`. В каждой ячейке: **текст `content[0].text` / полный JSON результата `tools/call`**. Полный результат сериализован с `ensure_ascii=False`, `separators=(",", ":")`; включает текст, `structuredContent` и поля SDK, но не JSON-RPC оболочку `id/jsonrpc/result`. Это воспроизводимый подсчёт выбранным токенизатором, а не универсальная стоимость для любой модели. Текст и structuredContent содержат одинаковые данные, поэтому полный результат крупнее.

Общий аргумент всех примеров: `schedule_handle="schedule-v1"`.

| Пример | concise: текст / результат | detailed: текст / результат |
| --- | ---: | ---: |
| `schedule_search(course="agents")` | 57 / 167 | 118 / 288 |
| `schedule_get(entry_id="agents-mon")` | 36 / 123 | 81 / 212 |
| `schedule_day(day="wednesday")` | 59 / 171 | 121 / 294 |

Исходные ответы и измерения: [artifacts/token-counts.json](artifacts/token-counts.json). Повторный подсчёт: `python measure_tokens.py`.

#### Проверки и MCP Inspector

`test_server.py` запускает реальный сервер отдельным процессом и проверяет через MCP: успех каждого инструмента в обоих форматах, ошибки каждого инструмента, неверные типы и enum, лишние поля, отсутствие handle, неизвестный инструмент, ненайденную запись, пустой поиск, входные/выходные схемы, discovery, `_meta`, вызов до discovery и handle после перезапуска.

Для Inspector нужен Node.js >=22.19. Проверяемая версия Inspector: `2.10.1`.

```powershell
npm install --prefix .inspector @modelcontextprotocol/inspector@2.10.1
.\.venv\Scripts\python.exe run_inspector.py --cli .inspector/node_modules/@modelcontextprotocol/inspector/clients/launcher/build/index.js
```

Скрипт запускает официальный Inspector CLI в режиме `--protocol-era modern`: каталог со строгой проверкой схем и успешный/ошибочный вызов всех четырёх инструментов. Для ошибки инструмента ожидается код завершения Inspector `5`, для успеха — `0`. Сохраняются полные команды, stdout, stderr и коды завершения в [artifacts/inspector-log.json](artifacts/inspector-log.json). JSON-RPC обмен нашего клиента хранится отдельно и не выдаётся за лог Inspector.

Проверено 9 октября 2026 года: **28 pytest-тестов прошли**, отчёт [artifacts/pytest-results.xml](artifacts/pytest-results.xml); **все 9 запусков Inspector прошли** (каталог + 4 успеха + 4 ожидаемые ошибки), стектрейсов в логе нет. Окружение: Windows, Python 3.13.7, MCP SDK 2.2.0, Node.js 22.20.0, Inspector 2.10.1. Inspector получает аргументы через `--tool-args-json`, чтобы номер аудитории оставался строкой.

#### Официальные источники

Эксперименты выбора из 100 инструментов и агентных петель находятся в [experiments/README.md](experiments/README.md). Итоговые измерения с Qwen3-0.6B, Recall@5, токенами и бутстрэп-интервалами: [experiments/results/REPORT.md](experiments/results/REPORT.md).

- [Спецификация MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [Изменения stateless, discovery и `_meta`](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [Python SDK v2](https://github.com/modelcontextprotocol/python-sdk)
- [Inspector CLI: команды, modern mode и коды завершения](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md)


### 3.1. Фактические протокольные сообщения

Первый запрос и ответ discovery из журнала реального клиента:


```json
[
  {
    "request": {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "server/discover",
      "params": {
        "_meta": {
          "io.modelcontextprotocol/protocolVersion": "2026-07-28",
          "io.modelcontextprotocol/clientInfo": {
            "name": "schedule-demo",
            "version": "1.0.0"
          },
          "io.modelcontextprotocol/clientCapabilities": {}
        }
      }
    }
  },
  {
    "response": {
      "jsonrpc": "2.0",
      "id": 1,
      "result": {
        "cacheScope": "private",
        "capabilities": {
          "prompts": {
            "listChanged": true
          },
          "resources": {
            "listChanged": true,
            "subscribe": true
          },
          "tools": {
            "listChanged": true
          }
        },
        "resultType": "complete",
        "supportedVersions": [
          "2026-07-28"
        ],
        "ttlMs": 0,
        "_meta": {
          "io.modelcontextprotocol/serverInfo": {
            "name": "Course schedule",
            "version": "1.0.0"
          }
        }
      }
    }
  }
]
```


Успешный вызов (запрос и ответ):


```json
[
  {
    "request": {
      "jsonrpc": "2.0",
      "id": 3,
      "method": "tools/call",
      "params": {
        "name": "schedule_search",
        "arguments": {
          "schedule_handle": "schedule-v1",
          "course": "agents"
        },
        "_meta": {
          "io.modelcontextprotocol/protocolVersion": "2026-07-28",
          "io.modelcontextprotocol/clientInfo": {
            "name": "schedule-demo",
            "version": "1.0.0"
          },
          "io.modelcontextprotocol/clientCapabilities": {}
        }
      }
    }
  },
  {
    "response": {
      "jsonrpc": "2.0",
      "id": 3,
      "result": {
        "content": [
          {
            "text": "{\"schedule_handle\":\"schedule-v1\",\"synthetic\":true,\"entries\":[{\"id\":\"agents-mon\",\"day\":\"monday\",\"start\":\"10:00\",\"room\":\"314\"},{\"id\":\"agents-wed\",\"day\":\"wednesday\",\"start\":\"10:00\",\"room\":\"314\"}]}",
            "type": "text"
          }
        ],
        "isError": false,
        "resultType": "complete",
        "structuredContent": {
          "schedule_handle": "schedule-v1",
          "synthetic": true,
          "entries": [
            {
              "id": "agents-mon",
              "day": "monday",
              "start": "10:00",
              "room": "314"
            },
            {
              "id": "agents-wed",
              "day": "wednesday",
              "start": "10:00",
              "room": "314"
            }
          ]
        },
        "_meta": {
          "io.modelcontextprotocol/serverInfo": {
            "name": "Course schedule",
            "version": "1.0.0"
          }
        }
      }
    }
  }
]
```


Ошибка инструмента (запрос и ответ):


```json
[
  {
    "request": {
      "jsonrpc": "2.0",
      "id": 4,
      "method": "tools/call",
      "params": {
        "name": "schedule_search",
        "arguments": {
          "schedule_handle": "invalid",
          "course": "agents"
        },
        "_meta": {
          "io.modelcontextprotocol/protocolVersion": "2026-07-28",
          "io.modelcontextprotocol/clientInfo": {
            "name": "schedule-demo",
            "version": "1.0.0"
          },
          "io.modelcontextprotocol/clientCapabilities": {}
        }
      }
    }
  },
  {
    "response": {
      "jsonrpc": "2.0",
      "id": 4,
      "result": {
        "content": [
          {
            "text": "{\"code\":\"invalid_arguments\",\"message\":\"Invalid fields: schedule_handle\",\"hint\":\"Use tools/list: supply required fields, enum values and correct types; remove extra fields.\"}",
            "type": "text"
          }
        ],
        "isError": true,
        "resultType": "complete",
        "_meta": {
          "io.modelcontextprotocol/serverInfo": {
            "name": "Course schedule",
            "version": "1.0.0"
          }
        }
      }
    }
  }
]
```


### 3.2. Сводка реального MCP Inspector

Журнал содержит команды, stdout, stderr и exit code. Код 5 здесь означает ожидаемый результат инструмента с `isError: true`; это проверка ошибки, а не падение сервера. Скриншот не требовался, поскольку задание допускает лог.


| Случай | Код завершения | Стектрейс |
| --- | --- | --- |
| catalog | 0 | нет |
| schedule_search success | 0 | нет |
| schedule_search error | 5 | нет |
| schedule_get success | 0 | нет |
| schedule_get error | 5 | нет |
| schedule_day success | 0 | нет |
| schedule_day error | 5 | нет |
| schedule_room success | 0 | нет |
| schedule_room error | 5 | нет |


## 4. Экспериментальная установка и методика

Выбрана указанная пользователем Qwen/Qwen3-0.6B; для поиска — Qwen/Qwen3-Embedding-0.6B того же размера. Обе модели — официальные GGUF Q8_0, запускаются локально через llama.cpp b11429 на CPU, 8 потоков, один слот. ОС Windows; Python 3.13.7; 16 логических процессоров и около 16,89 ГБ RAM. Контекст генерации 8192, эмбеддингов 2048; адреса сервисов 127.0.0.1:18080 и :18081. Веса, ревизии и контрольные суммы приведены ниже.

### 4.1. Часть A: построение выборки и сравнение

Пул состоит из четырёх реально исполняемых инструментов и 96 отвлекающих описаний. 28 близких описаний относятся к экзаменам, консультациям, архиву расписания, аудиториям, календарю и операциям расписания. 68 дальних получены из 17 других доменов по четыре действия. Отвлекающие инструменты не исполнялись. Полный каталог и разметка приведены в приложениях.

Пулы вложенные: первые N записей tools.json, N ∈ {5,20,50,100}; четыре целевых инструмента присутствуют в каждом пуле. Близкие и дальние описания перемешаны с seed 20261009 и чередуются. Состав пула фиксирован; порядок показанных кандидатов перемешивается по повтору одинаково для двух условий. Gold выбирается заранее: известный entry_id → get; только аудитория → room; только день для всех курсов → day; фильтр курса, курс вместе с днём или общий поиск → search. Запросов соответственно 8, 8, 7, 7. Общую рубрику получает модель в обоих условиях; правильный ответ конкретного запроса ей не передаётся.

В варианте A модель видит имена и все N описаний. В B эмбеддинг пользовательского текста сравнивается с эмбеддингами **только описаний** внутри текущего пула; выбираются пять максимальных cosine similarity. Вектор имеет размерность 1024, применяется last pooling и нормализация. Затем модель видит имена и описания найденных кандидатов. Ранжирование не использует gold, имена инструментов или исполняемые отвлекающие функции. Для N=5 запросы A/B идентичны, что дополнительно проверено аудитом.

Модель отвечает JSON вида `{"tool":"schedule_search"}`. Структура ограничена JSON Schema, но значение tool не ограничено enum кандидатов; отсутствующее в каталоге имя считается ошибкой. Это измерение выбора по описаниям, а не испытание встроенного function calling конкретного поставщика. По три запуска каждого запроса и каждого условия: 30 × 3 × 4 × 2 = 720 вызовов модели.

### 4.2. Метрики и интервалы

Точность = сумма индикаторов совпадения выбранного имени с gold / 90 для каждой пары N/условие. Recall@5 = число запросов, для которых gold входит в найденные пять / 30. Поиск детерминирован и повторно не увеличивает знаменатель Recall. Средний вход LLM = среднее `usage.prompt_tokens` по 90 вызовам, включая системный текст, каталог и шаблон чата. Вход query embedding указан отдельно; складывание токенов двух разных моделей служит учётом объёма запросов, а не оценкой единой денежной стоимости.

Для 95%-го percentile bootstrap генерируется 10 000 выборок по 30 **запросов** с возвращением. У каждого выбранного запроса сохраняются все три повтора. В каждой выборке пересчитывается точность; границы — 2,5-й и 97,5-й процентили. Для B−A одни и те же индексы запросов используются в обоих условиях, разность выражается в процентных пунктах. Повторы не считаются независимыми запросами. Аналогичные дополнительные интервалы для части B ресэмплируют 20 задач, сохраняя три повтора. Seed bootstrap 20261009.

### 4.3. Часть B: нестабильность, guard и критерий успеха

Экспериментальный `schedule_search` дополнительно принимает date. Недельный снимок разворачивается на календарные даты; основной сервер с аргументом day остаётся прежним. Задача — найти хотя бы одно занятие нужного курса внутри включительного интервала start_date…end_date; начать с заданной даты, разрешены другие даты в интервале. Полные 20 формулировок приведены в приложении C.

Каждый валидный вызов с вероятностью 0,5 вместо записей возвращает `[]` без объяснения. Отказ вычисляется детерминированно по seed и номеру вызова; harness явно передаёт `fault_handle` вида seed:ordinal. Сервер не хранит RNG-сессию. Для одной задачи и повтора во всех трёх условиях совпадает последовательность потенциальных отказов. Вероятность 50% не требует ровно половины отказов в конечной выборке: фактически получилось 31/60 (51,7%) в каждом условии.

Условия: baseline — пустой ответ без guard; guard — тот же инструмент с окном 6 и остановкой до исполнения вызова, который создаст третий идентичный подряд или A-B-A-B; hint — без guard, вместо пустоты `{"entries":[],"message":"Ничего не найдено; попробуйте другое значение date в разрешённом интервале."}`. В каждом условии 20 × 3 = 60 эпизодов, всего 180.

Вызовы сравниваются по имени инструмента и каноническому JSON доменных аргументов. A и B в чередовании должны различаться. Управляющие fault_handle и response_mode не входят в сигнатуру, иначе новый ordinal искусственно скрывал бы повтор. Guard проверяет последние шесть вызовов вместе с предлагаемым вызовом. Исполненная петля и заблокированная попытка учитываются отдельно. Предельная длина — 12 шагов; достижение лимита само по себе не объявляется петлёй.

Один шаг — один ответ модели, включая финальный ответ и заблокированное предложение вызова. Токены эпизода — сумма входных и выходных usage всех шагов; повторно переданная история входит в расход. Успех требует, чтобы финальные entry_id и date соответствовали записи, реально полученной из инструмента, нужному курсу и допустимому интервалу. Выдуманная запись и остановка guard не считаются успехом.

### 4.4. Зафиксированные настройки


```json
{
  "seed": 20261009,
  "chat_model": "Qwen/Qwen3-0.6B",
  "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
  "quantization": "Q8_0",
  "temperature": 0.7,
  "top_p": 0.8,
  "top_k": 20,
  "min_p": 0,
  "enable_thinking": false,
  "selection_max_tokens": 48,
  "agent_max_tokens": 160,
  "episode_max_steps": 12,
  "guard_window": 6,
  "guard_policy": "stop before third identical or fourth ABAB; lecture implementation unprovided",
  "bootstrap_draws": 10000,
  "bootstrap_unit": "query/task clusters, preserving all three repeats",
  "dataset_hashes": {
    "tools.json": "1de96e7169e2bfbb599057ba40f734d68e35f6933915342eb390ddf5b5281d39",
    "queries.json": "c1347e071243a61945e3f6b0449d1a9bee710ad6d24bd596e02c41f3d4026204",
    "loop_tasks.json": "87c056a4999aada5d36370e6019cd060473a21ec9314fdccfa57e84283565b85"
  },
  "source_hashes": {
    "analyze.py": "06fe50373b705a843e124869ef63976b4daf2971c1f97c5e1a69670d337a771f",
    "audit_results.py": "887be578fefd8caa91bc29184b95a8deb82a55545180e02ea5c9ce6c85243fef",
    "build_data.py": "f575467534b35b2d889029867f45be3de26c94d8f6b72388fda302e125167bc3",
    "core.py": "9d41f11eb7af72c36560a51b41d4264f6cdc9bd40917fa29b15591bec7f9a2ef",
    "download_models.py": "637f1db319016f949abcf3e6cb93456ca07bb1452cd9a0e392a64bbcfb486885",
    "local_api.py": "ad8091eff0e200005a593d3edec1baa79f614de236d2313c958de8a110a4d0f1",
    "run_all.py": "5d5aea85e518c026ee27f20c1959e1edc6baa5932e4325e1a82bc52a2db40048",
    "run_loops.py": "50b5998cb76108516d957bc084bd08860bfa54295244ab97bb6dcfb0f2e0f433",
    "run_selection.py": "3ec4c2c1bd5fc47fceb34332d00b7ee1b77103f533d4d901e47b21d8fdcd8f8b",
    "test_experiments.py": "757fb502b46190fcb85d2e1076a08b3e9cfdafc1900c71130f005fbefa4bf3fa",
    "unstable_server.py": "fb601ebe038c49241d98afead54392ae0dee6b0093c2cb8650f232db765620ce"
  }
}
```


### 4.5. Происхождение моделей и контрольные суммы


```json
{
  "models": [
    {
      "role": "chat",
      "repo": "Qwen/Qwen3-0.6B-GGUF",
      "revision": "23749fefcc72300e3a2ad315e1317431b06b590a",
      "file": "Qwen3-0.6B-Q8_0.gguf",
      "path": "D:\\lesson-02-mcp-demo\\.runtime\\qwen-experiments\\Qwen3-0.6B-Q8_0.gguf",
      "url": "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/23749fefcc72300e3a2ad315e1317431b06b590a/Qwen3-0.6B-Q8_0.gguf",
      "sha256": "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031",
      "quantization": "Q8_0"
    },
    {
      "role": "embedding",
      "repo": "Qwen/Qwen3-Embedding-0.6B-GGUF",
      "revision": "370f27d7550e0def9b39c1f16d3fbaa13aa67728",
      "file": "Qwen3-Embedding-0.6B-Q8_0.gguf",
      "path": "D:\\lesson-02-mcp-demo\\.runtime\\qwen-experiments\\Qwen3-Embedding-0.6B-Q8_0.gguf",
      "url": "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/370f27d7550e0def9b39c1f16d3fbaa13aa67728/Qwen3-Embedding-0.6B-Q8_0.gguf",
      "sha256": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
      "quantization": "Q8_0"
    }
  ],
  "engine": {
    "tag": "b11429",
    "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-win-cpu-x64.zip",
    "sha256": "1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe"
  }
}
```


## 5. Измеренные результаты, сравнение и ограничения

Ниже включён полный отчёт сохранённого анализа экспериментов. Проценты округлены до одного десятичного знака; исходная точность чисел сохранена в summary.json.


### Эксперимент выбора инструментов и агентных петель

Все результаты получены локальной Qwen/Qwen3-0.6B в официальной Q8_0-квантизации; поиск использует Qwen/Qwen3-Embedding-0.6B Q8_0, last pooling и cosine similarity. Non-thinking mode; temperature=0.7, top_p=0.8, top_k=20, min_p=0. Отвлекающие инструменты не исполняются.

#### A. Выбор

В каждой строке 30 запросов × 3 повтора. 95%-интервалы: 10 000 бутстрэп-выборок целых запросов, сохраняющих все повторы. Recall@5 вычислен по 30 запросам отдельно от выбора модели. A — все N описаний; B — top-5, найденные только по эмбеддингам описаний.

| N | Вариант | Точность | 95% CI | Recall@5 | Вход LLM, токены | Вход с query embedding |
| ---: | --- | ---: | --- | ---: | ---: | ---: |
| 5 | A | 50.0% | 33.3% – 66.7% | — | 201.3 | 201.3 |
| 5 | B | 50.0% | 33.3% – 66.7% | 100.0% | 201.3 | 238.2 |
| 20 | A | 47.8% | 31.1% – 64.4% | — | 395.3 | 395.3 |
| 20 | B | 47.8% | 30.0% – 65.6% | 50.0% | 211.9 | 248.9 |
| 50 | A | 43.3% | 27.8% – 58.9% | — | 779.3 | 779.3 |
| 50 | B | 6.7% | 0.0% – 16.7% | 6.7% | 215.7 | 252.7 |
| 100 | A | 43.3% | 31.1% – 55.6% | — | 1396.3 | 1396.3 |
| 100 | B | 0.0% | 0.0% – 0.0% | 0.0% | 212.8 | 249.8 |

Однократное построение индекса: 1030 входных токенов embedding-модели; это не повторяется для каждого запроса. Query embedding учитывается как логический онлайн-расход для B; при фактическом прогоне он кэшируется один раз для каждого запроса и переиспользуется во всех N и повторах. В таблице LLM учитываются все входные токены, включая KV-кэшированные: usage.prompt_tokens, а не время вычисления.

| N | Парная разница точности B − A | 95% CI |
| ---: | ---: | --- |
| 5 | 0.0% | 0.0% – 0.0% |
| 20 | 0.0% | -16.7% – 15.6% |
| 50 | -36.7% | -51.1% – -22.2% |
| 100 | -43.3% | -55.6% – -31.1% |

При N=100 сокращение контекста не сохранило точность: правильный инструмент отсутствовал во всех найденных top-5. Это сбой этапа retrieval на данном фиксированном наборе, а не доказательство, что поиск по эмбеддингам вообще бесполезен. Проверка embedding-sanity.json подтвердила размерность 1024, уникальность векторов, cosine≈1 для повторно закодированного описания и меньшую близость нерелевантного описания. Бутстрэп-интервал 0–0 при всех нулевых ответах отражает конечную выборку и не доказывает нулевую точность на любых новых запросах.

#### B. Петли

20 задач × 3 повтора на вариант. baseline — пустой ответ без пояснения; guard — такой же инструмент плюс остановка до третьего одинакового вызова или четвёртого вызова A-B-A-B, окно 6; hint — пояснение вместо пустого ответа, без guard. Алгоритм лекции не предоставлен: использован описанный здесь guard по двум критериям задания, а не подтверждённая копия кода лекции.

Случайный отказ имеет вероятность 50% на каждый вызов. Для одной задачи и повтора одинаковые seed/номер вызова дают одинаковую маску отказов во всех вариантах; сравнение парное. Данные не становятся другими при включении подсказки. Неустойчивый schedule_search реально вызывается через MCP 2026-07-28; fault_handle передаётся явно, сервер не хранит сессию.

| Вариант | Петли (исполненные) | Попытка/петля | Средние шаги | Входные токены | Выходные токены | Всего токенов | Успех |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.0% | 0.0% | 2.00 | 510.0 | 67.2 | 577.3 | 48.3% |
| guard | 0.0% | 0.0% | 2.00 | 510.1 | 67.7 | 577.8 | 48.3% |
| hint | 0.0% | 0.0% | 2.00 | 525.5 | 64.2 | 589.8 | 48.3% |

Один шаг — один вызов модели, включая финальный ответ или предложение вызова, заблокированное guard. Токены эпизода — сумма usage всех таких шагов, включая повторно переданную историю. Успех требует финальной ссылки на действительно полученную запись нужного курса внутри разрешённого интервала; выдуманный ответ и остановка guard не считаются успехом. Петля проверяется по каноническому JSON имени инструмента и доменных аргументов. fault_handle и response_mode являются управляющими полями harness и не участвуют в сигнатуре. Ограничение каждого эпизода — 12 шагов; завершение по лимиту не объявляется петлёй автоматически.

#### Что помогает сильнее

С guard доля исполненных петель — 0.0%, без guard — 0.0%; успех соответственно 48.3% и 48.3%. Подсказка без guard дала 0.0% петель и 48.3% успеха.
По доле выполненных задач варианты совпали; решающего преимущества по этой метрике нет. Сравните токены, исполненные петли и попытки петель.
Парная разница успеха hint − guard: 0.0%, 95% CI 0.0% – 0.0%. Это исследовательская оценка на 20 задачах; она не устанавливает универсального преимущества на других моделях и доменах.
Интервал включает ноль: убедительного преимущества одного варианта по успеху на этом наборе не установлено; направление точечной оценки не равно статистически подтверждённому выигрышу.
В baseline заданные паттерны петель не встретились. Этот прогон не позволяет эмпирически оценить устранение петель guard: нет наблюдавшихся петель для устранения. Неуспешный эпизод может закончиться выдуманным финальным ответом вместо повторных вызовов. Нулевой бутстрэп-интервал при нуле наблюдений — особенность percentile bootstrap, а не доказательство нулевого риска на новых задачах.
Во всех 180 эпизодах модель сделала один вызов инструмента и сразу финальный ответ. После инъецированного пустого результата она не повторяла поиск и не следовала подсказке сменить date. Guard ни разу не сработал; успех в каждом варианте равен 29/60, то есть ровно числу вызовов без отказа. Для оценки защиты именно от петель нужен следующий, отдельно объявленный эксперимент с агентом/задачами, в которых наблюдаются повторные попытки. Эти данные не были заменены подобранными успешными прогонами.

| Вариант | Инъецированные отказы / исполненные вызовы | Фактическая доля отказов |
| --- | ---: | ---: |
| baseline | 31 / 60 | 51.7% |
| guard | 31 / 60 | 51.7% |
| hint | 31 / 60 | 51.7% |

#### Ограничения и воспроизводимость

Пулы вложенные и фиксированные; все правильные инструменты доступны при любом N. Порядок описаний перемешан по повтору, одинаковое относительное упорядочение используется для A и B. Золотые ответы не передаются модели; общее правило выбора передаётся обоим вариантам. Вывод ограничен JSON-схемой, но имя инструмента не ограничено enum кандидатов: неверное имя считается ошибкой. Это тест выбора по описаниям с JSON-ответом, а не сравнение vendor-specific native function calling. Дистракторы синтетические и размечены; 28 из 96 близки по смыслу. Три повтора не являются 90 независимыми запросами для CI. Сэмплирование с фиксированными seed и KV-кэш может иметь небольшие численные различия между повторными запусками.

Сырые данные: selection.jsonl, retrieval.json, loops.jsonl, loop-mcp-wire.json. Сводные численные значения и парные интервалы: summary.json. Полные запросы модели, ответы, usage и причины завершения сохранены. Параметры моделей, SHA256 весов и движка — model-manifest.json; протокол эксперимента — ../README.md.

Источники: [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B), [официальный GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF), [Qwen3-Embedding GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF), [llama.cpp API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).


### 5.1. Дополнительная детализация ошибок и интервалов


| N | Вариант | Правильных / 90 | Неверных / отсутствующих имён |
| --- | --- | --- | --- |
| 5 | A | 45 / 90 | 0 |
| 5 | B | 45 / 90 | 0 |
| 20 | A | 43 / 90 | 0 |
| 20 | B | 43 / 90 | 0 |
| 50 | A | 39 / 90 | 0 |
| 50 | B | 6 / 90 | 7 |
| 100 | A | 39 / 90 | 0 |
| 100 | B | 0 / 90 | 3 |



| Условие | Успех / 60 | 95% CI успеха | Неподтверждённый финал | Средние вызовы инструмента |
| --- | --- | --- | --- | --- |
| baseline | 29 / 60 | 35.0%–61.7% | 31 | 1 |
| guard | 29 / 60 | 35.0%–61.7% | 31 | 1 |
| hint | 29 / 60 | 35.0%–61.7% | 31 | 1 |


При N=100 вход LLM уменьшается с 1396,3 до 212,8 токена, примерно на 84,8%, но точность падает на 43,3 процентного пункта. Одной экономии контекста недостаточно: до оценки селектора необходимо проверять Recall поиска. Возможное объяснение ошибок — короткие английские описания целевых инструментов и семантически близкие альтернативы при русских запросах; это гипотеза, а не установленная причина. Проверка эмбеддингов исключает простую ситуацию одинаковых или нулевых векторов.

Интервалы успеха в B одинаковы: 35,0%–61,7%. Парные разности успеха guard−baseline, hint−baseline и hint−guard равны 0 п.п., bootstrap CI 0–0 на этой выборке. Нулевой интервал отражает совпадение наблюдаемых исходов; он не доказывает эквивалентность методов в генеральной совокупности. У hint средний расход выше baseline на 12,5 токена без прироста успеха. Guard здесь не использовался ни разу, поэтому объявлять его более эффективной защитой на основании малого расхода нельзя.

## 6. Проверки и независимый аудит

Основные 28 тестов проверяют все четыре инструмента в обоих форматах, ошибки, валидацию схем, discovery, метаданные и сохранение handle после перезапуска. Дополнительные 12 проверяют состав данных и gold, поиск внутри текущего пула, нормализацию вызовов, обнаружение обоих паттернов петель, остановку guard до исполнения, bootstrap по кластерам, парные отказы, изменение только пустого ответа и требование реально наблюдаемой записи для успеха.

Совместный прогон: **40 passed**; failures/errors — 0. Длительность testsuite в сохранённом XML — 11,063 секунды. Отдельная работоспособность guard подтверждена тестами паттернов, но его полезность в агентных эпизодах не установлена.

Аудит повторно проверяет полноту 720 решений и 180 эпизодов, совпадение gold, размеры каталогов, парность seed/порядка, идентичность запросов при N=5, суммы usage, маски отказов, корректность финального успеха и критерии петель. Результат аудита:


```json
{
  "selection_rows_verified": 720,
  "episodes_verified": 180,
  "checks": [
    "gold_labels",
    "recomputed_accuracy",
    "candidate_count",
    "paired_seeds_and_order",
    "N5_identical_requests",
    "token_usage_sum",
    "fault_masks",
    "observed_success",
    "loop_definitions",
    "guard_prevents_execution"
  ]
}
```

## 7. Воспроизведение

Команды PowerShell выполняются из каталога проекта. Для независимого повторения используется новый каталог результатов: исходные наблюдения не перезаписываются. Доступ к API-ключам не требуется; модель запускается локально. Для скачивания пакетов, Inspector и весов нужен интернет. Полный lock-файл рассчитан на использованное окружение Windows/Python 3.13.

```powershell
Set-Location 'D:/lesson-02-mcp-demo/mcp-demo'
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe client.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe measure_tokens.py
npm install --prefix .inspector @modelcontextprotocol/inspector@2.10.1
.\.venv\Scripts\python.exe run_inspector.py --cli .inspector/node_modules/@modelcontextprotocol/inspector/clients/launcher/build/index.js
.\.venv\Scripts\python.exe experiments/download_models.py --directory D:/lesson-02-mcp-demo/.runtime/qwen-experiments
.\.venv\Scripts\python.exe experiments/run_all.py --runtime D:/lesson-02-mcp-demo/.runtime/qwen-experiments --output experiments/results-new
```

run_all.py запускает два локальных сервиса моделей и завершает собственные процессы по окончании. При занятом порте останавливается; чужие процессы не завершает. Для сравнения сохраняются фиксированные данные и параметры. При изменении модели, данных или guard нужен отдельный каталог, чтобы не смешать условия.

## 8. Файлы доказательств

Отчёт содержит все численные результаты и полные перечни примеров. Для проверки на уровне каждого вызова доступны следующие файлы рядом с отчётом:


| Файл | Содержание |
| --- | --- |
| [server.py](server.py) | Реализация основных инструментов и схем |
| [client.py](client.py) | Stateless JSON-RPC клиент с _meta |
| [README.md](README.md) | Документация реализации и три примера токенов |
| [artifacts/wire-log.json](artifacts/wire-log.json) | Реальные discovery, tools/list, вызовы и ошибки |
| [artifacts/token-counts.json](artifacts/token-counts.json) | Тексты шести ответов и подсчёт токенов |
| [artifacts/inspector-log.json](artifacts/inspector-log.json) | Девять настоящих запусков Inspector |
| [artifacts/pytest-results.xml](artifacts/pytest-results.xml) | 28 основных тестов |
| [experiments/results/pytest-all.xml](experiments/results/pytest-all.xml) | 40 тестов совместно |
| [experiments/results/selection.jsonl](experiments/results/selection.jsonl) | Все 720 решений с запросами, ответами и usage |
| [experiments/results/retrieval.json](experiments/results/retrieval.json) | 120 результатов поиска: 30 запросов × 4 N |
| [experiments/results/embeddings.json](experiments/results/embeddings.json) | Векторы каталога и запросов |
| [experiments/results/embedding-sanity.json](experiments/results/embedding-sanity.json) | Проверка векторов |
| [experiments/results/loops.jsonl](experiments/results/loops.jsonl) | Все 180 эпизодов и их исходы |
| [experiments/results/loop-mcp-wire.json](experiments/results/loop-mcp-wire.json) | Настоящий MCP обмен нестабильного инструмента |
| [experiments/results/summary.json](experiments/results/summary.json) | Метрики и bootstrap интервалы без округления |
| [experiments/results/audit.json](experiments/results/audit.json) | Независимая проверка журналов |
| [experiments/results/run-settings.json](experiments/results/run-settings.json) | Настройки и SHA-256 исходников/данных |
| [experiments/results/model-manifest.json](experiments/results/model-manifest.json) | Ревизии и SHA-256 моделей и runtime |
| [experiments/results/chat-server.log](experiments/results/chat-server.log) | Журнал генеративной модели |
| [experiments/results/embedding-server.log](experiments/results/embedding-server.log) | Журнал embedding-модели |


## Приложение A. Полный пул из 100 инструментов

Порядок совпадает с tools.json. Пулы N — первые N строк; «целевой» — исполняемый инструмент, «близкий»/«дальний» — синтетическое отвлекающее описание. Описания представлены дословно, поскольку по ним строился индекс.


| № | Имя | Тип | Описание |
| --- | --- | --- | --- |
| 1 | schedule_search | целевой | Search the explicit synthetic schedule snapshot by course and weekday. |
| 2 | schedule_get | целевой | Get one schedule entry; obtain entry_id using schedule_search. |
| 3 | schedule_day | целевой | List every scheduled class on one supported weekday. |
| 4 | schedule_room | целевой | List classes in one supported classroom. |
| 5 | exam_get | близкий | Get one examination by examination identifier from the exam timetable. |
| 6 | git_list | дальний | Retrieve commit changes for the git domain. |
| 7 | devices_get | дальний | Retrieve device firmware versions for the devices domain. |
| 8 | exam_search | близкий | Search the synthetic examination timetable by course and exam date; returns exams, not ordinary classes. |
| 9 | weather_inspect | дальний | Retrieve air quality readings for the weather domain. |
| 10 | issues_list | дальний | Retrieve issue comments for the issues domain. |
| 11 | schedule_notifications | близкий | Configure reminders about upcoming classes; changes notification settings. |
| 12 | files_search | дальний | Retrieve local file names for the files domain. |
| 13 | inventory_inspect | дальний | Retrieve shipment records for the inventory domain. |
| 14 | room_details | близкий | Read classroom capacity, facilities and building address by room number. |
| 15 | inventory_list | дальний | Retrieve warehouse locations for the inventory domain. |
| 16 | weather_get | дальний | Retrieve weather observations for the weather domain. |
| 17 | teacher_schedule_search | близкий | Search a specific teacher's teaching workload by teacher and weekday. |
| 18 | mail_list | дальний | Retrieve mail folders for the mail domain. |
| 19 | devices_search | дальний | Retrieve network device records for the devices domain. |
| 20 | schedule_delete | близкий | Delete a class entry from the synthetic course timetable. |
| 21 | finance_inspect | дальний | Retrieve company fundamentals for the finance domain. |
| 22 | images_inspect | дальний | Retrieve image copyright metadata for the images domain. |
| 23 | room_availability | близкий | Find free classroom time slots; returns availability rather than scheduled classes. |
| 24 | support_inspect | дальний | Retrieve customer contact profiles for the support domain. |
| 25 | issues_search | дальний | Retrieve software issue tickets for the issues domain. |
| 26 | teacher_schedule_get | близкий | Get a teacher workload entry by workload identifier. |
| 27 | mail_inspect | дальний | Retrieve email attachments for the mail domain. |
| 28 | analytics_get | дальний | Retrieve traffic metrics for the analytics domain. |
| 29 | consultation_get | близкий | Get one teacher consultation appointment by appointment identifier. |
| 30 | issues_get | дальний | Retrieve issue details for the issues domain. |
| 31 | weather_list | дальний | Retrieve precipitation alerts for the weather domain. |
| 32 | archive_schedule_get | близкий | Read one archived schedule entry using an archive record identifier. |
| 33 | support_search | дальний | Retrieve customer support cases for the support domain. |
| 34 | finance_list | дальний | Retrieve exchange rates for the finance domain. |
| 35 | calendar_search | близкий | Search a student's personal calendar appointments by date and title. |
| 36 | fitness_inspect | дальний | Retrieve equipment specifications for the fitness domain. |
| 37 | music_search | дальний | Retrieve music tracks for the music domain. |
| 38 | archive_schedule_room | близкий | List historical classes held in a classroom during a previous semester. |
| 39 | issues_inspect | дальний | Retrieve issue labels for the issues domain. |
| 40 | maps_search | дальний | Retrieve street addresses for the maps domain. |
| 41 | archive_schedule_day | близкий | List all historical course classes on a weekday in an archived semester. |
| 42 | travel_list | дальний | Retrieve flight routes for the travel domain. |
| 43 | devices_list | дальний | Retrieve device status readings for the devices domain. |
| 44 | course_enroll | близкий | Enroll a student in a course; changes the enrollment roster. |
| 45 | books_search | дальний | Retrieve library books for the books domain. |
| 46 | git_get | дальний | Retrieve repository branches for the git domain. |
| 47 | schedule_update | близкий | Change the time, weekday or classroom of an existing class entry. |
| 48 | finance_search | дальний | Retrieve stock quotes for the finance domain. |
| 49 | analytics_search | дальний | Retrieve website traffic events for the analytics domain. |
| 50 | schedule_conflicts | близкий | Detect overlapping classroom bookings and conflicting class times. |
| 51 | git_search | дальний | Retrieve source code commits for the git domain. |
| 52 | weather_search | дальний | Retrieve city weather forecasts for the weather domain. |
| 53 | exam_room | близкий | List examinations in a classroom; excludes regular course classes. |
| 54 | travel_search | дальний | Retrieve hotel listings for the travel domain. |
| 55 | fitness_search | дальний | Retrieve exercise routines for the fitness domain. |
| 56 | consultation_room | близкий | List office-hour consultation slots in a classroom. |
| 57 | files_inspect | дальний | Retrieve file metadata for the files domain. |
| 58 | analytics_list | дальний | Retrieve conversion funnels for the analytics domain. |
| 59 | calendar_get | близкий | Read one personal calendar event using an event identifier. |
| 60 | files_list | дальний | Retrieve directory listings for the files domain. |
| 61 | recipes_search | дальний | Retrieve cooking recipes for the recipes domain. |
| 62 | schedule_export | близкий | Export the complete course timetable to an ICS calendar file. |
| 63 | support_list | дальний | Retrieve support case messages for the support domain. |
| 64 | fitness_list | дальний | Retrieve workout records for the fitness domain. |
| 65 | schedule_bus | близкий | Search campus shuttle bus departure times by stop and weekday. |
| 66 | music_list | дальний | Retrieve artist biographies for the music domain. |
| 67 | inventory_get | дальний | Retrieve product stock levels for the inventory domain. |
| 68 | exam_day | близкий | List every examination on one weekday in the examination timetable. |
| 69 | maps_list | дальний | Retrieve geographic coordinates for the maps domain. |
| 70 | books_list | дальний | Retrieve author biographies for the books domain. |
| 71 | archive_schedule_search | близкий | Search historical course schedule snapshots from previous semesters. |
| 72 | mail_get | дальний | Retrieve email contents for the mail domain. |
| 73 | files_get | дальний | Retrieve file contents for the files domain. |
| 74 | consultation_search | близкий | Search teacher office-hour appointments by course and weekday. |
| 75 | recipes_list | дальний | Retrieve nutrition information for the recipes domain. |
| 76 | books_inspect | дальний | Retrieve book reviews for the books domain. |
| 77 | schedule_create | близкий | Create a new class in the synthetic course schedule; modifies the timetable. |
| 78 | fitness_get | дальний | Retrieve exercise descriptions for the fitness domain. |
| 79 | images_get | дальний | Retrieve image dimensions for the images domain. |
| 80 | consultation_day | близкий | List teacher consultations and office hours on a weekday. |
| 81 | music_inspect | дальний | Retrieve playlists for the music domain. |
| 82 | books_get | дальний | Retrieve book editions for the books domain. |
| 83 | calendar_day | близкий | List personal calendar appointments on a date, including non-course events. |
| 84 | maps_inspect | дальний | Retrieve nearby landmarks for the maps domain. |
| 85 | music_get | дальний | Retrieve album metadata for the music domain. |
| 86 | course_details | близкий | Read a course syllabus and prerequisites by course identifier; contains no class times. |
| 87 | analytics_inspect | дальний | Retrieve audience segments for the analytics domain. |
| 88 | support_get | дальний | Retrieve support case details for the support domain. |
| 89 | images_search | дальний | Retrieve image asset names for the images domain. |
| 90 | finance_get | дальний | Retrieve historical market prices for the finance domain. |
| 91 | images_list | дальний | Retrieve image color palettes for the images domain. |
| 92 | maps_get | дальний | Retrieve walking directions for the maps domain. |
| 93 | inventory_search | дальний | Retrieve warehouse products for the inventory domain. |
| 94 | mail_search | дальний | Retrieve email messages for the mail domain. |
| 95 | recipes_inspect | дальний | Retrieve cooking techniques for the recipes domain. |
| 96 | travel_get | дальний | Retrieve hotel room types for the travel domain. |
| 97 | recipes_get | дальний | Retrieve recipe ingredients for the recipes domain. |
| 98 | git_inspect | дальний | Retrieve repository tags for the git domain. |
| 99 | travel_inspect | дальний | Retrieve airport information for the travel domain. |
| 100 | devices_inspect | дальний | Retrieve device configuration backups for the devices domain. |



## Приложение B. Все 30 запросов с эталонным инструментом


| ID | Запрос | Правильный инструмент |
| --- | --- | --- |
| q01 | Найди занятия курса agents в текущем учебном расписании. | schedule_search |
| q02 | Покажи все занятия курса python из снимка schedule-v1. | schedule_search |
| q03 | Какие пары по databases стоят в расписании? | schedule_search |
| q04 | Найди занятия agents, которые проходят в среду. | schedule_search |
| q05 | Проверь расписание курса python на вторник. | schedule_search |
| q06 | Выведи все записи текущего расписания без фильтров. | schedule_search |
| q07 | Нужен поиск пар по курсу agents и дню monday. | schedule_search |
| q08 | Есть ли у databases занятия в понедельник? | schedule_search |
| q09 | Открой занятие с идентификатором agents-mon. | schedule_get |
| q10 | Получить одну запись расписания: python-tue. | schedule_get |
| q11 | Покажи подробности занятия databases-wed из schedule-v1. | schedule_get |
| q12 | Мне нужна конкретная пара agents-wed, её id уже известен. | schedule_get |
| q13 | Прочитай запись agents-mon без поиска других занятий. | schedule_get |
| q14 | У меня есть entry_id python-tue. Покажи соответствующее занятие. | schedule_get |
| q15 | По ключу databases-wed получить занятие текущего расписания. | schedule_get |
| q16 | Верни подробную запись пары agents-wed по её идентификатору. | schedule_get |
| q17 | Выведи все учебные пары в понедельник, независимо от курса. | schedule_day |
| q18 | Какие занятия текущего расписания проходят во вторник? Нужны все курсы. | schedule_day |
| q19 | Покажи полное расписание учебных занятий на среду. | schedule_day |
| q20 | Мне нужен список всех пар на monday из schedule-v1. | schedule_day |
| q21 | Собери все занятия вторника, без фильтра по предмету. | schedule_day |
| q22 | Что стоит в учебном расписании на wednesday по всем курсам? | schedule_day |
| q23 | Список обычных учебных занятий понедельника целиком. | schedule_day |
| q24 | Какие учебные пары запланированы в аудитории 314? | schedule_room |
| q25 | Покажи занятия в кабинете 210 из текущего расписания. | schedule_room |
| q26 | Все запланированные занятия аудитории 115. | schedule_room |
| q27 | Нужен список пар, проходящих в комнате 314, по всем дням. | schedule_room |
| q28 | Что за учебные занятия стоят для аудитории 210 в schedule-v1? | schedule_room |
| q29 | Перечисли пары в кабинете 115 без проверки свободных мест. | schedule_room |
| q30 | Для аудитории 314 получи запланированные занятия всех курсов. | schedule_room |



## Приложение C. Все 20 задач части B

Каждая задача выполнялась трижды в каждом из трёх условий. Handle для всех задач — schedule-v1.


| ID | Задача |
| --- | --- |
| t01 | Найди хотя бы одно занятие курса agents между 2026-10-12 и 2026-10-19 включительно. Начни с date=2026-10-12. Верни найденные entry_id и date; используй только данные инструмента. |
| t02 | Найди хотя бы одно занятие курса python между 2026-10-13 и 2026-10-20 включительно. Начни с date=2026-10-13. Верни найденные entry_id и date; используй только данные инструмента. |
| t03 | Найди хотя бы одно занятие курса databases между 2026-10-14 и 2026-10-21 включительно. Начни с date=2026-10-14. Верни найденные entry_id и date; используй только данные инструмента. |
| t04 | Найди хотя бы одно занятие курса agents между 2026-10-19 и 2026-10-26 включительно. Начни с date=2026-10-19. Верни найденные entry_id и date; используй только данные инструмента. |
| t05 | Найди хотя бы одно занятие курса python между 2026-10-20 и 2026-10-27 включительно. Начни с date=2026-10-20. Верни найденные entry_id и date; используй только данные инструмента. |
| t06 | Найди хотя бы одно занятие курса databases между 2026-10-21 и 2026-10-28 включительно. Начни с date=2026-10-21. Верни найденные entry_id и date; используй только данные инструмента. |
| t07 | Найди хотя бы одно занятие курса agents между 2026-10-26 и 2026-11-02 включительно. Начни с date=2026-10-26. Верни найденные entry_id и date; используй только данные инструмента. |
| t08 | Найди хотя бы одно занятие курса python между 2026-10-27 и 2026-11-03 включительно. Начни с date=2026-10-27. Верни найденные entry_id и date; используй только данные инструмента. |
| t09 | Найди хотя бы одно занятие курса databases между 2026-10-28 и 2026-11-04 включительно. Начни с date=2026-10-28. Верни найденные entry_id и date; используй только данные инструмента. |
| t10 | Найди хотя бы одно занятие курса agents между 2026-11-02 и 2026-11-09 включительно. Начни с date=2026-11-02. Верни найденные entry_id и date; используй только данные инструмента. |
| t11 | Найди хотя бы одно занятие курса python между 2026-11-03 и 2026-11-10 включительно. Начни с date=2026-11-03. Верни найденные entry_id и date; используй только данные инструмента. |
| t12 | Найди хотя бы одно занятие курса databases между 2026-11-04 и 2026-11-11 включительно. Начни с date=2026-11-04. Верни найденные entry_id и date; используй только данные инструмента. |
| t13 | Найди хотя бы одно занятие курса agents между 2026-11-09 и 2026-11-16 включительно. Начни с date=2026-11-09. Верни найденные entry_id и date; используй только данные инструмента. |
| t14 | Найди хотя бы одно занятие курса python между 2026-11-10 и 2026-11-17 включительно. Начни с date=2026-11-10. Верни найденные entry_id и date; используй только данные инструмента. |
| t15 | Найди хотя бы одно занятие курса databases между 2026-11-11 и 2026-11-18 включительно. Начни с date=2026-11-11. Верни найденные entry_id и date; используй только данные инструмента. |
| t16 | Найди хотя бы одно занятие курса agents между 2026-11-16 и 2026-11-23 включительно. Начни с date=2026-11-16. Верни найденные entry_id и date; используй только данные инструмента. |
| t17 | Найди хотя бы одно занятие курса python между 2026-11-17 и 2026-11-24 включительно. Начни с date=2026-11-17. Верни найденные entry_id и date; используй только данные инструмента. |
| t18 | Найди хотя бы одно занятие курса databases между 2026-11-18 и 2026-11-25 включительно. Начни с date=2026-11-18. Верни найденные entry_id и date; используй только данные инструмента. |
| t19 | Найди хотя бы одно занятие курса agents между 2026-11-23 и 2026-11-30 включительно. Начни с date=2026-11-23. Верни найденные entry_id и date; используй только данные инструмента. |
| t20 | Найди хотя бы одно занятие курса python между 2026-11-24 и 2026-12-01 включительно. Начни с date=2026-11-24. Верни найденные entry_id и date; используй только данные инструмента. |



## Приложение D. Полные входные схемы четырёх основных инструментов

Схемы получены из каталога фактического сервера. На верхнем уровне дополнительных полей нет; описания есть у всех параметров. entry_id открыт, остальные закрытые доменные множества используют enum.


### schedule_search

```json
{
  "properties": {
    "schedule_handle": {
      "description": "Explicit immutable schedule snapshot handle.",
      "title": "Schedule Handle",
      "type": "string",
      "enum": [
        "schedule-v1"
      ]
    },
    "course": {
      "default": "all",
      "description": "Course filter; all selects every course.",
      "enum": [
        "all",
        "agents",
        "python",
        "databases"
      ],
      "title": "Course",
      "type": "string"
    },
    "day": {
      "default": "all",
      "description": "Weekday filter; all selects every day.",
      "enum": [
        "all",
        "monday",
        "tuesday",
        "wednesday"
      ],
      "title": "Day",
      "type": "string"
    },
    "response_format": {
      "default": "concise",
      "description": "Amount of detail in the response.",
      "enum": [
        "concise",
        "detailed"
      ],
      "title": "Response Format",
      "type": "string"
    }
  },
  "required": [
    "schedule_handle"
  ],
  "title": "schedule_searchArguments",
  "type": "object",
  "additionalProperties": false,
  "description": "Search the explicit synthetic schedule snapshot by course and weekday."
}
```


### schedule_get

```json
{
  "properties": {
    "schedule_handle": {
      "description": "Explicit immutable schedule snapshot handle.",
      "title": "Schedule Handle",
      "type": "string",
      "enum": [
        "schedule-v1"
      ]
    },
    "entry_id": {
      "description": "Entry identifier returned by schedule_search.",
      "maxLength": 64,
      "minLength": 1,
      "title": "Entry Id",
      "type": "string"
    },
    "response_format": {
      "default": "concise",
      "description": "Amount of detail in the response.",
      "enum": [
        "concise",
        "detailed"
      ],
      "title": "Response Format",
      "type": "string"
    }
  },
  "required": [
    "schedule_handle",
    "entry_id"
  ],
  "title": "schedule_getArguments",
  "type": "object",
  "additionalProperties": false,
  "description": "Get one schedule entry; obtain entry_id using schedule_search."
}
```


### schedule_day

```json
{
  "properties": {
    "schedule_handle": {
      "description": "Explicit immutable schedule snapshot handle.",
      "title": "Schedule Handle",
      "type": "string",
      "enum": [
        "schedule-v1"
      ]
    },
    "day": {
      "description": "Weekday to inspect.",
      "enum": [
        "monday",
        "tuesday",
        "wednesday"
      ],
      "title": "Day",
      "type": "string"
    },
    "response_format": {
      "default": "concise",
      "description": "Amount of detail in the response.",
      "enum": [
        "concise",
        "detailed"
      ],
      "title": "Response Format",
      "type": "string"
    }
  },
  "required": [
    "schedule_handle",
    "day"
  ],
  "title": "schedule_dayArguments",
  "type": "object",
  "additionalProperties": false,
  "description": "List every scheduled class on one supported weekday."
}
```


### schedule_room

```json
{
  "properties": {
    "schedule_handle": {
      "description": "Explicit immutable schedule snapshot handle.",
      "title": "Schedule Handle",
      "type": "string",
      "enum": [
        "schedule-v1"
      ]
    },
    "room": {
      "description": "Supported classroom number.",
      "enum": [
        "314",
        "210",
        "115"
      ],
      "title": "Room",
      "type": "string"
    },
    "response_format": {
      "default": "concise",
      "description": "Amount of detail in the response.",
      "enum": [
        "concise",
        "detailed"
      ],
      "title": "Response Format",
      "type": "string"
    }
  },
  "required": [
    "schedule_handle",
    "room"
  ],
  "title": "schedule_roomArguments",
  "type": "object",
  "additionalProperties": false,
  "description": "List classes in one supported classroom."
}
```


### Общая выходная схема успешного результата

Ошибка передаётся как isError с текстовым JSON code/message/hint. Успешный результат содержит совпадающие content и structuredContent; это учтено при измерении полного размера.


```json
{
  "type": "object",
  "description": "Synthetic schedule query result.",
  "additionalProperties": false,
  "required": [
    "schedule_handle",
    "synthetic",
    "entries"
  ],
  "properties": {
    "schedule_handle": {
      "type": "string",
      "description": "Immutable snapshot handle.",
      "enum": [
        "schedule-v1"
      ]
    },
    "synthetic": {
      "type": "boolean",
      "enum": [
        true
      ],
      "description": "Data are invented for this exercise."
    },
    "source": {
      "type": "string",
      "description": "Fixture provenance.",
      "enum": [
        "fixture:schedule-v1"
      ]
    },
    "timezone": {
      "type": "string",
      "description": "Timezone of the listed class times.",
      "enum": [
        "Europe/Moscow"
      ]
    },
    "note": {
      "type": "string",
      "description": "Disclaimer about the synthetic dataset."
    },
    "entries": {
      "type": "array",
      "description": "Matching classes; empty when no classes match.",
      "items": {
        "type": "object",
        "description": "One class; detailed mode adds course, end and teacher.",
        "additionalProperties": false,
        "required": [
          "id",
          "day",
          "start",
          "room"
        ],
        "properties": {
          "id": {
            "type": "string",
            "description": "Entry identifier for schedule_get."
          },
          "course": {
            "type": "string",
            "description": "Course identifier.",
            "enum": [
              "agents",
              "python",
              "databases"
            ]
          },
          "day": {
            "type": "string",
            "description": "Class weekday.",
            "enum": [
              "monday",
              "tuesday",
              "wednesday"
            ]
          },
          "start": {
            "type": "string",
            "description": "Start time HH:MM in the schedule timezone."
          },
          "end": {
            "type": "string",
            "description": "End time HH:MM in the schedule timezone."
          },
          "room": {
            "type": "string",
            "description": "Classroom number.",
            "enum": [
              "314",
              "210",
              "115"
            ]
          },
          "teacher": {
            "type": "string",
            "description": "Synthetic teacher name."
          }
        }
      }
    }
  }
}
```

## Приложение E. Источники

Протокольная реализация опирается на [спецификацию MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28), [описание изменений версии](https://blog.modelcontextprotocol.io/posts/2026-07-28/) и [Python SDK](https://github.com/modelcontextprotocol/python-sdk). Режим и коды Inspector описаны в [официальной документации CLI](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md).

Модели: [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B), [официальный GGUF генеративной модели](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF), [официальный GGUF Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF). Сервер локального выполнения: [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md). Источник всех экспериментальных чисел — собственные журналы проекта, перечисленные в разделе 8.
