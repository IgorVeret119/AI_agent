# MCP: синтетическое расписание курсов

Домен сохранён из исходного примера ДЗ 1: расписание курсов. Все занятия, преподаватели и аудитории вымышлены. SDK `mcp==2.2.0`, импорт `from mcp.server import MCPServer`, протокол **2026-07-28**, транспорт stdio.

## Запуск

Обычный Python 3.13 на Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe client.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe measure_tokens.py
```

`requirements.txt` задаёт основные зависимости; `requirements-lock.txt` фиксирует все версии проверенного окружения Windows/Python 3.13. При первом измерении tiktoken скачивает словарь `cl100k_base`. Сам сервер работает только с локальной неизменяемой фикстурой.

## Контракт инструментов

| Инструмент | Назначение | Обязательные аргументы |
| --- | --- | --- |
| `schedule_search` | Фильтр по курсу и дню; `all` — без фильтра | `schedule_handle` |
| `schedule_get` | Занятие по идентификатору из поиска | `schedule_handle`, `entry_id` |
| `schedule_day` | Все занятия указанного дня | `schedule_handle`, `day` |
| `schedule_room` | Все занятия в аудитории | `schedule_handle`, `room` |

Каждый инструмент принимает `response_format`: enum `concise` / `detailed`, по умолчанию `concise`. Входные и выходные объекты закрыты: `additionalProperties: false`, у всех полей есть `description`. Курсы, дни, аудитории и форматы объявлены через `enum`; строка аудитории `"314"` и число `314` различаются. `entry_id` — открытый идентификатор, его нужно получать из поиска. Источник истины для аргументов — `tools/list`.

`concise` возвращает `id`, `day`, `start`, `room`. `detailed` добавляет `course`, `end`, `teacher`, источник, часовой пояс и пояснение. Оба режима сохраняют `schedule_handle` и `synthetic: true`. Отсутствие совпадений при поиске — успешный ответ с пустым `entries`.

## Stateless и discovery

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

## Ошибки

Ошибки инструментов возвращаются как результат `tools/call` с `isError: true`. Текстовый блок содержит JSON с `code`, `message`, `hint`. Например, `schedule_get` с несуществующим `entry_id` возвращает `entry_not_found` и совет выполнить `schedule_search` с тем же handle. Неверные типы, enum, лишние и отсутствующие поля получают `invalid_arguments` и подсказку свериться с `tools/list`. Неожиданные внутренние ошибки заменяются безопасным сообщением без стектрейса. Протокольные ошибки, например некорректный JSON-RPC, остаются ошибками протокола SDK.

## Размер ответа в токенах

Измерено `tiktoken==0.11.0`, encoding `cl100k_base`. В каждой ячейке: **текст `content[0].text` / полный JSON результата `tools/call`**. Полный результат сериализован с `ensure_ascii=False`, `separators=(",", ":")`; включает текст, `structuredContent` и поля SDK, но не JSON-RPC оболочку `id/jsonrpc/result`. Это воспроизводимый подсчёт выбранным токенизатором, а не универсальная стоимость для любой модели. Текст и structuredContent содержат одинаковые данные, поэтому полный результат крупнее.

Общий аргумент всех примеров: `schedule_handle="schedule-v1"`.

| Пример | concise: текст / результат | detailed: текст / результат |
| --- | ---: | ---: |
| `schedule_search(course="agents")` | 57 / 167 | 118 / 288 |
| `schedule_get(entry_id="agents-mon")` | 36 / 123 | 81 / 212 |
| `schedule_day(day="wednesday")` | 59 / 171 | 121 / 294 |

Исходные ответы и измерения: [artifacts/token-counts.json](artifacts/token-counts.json). Повторный подсчёт: `python measure_tokens.py`.

## Проверки и MCP Inspector

`test_server.py` запускает реальный сервер отдельным процессом и проверяет через MCP: успех каждого инструмента в обоих форматах, ошибки каждого инструмента, неверные типы и enum, лишние поля, отсутствие handle, неизвестный инструмент, ненайденную запись, пустой поиск, входные/выходные схемы, discovery, `_meta`, вызов до discovery и handle после перезапуска.

Для Inspector нужен Node.js >=22.19. Проверяемая версия Inspector: `2.10.1`.

```powershell
npm install --prefix .inspector @modelcontextprotocol/inspector@2.10.1
.\.venv\Scripts\python.exe run_inspector.py --cli .inspector/node_modules/@modelcontextprotocol/inspector/clients/launcher/build/index.js
```

Скрипт запускает официальный Inspector CLI в режиме `--protocol-era modern`: каталог со строгой проверкой схем и успешный/ошибочный вызов всех четырёх инструментов. Для ошибки инструмента ожидается код завершения Inspector `5`, для успеха — `0`. Сохраняются полные команды, stdout, stderr и коды завершения в [artifacts/inspector-log.json](artifacts/inspector-log.json). JSON-RPC обмен нашего клиента хранится отдельно и не выдаётся за лог Inspector.

Проверено 9 октября 2026 года: **28 pytest-тестов прошли**, отчёт [artifacts/pytest-results.xml](artifacts/pytest-results.xml); **все 9 запусков Inspector прошли** (каталог + 4 успеха + 4 ожидаемые ошибки), стектрейсов в логе нет. Окружение: Windows, Python 3.13.7, MCP SDK 2.2.0, Node.js 22.20.0, Inspector 2.10.1. Inspector получает аргументы через `--tool-args-json`, чтобы номер аудитории оставался строкой.

## Официальные источники

Эксперименты выбора из 100 инструментов и агентных петель находятся в [experiments/README.md](experiments/README.md). Итоговые измерения с Qwen3-0.6B, Recall@5, токенами и бутстрэп-интервалами: [experiments/results/REPORT.md](experiments/results/REPORT.md).

- [Спецификация MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [Изменения stateless, discovery и `_meta`](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [Python SDK v2](https://github.com/modelcontextprotocol/python-sdk)
- [Inspector CLI: команды, modern mode и коды завершения](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md)
