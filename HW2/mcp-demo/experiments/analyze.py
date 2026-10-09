"""Aggregate saved real runs, with query-cluster percentile bootstrap CIs."""
import argparse
import collections
import json
import statistics
from pathlib import Path

from core import clustered_ci

ROOT = Path(__file__).resolve().parent


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def grouped(rows, metric, id_field):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row[id_field]].append(float(metric(row)))
    return dict(groups)


def paired_delta(left, right, metric, id_field):
    a = {(row[id_field], row["repeat"]): metric(row) for row in left}
    b = {(row[id_field], row["repeat"]): metric(row) for row in right}
    if set(a) != set(b):
        raise ValueError("Unpaired observations")
    groups = collections.defaultdict(list)
    for (identifier, repeat), value in a.items():
        groups[identifier].append(float(b[identifier, repeat]) - float(value))
    return {"mean": statistics.mean([v for values in groups.values() for v in values]), "ci95": clustered_ci(groups)}


def percent(value):
    return f"{100 * value:.1f}%"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "results"))
    args = parser.parse_args()
    output = Path(args.output)
    selection = read_rows(output / "selection.jsonl")
    loops = read_rows(output / "loops.jsonl")
    retrieval = json.loads((output / "retrieval.json").read_text(encoding="utf-8"))
    assert len(selection) == 720 and len(loops) == 180 and len(retrieval) == 120, "Incomplete benchmark"
    assert len({(r["n"], r["variant"], r["repeat"], r["query_id"]) for r in selection}) == 720
    assert len({(r["variant"], r["repeat"], r["task_id"]) for r in loops}) == 180
    summary = {"selection": [], "loops": [], "selection_paired_deltas": {}, "loop_paired_deltas": {}, "bootstrap": {"unit_A": "queries", "clusters_A": 30, "repeats_per_cluster": 3, "unit_B": "tasks", "clusters_B": 20, "draws": 10000, "seed": 20261009, "interval": "percentile 2.5%,97.5%"}}
    for n in (5, 20, 50, 100):
        at_n = [r for r in retrieval if r["n"] == n]
        for variant in ("A", "B"):
            rows = [r for r in selection if (r["n"], r["variant"]) == (n, variant)]
            assert len(rows) == 90
            summary["selection"].append({"n": n, "variant": variant, "calls": len(rows), "accuracy": statistics.mean(r["correct"] for r in rows), "accuracy_ci95": clustered_ci(grouped(rows, lambda r: r["correct"], "query_id")), "retrieval_recall_at5": statistics.mean(r["hit"] for r in at_n) if variant == "B" else None, "mean_llm_input_tokens": statistics.mean(r["raw"]["usage"]["prompt_tokens"] for r in rows), "mean_query_embedding_tokens": statistics.mean(r["query_embedding_tokens"] for r in rows), "mean_input_tokens_with_query_embedding": statistics.mean(r["raw"]["usage"]["prompt_tokens"] + r["query_embedding_tokens"] for r in rows), "invalid_or_out_of_catalog": sum(not isinstance(r["predicted"], str) or r["predicted"] not in r["candidates"] for r in rows)})
        summary["selection_paired_deltas"][str(n)] = paired_delta([r for r in selection if r["n"] == n and r["variant"] == "A"], [r for r in selection if r["n"] == n and r["variant"] == "B"], lambda r: r["correct"], "query_id")
    for variant in ("baseline", "guard", "hint"):
        rows = [r for r in loops if r["variant"] == variant]
        injected = [event["fault_injected"] for row in rows for event in row["trace"] if "fault_injected" in event]
        summary["loops"].append({"variant": variant, "episodes": len(rows), "loop_rate": statistics.mean(r["loop"] for r in rows), "loop_rate_ci95": clustered_ci(grouped(rows, lambda r: r["loop"], "task_id")), "loop_attempt_or_execution_rate": statistics.mean(r["loop_attempt_or_execution"] for r in rows), "success_rate": statistics.mean(r["success"] for r in rows), "success_rate_ci95": clustered_ci(grouped(rows, lambda r: r["success"], "task_id")), "mean_steps": statistics.mean(r["steps"] for r in rows), "mean_executed_calls": statistics.mean(r["executed_calls"] for r in rows), "mean_input_tokens": statistics.mean(r["usage"]["prompt_tokens"] for r in rows), "mean_output_tokens": statistics.mean(r["usage"]["completion_tokens"] for r in rows), "mean_total_tokens": statistics.mean(r["usage"]["total_tokens"] for r in rows), "empirical_fault_rate": statistics.mean(injected) if injected else None, "faulted_calls": sum(injected), "executed_fault_trials": len(injected), "statuses": dict(collections.Counter(r["status"] for r in rows))})
    baseline = [r for r in loops if r["variant"] == "baseline"]
    for variant in ("guard", "hint"):
        rows = [r for r in loops if r["variant"] == variant]
        summary["loop_paired_deltas"][variant] = {"loop_rate": paired_delta(baseline, rows, lambda r: r["loop"], "task_id"), "success_rate": paired_delta(baseline, rows, lambda r: r["success"], "task_id")}
    summary["loop_paired_deltas"]["hint_minus_guard"] = {"loop_rate": paired_delta([r for r in loops if r["variant"] == "guard"], [r for r in loops if r["variant"] == "hint"], lambda r: r["loop"], "task_id"), "success_rate": paired_delta([r for r in loops if r["variant"] == "guard"], [r for r in loops if r["variant"] == "hint"], lambda r: r["success"], "task_id")}
    cache = json.loads((output / "embeddings.json").read_text(encoding="utf-8"))
    summary["embedding_one_time_index_tokens"] = sum(r["prompt_tokens"] for r in cache["tools"].values())
    summary["fault_probability"] = 0.5
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ["# Эксперимент выбора инструментов и агентных петель", "", "Все результаты получены локальной Qwen/Qwen3-0.6B в официальной Q8_0-квантизации; поиск использует Qwen/Qwen3-Embedding-0.6B Q8_0, last pooling и cosine similarity. Non-thinking mode; temperature=0.7, top_p=0.8, top_k=20, min_p=0. Отвлекающие инструменты не исполняются.", "", "## A. Выбор", "", "В каждой строке 30 запросов × 3 повтора. 95%-интервалы: 10 000 бутстрэп-выборок целых запросов, сохраняющих все повторы. Recall@5 вычислен по 30 запросам отдельно от выбора модели. A — все N описаний; B — top-5, найденные только по эмбеддингам описаний.", "", "| N | Вариант | Точность | 95% CI | Recall@5 | Вход LLM, токены | Вход с query embedding |", "| ---: | --- | ---: | --- | ---: | ---: | ---: |"]
    for r in summary["selection"]:
        ci = " – ".join(percent(x) for x in r["accuracy_ci95"])
        recall = "—" if r["retrieval_recall_at5"] is None else percent(r["retrieval_recall_at5"])
        report.append(f"| {r['n']} | {r['variant']} | {percent(r['accuracy'])} | {ci} | {recall} | {r['mean_llm_input_tokens']:.1f} | {r['mean_input_tokens_with_query_embedding']:.1f} |")
    report.extend(["", f"Однократное построение индекса: {summary['embedding_one_time_index_tokens']} входных токенов embedding-модели; это не повторяется для каждого запроса. Query embedding учитывается как логический онлайн-расход для B; при фактическом прогоне он кэшируется один раз для каждого запроса и переиспользуется во всех N и повторах. В таблице LLM учитываются все входные токены, включая KV-кэшированные: usage.prompt_tokens, а не время вычисления.", "", "| N | Парная разница точности B − A | 95% CI |", "| ---: | ---: | --- |"])
    for n, row in summary["selection_paired_deltas"].items():
        report.append(f"| {n} | {percent(row['mean'])} | {' – '.join(percent(x) for x in row['ci95'])} |")
    report.extend(["", "При N=100 сокращение контекста не сохранило точность: правильный инструмент отсутствовал во всех найденных top-5. Это сбой этапа retrieval на данном фиксированном наборе, а не доказательство, что поиск по эмбеддингам вообще бесполезен. Проверка embedding-sanity.json подтвердила размерность 1024, уникальность векторов, cosine≈1 для повторно закодированного описания и меньшую близость нерелевантного описания. Бутстрэп-интервал 0–0 при всех нулевых ответах отражает конечную выборку и не доказывает нулевую точность на любых новых запросах."])
    report.extend(["", "## B. Петли", "", "20 задач × 3 повтора на вариант. baseline — пустой ответ без пояснения; guard — такой же инструмент плюс остановка до третьего одинакового вызова или четвёртого вызова A-B-A-B, окно 6; hint — пояснение вместо пустого ответа, без guard. Алгоритм лекции не предоставлен: использован описанный здесь guard по двум критериям задания, а не подтверждённая копия кода лекции.", "", "Случайный отказ имеет вероятность 50% на каждый вызов. Для одной задачи и повтора одинаковые seed/номер вызова дают одинаковую маску отказов во всех вариантах; сравнение парное. Данные не становятся другими при включении подсказки. Неустойчивый schedule_search реально вызывается через MCP 2026-07-28; fault_handle передаётся явно, сервер не хранит сессию.", "", "| Вариант | Петли (исполненные) | Попытка/петля | Средние шаги | Входные токены | Выходные токены | Всего токенов | Успех |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for r in summary["loops"]:
        report.append(f"| {r['variant']} | {percent(r['loop_rate'])} | {percent(r['loop_attempt_or_execution_rate'])} | {r['mean_steps']:.2f} | {r['mean_input_tokens']:.1f} | {r['mean_output_tokens']:.1f} | {r['mean_total_tokens']:.1f} | {percent(r['success_rate'])} |")
    rows = {r["variant"]: r for r in summary["loops"]}
    report.extend(["", "Один шаг — один вызов модели, включая финальный ответ или предложение вызова, заблокированное guard. Токены эпизода — сумма usage всех таких шагов, включая повторно переданную историю. Успех требует финальной ссылки на действительно полученную запись нужного курса внутри разрешённого интервала; выдуманный ответ и остановка guard не считаются успехом. Петля проверяется по каноническому JSON имени инструмента и доменных аргументов. fault_handle и response_mode являются управляющими полями harness и не участвуют в сигнатуре. Ограничение каждого эпизода — 12 шагов; завершение по лимиту не объявляется петлёй автоматически.", "", "## Что помогает сильнее", "", f"С guard доля исполненных петель — {percent(rows['guard']['loop_rate'])}, без guard — {percent(rows['baseline']['loop_rate'])}; успех соответственно {percent(rows['guard']['success_rate'])} и {percent(rows['baseline']['success_rate'])}. Подсказка без guard дала {percent(rows['hint']['loop_rate'])} петель и {percent(rows['hint']['success_rate'])} успеха."])
    if rows["hint"]["success_rate"] > rows["guard"]["success_rate"]:
        report.append("По выполнению задач подсказка оказалась полезнее guard на этом наборе. Guard предотвращает исполнение заданных паттернов конструктивно, но может прервать повтор, который преодолел бы случайный отказ.")
    elif rows["hint"]["success_rate"] < rows["guard"]["success_rate"]:
        report.append("По выполнению задач guard оказался полезнее подсказки на этом наборе. Подсказка не гарантирует, что небольшая модель изменит аргументы корректно.")
    else:
        report.append("По доле выполненных задач варианты совпали; решающего преимущества по этой метрике нет. Сравните токены, исполненные петли и попытки петель.")
    difference = summary["loop_paired_deltas"]["hint_minus_guard"]["success_rate"]
    report.append(f"Парная разница успеха hint − guard: {percent(difference['mean'])}, 95% CI {' – '.join(percent(x) for x in difference['ci95'])}. Это исследовательская оценка на 20 задачах; она не устанавливает универсального преимущества на других моделях и доменах.")
    if difference["ci95"][0] <= 0 <= difference["ci95"][1]:
        report.append("Интервал включает ноль: убедительного преимущества одного варианта по успеху на этом наборе не установлено; направление точечной оценки не равно статистически подтверждённому выигрышу.")
    if rows["baseline"]["loop_rate"] == 0:
        report.append("В baseline заданные паттерны петель не встретились. Этот прогон не позволяет эмпирически оценить устранение петель guard: нет наблюдавшихся петель для устранения. Неуспешный эпизод может закончиться выдуманным финальным ответом вместо повторных вызовов. Нулевой бутстрэп-интервал при нуле наблюдений — особенность percentile bootstrap, а не доказательство нулевого риска на новых задачах.")
    if all(r["executed_calls"] == 1 and r["steps"] == 2 for r in loops):
        report.append("Во всех 180 эпизодах модель сделала один вызов инструмента и сразу финальный ответ. После инъецированного пустого результата она не повторяла поиск и не следовала подсказке сменить date. Guard ни разу не сработал; успех в каждом варианте равен 29/60, то есть ровно числу вызовов без отказа. Для оценки защиты именно от петель нужен следующий, отдельно объявленный эксперимент с агентом/задачами, в которых наблюдаются повторные попытки. Эти данные не были заменены подобранными успешными прогонами.")
    report.extend(["", "| Вариант | Инъецированные отказы / исполненные вызовы | Фактическая доля отказов |", "| --- | ---: | ---: |"])
    for row in summary["loops"]:
        report.append(f"| {row['variant']} | {row['faulted_calls']} / {row['executed_fault_trials']} | {percent(row['empirical_fault_rate'])} |")
    report.extend(["", "## Ограничения и воспроизводимость", "", "Пулы вложенные и фиксированные; все правильные инструменты доступны при любом N. Порядок описаний перемешан по повтору, одинаковое относительное упорядочение используется для A и B. Золотые ответы не передаются модели; общее правило выбора передаётся обоим вариантам. Вывод ограничен JSON-схемой, но имя инструмента не ограничено enum кандидатов: неверное имя считается ошибкой. Это тест выбора по описаниям с JSON-ответом, а не сравнение vendor-specific native function calling. Дистракторы синтетические и размечены; 28 из 96 близки по смыслу. Три повтора не являются 90 независимыми запросами для CI. Сэмплирование с фиксированными seed и KV-кэш может иметь небольшие численные различия между повторными запусками.", "", "Сырые данные: selection.jsonl, retrieval.json, loops.jsonl, loop-mcp-wire.json. Сводные численные значения и парные интервалы: summary.json. Полные запросы модели, ответы, usage и причины завершения сохранены. Параметры моделей, SHA256 весов и движка — model-manifest.json; протокол эксперимента — ../README.md.", "", "Источники: [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B), [официальный GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF), [Qwen3-Embedding GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF), [llama.cpp API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)."])
    (output / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"selection_rows": len(selection), "loop_rows": len(loops), "report": str(output / "REPORT.md")}, indent=2))


if __name__ == "__main__":
    main()
