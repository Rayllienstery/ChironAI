"""
OpenAI-compatible RAG proxy for Zed (and other clients).
Accepts POST /v1/chat/completions, runs RAG (embed -> Qdrant), calls Ollama /api/chat,
returns OpenAI-format response. Listen on 0.0.0.0:8080 for remote access (e.g. Zed on Mac).

Usage:
  On PC: python rag_proxy.py  (after starting Ollama and Qdrant)
  On Mac Zed: OpenAI API Compatible -> API URL: http://<PC_IP>:8080, model: rag-ollama
  Windows firewall: allow inbound on port 8080.
"""

import json
import logging
import uuid

import requests
from flask import Flask, Response, jsonify, request
from rag_client import search_rag

app = Flask(__name__)

# Simple stdout logging so it's easy to inspect RAG traffic from the console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
RAG_MODEL_ID = "rag-ollama"
OLLAMA_MODEL = "danielsheep/gpt-oss-20b-unsloth:UD-Q6_K_XL"

# Models that support reasoning levels (GPT-OSS family)
REASONING_LEVEL_MODELS = ["gpt-oss", "gpt-oss-20b", "gpt-oss-120b"]

# How many characters of context/answer to log (to avoid flooding logs).
RAG_LOG_PREVIEW_CHARS = 800

RAG_SYSTEM_PREFIX = """
Ты — senior Swift/iOS инженер. Давай технически точные ответы и корректный код в рамках указанной архитектуры.

---------- СТРУКТУРА ОТВЕТА (соблюдай порядок) ----------
1. КРАТКИЙ ОТВЕТ — есть ли подтверждение в RAG; какая архитектура (или "без архитектуры").
2. ДАННЫЕ ИЗ RAG — конкретные API, сигнатуры (если есть). Если найден релевантный чанк — обязательно использовать и сослаться на него.
3. РЕАЛИЗАЦИЯ — код в рамках архитектуры, DocC на каждую функцию/метод, комментарии на английском. Если пользователь явно просит "без кода", "только объяснение", "ответ без кода" — не давать код, даже в примерах; только текстовое объяснение механики.
4. ИТОГ — краткий технический вывод.

Если пользователь просит «только код», «просто код», «код без пояснений» — можно опустить КРАТКИЙ ОТВЕТ и ИТОГ; дать только релевантные ДАННЫЕ ИЗ RAG (если есть) и РЕАЛИЗАЦИЮ одним цельным блоком кода без обрывков («... остальное как раньше» запрещено). Код — один полный, копируемый фрагмент; пояснения внутри блока кода не писать.

---------- ИСТОЧНИК ИСТИНЫ (RAG) ----------
Ниже в блоке "========= RAG КОНТЕКСТ =========" — фрагменты документации Apple (могут содержать URL, заголовки, параграфы, версии iOS/Swift). Каждое утверждение, взятое из RAG, должно ссылаться на номер чанка или URL, если они присутствуют в контексте (например: «по фрагменту 2», «[URL из контекста]»).
• В блоке «ДАННЫЕ ИЗ RAG» — только то, что прямо есть в тексте фрагментов; не интерпретировать сверх текста; не добавлять детали (сигнатуры, ключи plist, имена методов), которых нет в RAG. ОБЯЗАТЕЛЬНО: если в RAG найден релевантный чанк (особенно с высоким score, например >0.7, или с подходящими версиями iOS/Swift) — использовать его и явно сослаться на него в блоке «ДАННЫЕ ИЗ RAG» с указанием номера чанка или URL; не игнорировать найденные фрагменты. Если найден чанк про конкретный API/механизм из вопроса — начать ответ с него, а не с общих рассуждений.
• Приоритизация API: если в RAG есть несколько вариантов API для одной задачи (например старый и новый способ), использовать самый новый из доступных (по версии iOS/Swift в метаданных чанка). Если пользователь явно просит «последнюю версию» или «iOS 18+» — искать в RAG фрагменты с соответствующими версиями и использовать только их.
• В блоке «РЕАЛИЗАЦИЯ» — допускается инженерная реализация; но каждый факт (API, ключ, паттерн), не подтверждённый RAG, должен быть явно помечен как интерпретация (например: «интерпретация: …», «не из RAG: …»). Если в RAG нет точного названия API (например `Observation.observe(...)`) — не выдумывать сигнатуру; написать «В фрагментах не найдено» и использовать только известные API (например `withObservationTracking`, `updateProperties()`). Иначе модель будет выдавать выдуманные детали за факты из документации.
• Никогда не смешивать RAG-факты и свои выводы в одном утверждении.
Если в RAG нет подходящих фрагментов по вопросу — в ДАННЫЕ ИЗ RAG написать коротко: «В RAG нет релевантных фрагментов»; в РЕАЛИЗАЦИИ помечать неподтверждённые детали как интерпретация; не придумывать сигнатуры/имена из RAG.
Если в RAG есть только устаревший API (например старый lifecycle), а пользователь просит современный — в КРАТКОМ ОТВЕТЕ сказать об этом; по RAG дать вариант из документации, современный пометить как интерпретация.
Если в промпте указано, что релевантность фрагментов низкая — сначала написать "Мало подходящих фрагментов", затем дать ответ с явной оговоркой.

---------- АРХИТЕКТУРА ----------
Выбор: 1) если пользователь явно указал архитектуру (MVVM, Clean, MVC, TCA, "без архитектуры") — использовать строго её. 2) если не указал — по умолчанию «без архитектуры», прямолинейный код (модель не знает структуру проекта, пока пользователь не передал контекст; иначе возможна самодеятельность).
Паттерны: MVVM → ViewModel; Clean → Entity, Repository, UseCase; Clean+MVVM → VC→VM→UseCase→Repository→Entity; MVC/TCA — по названию.
Платформа: iOS→UIKit, macOS→AppKit; фреймворк по запросу (SwiftUI/UIKit/AppKit), не смешивать без запроса.
Clean: зависимости внутрь; UI не знает Repository; UseCase не зависит от UI. MVVM: VM — состояние и логика; VC — viewModel; VM не знает UIKit. Clean+MVVM: VM→UseCase→Repository→Entity; запрещено VM→Repository, VC→Repository, UseCase мутирует VM.

---------- ЗАПРЕЩЕНО ----------
Смешивать паттерны; добавлять слои без запроса; выдумывать API (в т.ч. несуществующие сигнатуры типа Observation.observe(...) — если в RAG нет точного названия, использовать только известные API или явно пометить «интерпретация»); выдавать догадки за подтверждённые; force unwrap (!), force try (try!); implicitly unwrapped optional (Type!) в свойствах и в вызовах (в т.ч. URL(string: "...")! — использовать guard let url = URL(string: "...") else { return }); игнорировать ошибки. Запрещены в коде: "TODO", "<#...#>", "dummy"; разрешены конкретные значения (реальный URL, реальные строки), если примеру нужны данные — не оставлять некомпилируемые дыры. Опционалы — guard/if let; ошибки — do/catch.
Обновлять UI до появления view (UIKit: до viewDidLoad/viewWillLayoutSubviews; SwiftUI: не полагаться на body до появления View там, где это может вызвать краш). Оставлять подписки (Combine, наблюдатели) или async-задачи без отмены при уходе с экрана/deinit.

---------- КОД ----------
Компилируемый Swift; без фиктивных свойств/методов; явная инициализация и подписки (не только lazy/closure); UI на main thread, @MainActor где нужно; @available при версионных API. DocC (///) на каждую функцию/метод — строго на английском; все inline-комментарии в коде — строго на английском. Никогда не писать DocC или комментарии в коде на русском.

iOS-специфика: обновление UI только после появления view (не в init); отмена подписок/наблюдателей и async-задач в deinit или при исчезновении экрана. Для интерактивных элементов по умолчанию добавлять accessibilityLabel/accessibilityHint, если пользователь не просит «без accessibility». Строки для UI — через локализацию (String(localized:) или NSLocalizedString), не хардкод пользовательских строк без пометки «интерпретация». При использовании API из RAG указывать минимальную версию iOS (@available(iOS X.Y, *) или комментарий). Стиль — Swift API Design Guidelines. Если запрос можно закрыть одним коротким примером — не раздувать ответ; при нескольких вариантах — один полный пример, остальные кратко. Если пользователь просит «с тестами», «unit test» — давать XCTest, без сторонних фреймворков, если не указано иное.

---------- САМОПРОВЕРКА (принципы) ----------
Перед выводом кода пройти по принципам, а не по списку кейсов. Самопроверка модульная: всегда — блок Always; если задача про конкуренцию/сеть/очередь — добавить 2–5; если задача про SwiftUI observation — добавить 10; если задача про UIKit + @Observable (iOS 18+) — добавить 11.

Always (всегда): компиляция (типы, API реальные, замыкания без retain cycle); UI на main (@MainActor, DispatchQueue.main, receive(on: .main)); без force unwrap (!) и force try (try!); @available при версионных API; без выдуманных API.

Если конкуренция/сеть/очередь (Combine, URLSession, очередь запросов, один запрос одновременно):
2) DATA RACE — общее состояние (очередь, флаг, свойства @Observable класса) только через одну DispatchQueue или lock или один актор; колбэки из sink/URLSession/Task.detached тоже через эту очередь или receive(on:) или MainActor. @Observable класс не thread-safe: доступ к его свойствам из разных акторов = race.
3) ОЧЕРЕДЬ И ОДИН ЗАПРОС — запрос реально попадает в очередь (send/append); один потребитель, следующая задача только после завершения текущей.
4) ПРИВЯЗКА ЗАПРОС–ОТВЕТ — при одном общем sink нужна явная привязка (очередь пар request+completion или один поток на запрос).
5) ПОДПИСКИ — кто запускает поток (send/scheduleNext)? При одном активном запросе — одна подписка (currentCancellable), не растущий Set.

Если SwiftUI observation (состояние для View):
10) @OBSERVABLE — тип состояния View/ViewModel @Observable, не ObservableObject/@Published без запроса.
Если UIKit + @Observable (iOS 18+ с UIObservationTrackingEnabled):
11) @OBSERVABLE + UI — обновление UI должно быть в updateProperties() или через явный переход на MainActor; доступ к @Observable свойствам только на одном акторе (обычно MainActor); Task.detached + доступ к @Observable = race.

(Детали принципов 2–5 и 6–10 — ниже, для справки.)

1) КОМПИЛЯЦИЯ (Always). Принцип: каждый символ (тип, метод, свойство) должен существовать и совпадать по типам; замыкания должны корректно захватывать и не создавать retain cycle. Проверка: мысленно пройти по цепочке вызовов — от входа (например fetch(url)) до выхода (subject.send, completion) — и убедиться, что типы сходятся, API реальные, подписка реально создаётся и хранится.

2) DATA RACE. Принцип: общее изменяемое состояние (очередь, флаг isProcessing, счётчик, массив запросов, свойства @Observable класса) не должно читаться и писаться из разных потоков/акторов без синхронизации. URLSession и многие Combine-издатели вызывают колбэки на фоновых очередях; код, вызываемый пользователем (например fetch), может выполняться на main или другой очереди. @Observable класс не thread-safe: доступ к его свойствам (например model.value) из разных акторов (например Task.detached меняет, а viewWillLayoutSubviews читает на MainActor) = data race. Поэтому: любое место, где ты меняешь или читаешь общее состояние (queue.append, isProcessing = true, scheduleNext(), subject.send(...), model.value = ...), должно выполняться на одной и той же сериализующей очереди (один DispatchQueue) или под одним lock, или все изменения @Observable свойств на одном акторе (обычно MainActor). Если колбэк из sink/receiveCompletion меняет это состояние — он тоже должен делать это через ту же очередь (например через dispatchQueue.async { ... } или receive(on: dispatchQueue) перед sink).

3) КАК РАБОТАЕТ ОЧЕРЕДЬ И ОДИН ЗАПРОС. Принцип: «ставить в очередь» значит реально вызывать код, который добавляет задачу (например subject.send(request) или queue.append(...)); «только один запрос одновременно» значит один потребитель (одна подписка на subject или один цикл scheduleNext), который берёт следующую задачу только после завершения текущей. Проверка: есть ли в коде вызов, который передаёт входящий запрос в очередь (send/append)? Кто и когда вызывает этот вызов? Если запрос нигде не send’ится — он никогда не выполнится.

4) ПРИВЯЗКА ЗАПРОС–ОТВЕТ. Принцип: если несколько запросов обрабатываются одним потоком результатов (один flatMap, один sink), каждый результат приходит в общий receiveValue — тогда нельзя просто вызвать «текущий» completion: нужно явно сопоставить результат с запросом (очередь пар (request, completion), при получении результата брать первую пару и вызывать её completion; или один поток на запрос, без общего sink). Проверка: при N вызовах enqueue и одном общем sink — как именно первый результат попадает в первый completion, второй во второй? Если механизма нет (очередь пар, идентификатор запроса) — ответы перепутаются.

5) ПОДПИСКИ И ЖИЗНЕЙНЫЙ ЦИКЛ. Принцип: подписка (sink, subscribe) должна быть создана и сохранена (store(in:)), и тот, кто создаёт подписку, должен быть тем, кто реально запускает цепочку (например init() подписывается на subject и вызывает scheduleNext при старте; или первый вызов fetch добавляет в очередь и вызывает scheduleNext). Если подписка создаётся в методе, который вызывается при каждом запросе, но запрос в subject не отправляется — цепочка не получает входных данных. Если в любой момент активна только одна подписка (один запрос одновременно) — хранить одну подписку (например currentCancellable: AnyCancellable?), а не накапливать в Set<AnyCancellable>: иначе подписки растут без ограничений. Проверка: кто первый раз «запускает» поток (send в subject или вызов scheduleNext)? Вызывается ли это при каждом новом запросе? Если один активный запрос — одна подписка в переменной или Set не растёт?

Итог: всегда — Always; при конкуренции/сети/очереди — добавить 2–5; при SwiftUI observation — добавить 10; при UIKit + @Observable (iOS 18+) — добавить 11.

---------- Swift 5.10 / 6.0 и iOS/macOS (принципы) ----------
Целевая среда: Swift 5.10+ / 6.0+, iOS/macOS. Принципы, не кейсы.

6) СТРОГАЯ КОНКУРЕНЦИЯ (Swift 6). Принцип: компилятор проверяет изоляцию; данные, пересекающие границы изоляции (из фоновой задачи в @MainActor, из одного actor в другой), должны быть Sendable или передаваться через await/async. Класс с изменяемым состоянием по умолчанию не Sendable; @Observable класс не Sendable; struct с только Sendable полями — Sendable; actor изолирует своё состояние. Доступ к свойствам @Observable класса из Task.detached (не-MainActor) при том что контроллер читает их на MainActor — нарушение строгой конкуренции Swift 6. Проверка: если код помечен как Swift 6 или «concurrency-safe» — нет ли передачи не-Sendable типа (в т.ч. @Observable класса) через границу изоляции без обёртки (Task { }, MainActor.assumeIsolated и т.д.)? Если свойство @Observable меняется из Task.detached или другого не-MainActor контекста, а читается на MainActor — это race.

7) UI ТОЛЬКО НА MAIN. Принцип: UIKit, AppKit и SwiftUI требуют обновления UI на main thread. В Swift 5.10/6 тип с @MainActor изолирован на main; вызов из фонового колбэка (URLSession, Combine на фоне) в UI — только через DispatchQueue.main.async { } или receive(on: DispatchQueue.main) или await MainActor.run { } / вызов @MainActor функции из async. Обновление UI-свойств (label.text = ..., view.isHidden = ...) должно происходить только в методах, которые гарантированно вызываются на main (например updateProperties(), viewWillLayoutSubviews()), или через явный переход на MainActor (await MainActor.run { ... }). Проверка: где обновляются UI-свойства (текст, скрытие, список)? Все ли эти пути выполняются на main? Если label.text обновляется в произвольном месте (например в замыкании Task.detached) без перехода на main — это нарушение.

8) SENDABLE И ГРАНИЦЫ ИЗОЛЯЦИИ. Принцип: замыкание, убегающее в другой поток или в actor, не должно захватывать изменяемые не-Sendable ссылки (например класс с var, @Observable класс). @Observable класс не Sendable; доступ к его свойствам из Task.detached или другого не-MainActor контекста при том что контроллер читает их на MainActor = нарушение изоляции. Либо захватывать только Sendable (значения, actor), либо отправлять работу на нужную изоляцию (MainActor, свой actor) и там читать/писать. Проверка: что захватывает [weak self] в completion/sink/Task.detached? Используется ли self (или его свойства, в т.ч. @Observable модель) после асинхронного вызова без перехода на правильную изоляцию? Если Task.detached обращается к model.value без MainActor — это нарушение.

9) ACTOR ДЛЯ ОБЩЕГО СОСТОЯНИЯ. Принцип: в Swift 5.10/6 общее изменяемое состояние можно изолировать в actor — тогда все обращения к нему сериализованы компилятором, гонки по этому состоянию нет. Если код на async/await — предпочитать actor вместо ручного DispatchQueue для очередей/флагов; если код на Combine/callbacks — по-прежнему одна DispatchQueue или вызов в actor через Task { await actor.method() } из колбэка. Проверка: есть ли общее состояние (очередь, флаг)? Если да — либо один DispatchQueue для всех доступов, либо actor.

10) @OBSERVABLE И SWIFTUI. Принцип: в Swift 5.9+ для SwiftUI-состояния используется @Observable; не подменять на ObservableObject/@Published без запроса. @Observable не требует явного Sendable для типов, используемых только на main в View/ViewModel. Проверка: если в запросе SwiftUI и современный Swift — тип состояния View/ViewModel @Observable?

11) @OBSERVABLE И UIKIT (iOS 18+). Принцип: при UIObservationTrackingEnabled система автоматически отслеживает чтение @Observable свойств в методах жизненного цикла (viewWillLayoutSubviews(), updateProperties() и т.д.) и перезапускает эти методы при изменении прочитанных свойств. НО: автоматическое обновление работает надёжно только если чтение и запись происходят на одном акторе (MainActor). Если в viewWillLayoutSubviews() (MainActor) читается model.value, а затем model.value меняется из Task.detached (не-MainActor) — observation engine не получает уведомление в thread-safe способе, и viewWillLayoutSubviews() не перезапускается автоматически. Если model.value меняется из Task (на MainActor) — автоматическое обновление работает: система перезапустит viewWillLayoutSubviews() и label обновится автоматически. @Observable класс не thread-safe: доступ к его свойствам из Task.detached (не-MainActor) при том что контроллер читает их на MainActor = data race и нарушение строгой конкуренции Swift 6. Все изменения @Observable свойств должны быть на MainActor (использовать Task вместо Task.detached или явно await MainActor.run), тогда автоматическое обновление UI работает. Проверка: если код использует @Observable + UIKit + Task.detached — нет ли доступа к свойствам модели из detached контекста? Если да — это race и автоматическое обновление не сработает; нужно Task на MainActor или await MainActor.run. Правильный паттерн: Task { for i in 1...5 { try? await Task.sleep(...); self.model.value = i } } — все на MainActor, автоматическое обновление работает.

Итог по 6–11: код для Swift 5.10/6 и iOS/macOS должен соблюдать изоляцию (UI на main, Sendable на границах), использовать actor или одну очередь для общего состояния, при необходимости @Observable для SwiftUI; при UIKit + @Observable (iOS 18+) с UIObservationTrackingEnabled — автоматическое обновление UI работает только если чтение и запись @Observable свойств происходят на одном акторе (MainActor); если запись из Task.detached (не-MainActor) — observation engine не сработает надёжно и UI не обновится автоматически; все изменения модели должны быть на MainActor.

---------- ЯЗЫК ----------
Язык ответа = язык вопроса. Код и API — английский. Тон — инженерный, без маркетинга.

"""

RAG_SYSTEM_SUFFIX = """
=================================
"""

# Limits for how much RAG context we feed into the model.
RAG_CONTEXT_CHUNK_CHARS = 1000
# 20B-модели плохо держат очень длинный контекст; 6–7k символов обычно стабильнее, чем 10k+.
RAG_CONTEXT_TOTAL_CHARS = 7_000
# Меньший topK даёт меньше шума и более детерминированное поведение.
RAG_TOP_K = 4  # how many candidates we ask Qdrant for per vector search
# If best retrieval score is below this, we do not treat RAG as confirmed; add caveat to prompt.
RAG_CONFIDENCE_THRESHOLD = 0.75


def _last_user_content(messages: list) -> str:
    """Extract text from the last user message (content may be string or array of parts)."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                return " ".join(parts).strip()
            return ""
    return ""


def _determine_reasoning_level(user_message: str, context_length: int, model_name: str) -> str:
    """
    Automatically determine reasoning level for GPT-OSS models based on query type and length.
    Returns: "low", "medium", or "high"
    
    Priority logic:
    1. Explicit user request (reasoning:high/low/medium)
    2. First character "!" -> high (quick override)
    3. Short queries (< 100 tokens) -> low (fast autocomplete-like)
    4. Complex reasoning keywords -> high
    5. Default -> medium (balanced)
    """
    # Check if model supports reasoning levels
    if not any(model_keyword in model_name.lower() for model_keyword in REASONING_LEVEL_MODELS):
        return None  # Not a reasoning-level model
    
    msg_lower = user_message.lower()
    msg_stripped = user_message.strip()
    
    # 1. Explicit user request (highest priority)
    if "reasoning:high" in msg_lower or "reasoning: high" in msg_lower:
        return "high"
    if "reasoning:low" in msg_lower or "reasoning: low" in msg_lower:
        return "low"
    if "reasoning:medium" in msg_lower or "reasoning: medium" in msg_lower:
        return "medium"
    
    # 2. First character "!" -> high (quick override)
    if msg_stripped and msg_stripped[0] == "!":
        return "high"
    
    # 3. Short queries -> low (fast autocomplete)
    if context_length < 100:
        return "low"
    
    # 4. Complex reasoning tasks -> high
    complex_keywords = [
        "refactor", "optimize", "debug", "analyze", "design", "architecture",
        "redesign", "restructure", "improve performance", "fix memory leak",
        "concurrency", "race condition", "thread safety", "actor isolation"
    ]
    if any(kw in msg_lower for kw in complex_keywords):
        return "high"
    
    # 5. Default -> medium (balanced for most tasks)
    return "medium"


def _framework_filter(query: str, results: list) -> list:
    """
    When the user clearly asks for one UI framework, keep only chunks from that framework
    so the model does not mix UIKit and SwiftUI. Uses url/path to detect UIKit vs SwiftUI docs.
    """
    q = query.lower()
    uikit_asked = "uikit" in q and "swiftui" not in q
    swiftui_asked = "swiftui" in q and "uikit" not in q
    if not uikit_asked and not swiftui_asked:
        return results
    needle = "uikit" if uikit_asked else "swiftui"
    filtered = []
    for h in results:
        payload = h.get("payload") or {}
        url = (payload.get("url") or "").lower()
        path = (payload.get("path") or "").lower()
        if needle in url or needle in path:
            filtered.append(h)
    return filtered if filtered else results


def _build_rag_context(last_user_text: str) -> tuple[str, list[dict], float]:
    """
    Run RAG: search_rag (metadata-first filter, doc_type weighting, multi-chunk when needed) ->
    framework filter -> concatenate payload text.
    Returns: (context_text, chunks_info, max_score). max_score is used for confidence threshold.
    """
    if not last_user_text:
        return "", [], 0.0
    try:
        results = search_rag(last_user_text)
        if not results:
            return "", [], 0.0
        results = _framework_filter(last_user_text, results)
        max_score = max(h.get("score", 0.0) for h in results) if results else 0.0
        parts: list[str] = []
        chunks_info: list[dict] = []
        total = 0
        for idx, h in enumerate(results, start=1):
            if total >= RAG_CONTEXT_TOTAL_CHARS:
                break
            payload = h.get("payload") or {}
            txt = (payload.get("text") or "").strip()
            if not txt:
                continue
            snippet = txt[:RAG_CONTEXT_CHUNK_CHARS]
            remaining = RAG_CONTEXT_TOTAL_CHARS - total
            if remaining <= 0:
                break
            snippet = snippet[:remaining]
            if not snippet:
                continue
            parts.append(snippet)
            total += len(snippet) + 2

            score = h.get("score", 0.0)
            rerank_score = h.get("rerank_score")
            chunk_info = {
                "index": idx,
                "score": f"{score:.4f}" if score else "N/A",
                "rerank_score": f"{rerank_score:.4f}" if rerank_score else None,
                "url": payload.get("url") or "N/A",
                "source": payload.get("source") or "N/A",
                "path": payload.get("path") or "N/A",
                "doc_type": payload.get("doc_type") or "N/A",
                "ios_versions": payload.get("ios_versions") or [],
                "swift_versions": payload.get("swift_versions") or [],
                "text_length": len(snippet),
                "text_preview": snippet[:100] + "..."
                if len(snippet) > 100
                else snippet,
            }
            chunks_info.append(chunk_info)
        return "\n\n".join(parts), chunks_info, max_score
    except Exception as e:
        logging.error(f"RAG context build error: {e}")
        return "", [], 0.0


def _ollama_messages(
    openai_messages: list, 
    rag_context: str, 
    max_retrieval_score: float = 1.0,
    reasoning_level: str = None,
    model_name: str = None
) -> list:
    """
    Build message list for Ollama: one system message (RAG prompt + context) then OpenAI messages.
    If reasoning_level is provided and model supports it, adds reasoning level instruction.
    """
    if rag_context:
        doc_block = rag_context + RAG_SYSTEM_SUFFIX
        if max_retrieval_score < RAG_CONFIDENCE_THRESHOLD:
            doc_block += (
                "\nRetrieval confidence is low (best score < {:.2f}). "
                "State that the provided fragments may not be the best match; suggest rephrasing or give a short caveat.\n"
            ).format(RAG_CONFIDENCE_THRESHOLD)
    else:
        doc_block = (
            "В базе нет релевантных фрагментов по этому запросу. "
            "Это НЕ значит, что таких версий, API или фич не существует — только то, что локальная Apple-дока не вернула совпадений. "
            "Отвечай как обычный эксперт по Swift из своих знаний, дай законченный, структурированный ответ и явно заверши мысль.\n"
        ) + RAG_SYSTEM_SUFFIX
    
    # Add reasoning level instruction for GPT-OSS models
    reasoning_instruction = ""
    if reasoning_level and model_name:
        if any(model_keyword in model_name.lower() for model_keyword in REASONING_LEVEL_MODELS):
            reasoning_instruction = f"\n\nReasoning: {reasoning_level}\n"
    
    system_content = RAG_SYSTEM_PREFIX + reasoning_instruction + doc_block

    ollama_msgs = [{"role": "system", "content": system_content}]
    for m in openai_messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_msgs.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            if isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content if p.get("type") == "text"
                )
            else:
                text = content or ""
            ollama_msgs.append({"role": role, "content": text})
    return ollama_msgs


def _chat_ollama(messages: list, stream: bool) -> requests.Response:
    """POST to Ollama /api/chat; return raw response (stream=True means streamed)."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        # 3072 токена — компромисс: достаточно для работы с несколькими файлами
        # и больших ответов в Zed, но заметно быстрее, чем «безлимитный» 8k.
        # Для детерминированности отключаем стохастику: низкая temperature/top_p.
        "options": {
            "num_predict": 3072,
            "temperature": 0.0,
            "top_p": 0.1,
        },
    }
    return requests.post(
        OLLAMA_CHAT_URL,
        json=payload,
        stream=stream,
        timeout=300,
    )


INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RAG Proxy</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 36rem; margin: 2rem auto; padding: 0 1rem; }
    h1 { color: #0a0; }
    code { background: #eee; padding: 0.2em 0.4em; border-radius: 4px; }
    ul { line-height: 1.6; }
  </style>
</head>
<body>
  <h1>RAG Proxy запущен</h1>
  <p>OpenAI-совместимый прокси с RAG (Ollama + Qdrant) доступен по этому адресу.</p>
  <ul>
    <li><code>GET /v1/models</code> — список моделей</li>
    <li><code>POST /v1/chat/completions</code> — чат с RAG-контекстом</li>
  </ul>
  <p>В Zed: OpenAI API Compatible → API URL: <code>http://&lt;этот_хост&gt;:8080</code>, модель: <code>rag-ollama</code>.</p>
</body>
</html>
"""


@app.route("/")
def index():
    """Show that the proxy is running."""
    return Response(INDEX_HTML, mimetype="text/html; charset=utf-8")


@app.route("/v1", methods=["GET"])
def v1_root():
    """OpenAI-style API root so Zed (and similar clients) detect the endpoint."""
    return jsonify({"object": "api", "version": "v1"})


@app.route("/v1/models", methods=["GET"])
def list_models():
    """OpenAI-style model list so Zed can pick rag-ollama."""
    return jsonify(
        {
        "object": "list",
        "data": [
            {
                "id": RAG_MODEL_ID,
                "object": "model",
                "created": 0,
                "owned_by": "local",
            }
        ],
        }
    )


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """Accept OpenAI chat body; run RAG; call Ollama; return OpenAI-format response."""
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    messages = body.get("messages") or []
    stream = body.get("stream", False)
    model = body.get("model") or RAG_MODEL_ID
    
    # Check for explicit reasoning level in request (highest priority)
    explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
    
    if not messages:
        return jsonify({"error": "messages is required"}), 400

    last_user = _last_user_content(messages)
    
    # Determine reasoning level (explicit > automatic)
    reasoning_level = None
    if explicit_reasoning:
        reasoning_level = explicit_reasoning.lower()
        if reasoning_level not in ["low", "medium", "high"]:
            reasoning_level = "medium"  # Fallback to medium if invalid
    else:
        # Automatic determination based on query
        context_length = len(last_user.split())  # Approximate token count
        reasoning_level = _determine_reasoning_level(
            last_user, context_length, OLLAMA_MODEL
        )
    
    rag_context, chunks_info, max_score = _build_rag_context(last_user)
    ollama_messages = _ollama_messages(
        messages, 
        rag_context, 
        max_retrieval_score=max_score,
        reasoning_level=reasoning_level,
        model_name=OLLAMA_MODEL
    )

    # Log incoming RAG query with detailed chunk information.
    try:
        logging.info("=" * 80)
        logging.info(f"RAG REQUEST: model={model}, query={last_user!r}")
        if reasoning_level:
            logging.info(f"Reasoning level: {reasoning_level.upper()}")
        logging.info(
            f"Found {len(chunks_info)} chunks, total context: {len(rag_context)} chars"
        )

        if chunks_info:
            logging.info("-" * 80)
            for chunk in chunks_info:
                ios_versions_str = (
                    ", ".join(chunk["ios_versions"]) if chunk["ios_versions"] else "N/A"
                )
                swift_versions_str = (
                    ", ".join(chunk["swift_versions"])
                    if chunk["swift_versions"]
                    else "N/A"
                )
                rerank_str = (
                    f", rerank={chunk['rerank_score']}" if chunk["rerank_score"] else ""
                )

                logging.info(
                    f"[{chunk['index']}] score={chunk['score']}{rerank_str} | "
                    f"source={chunk['source']} | doc_type={chunk['doc_type']} | "
                    f"size={chunk['text_length']} chars"
                )
                logging.info(f"     URL: {chunk['url']}")
                logging.info(f"     Path: {chunk['path']}")
                if ios_versions_str != "N/A" or swift_versions_str != "N/A":
                    logging.info(
                        f"     Versions: iOS=[{ios_versions_str}], Swift=[{swift_versions_str}]"
                    )
                logging.info(f"     Preview: {chunk['text_preview']}")
                logging.info("-" * 80)
        else:
            logging.info("No relevant chunks found in RAG context")
        logging.info("=" * 80)
    except Exception as e:
        # Логирование не должно ломать основной поток.
        logging.error(f"RAG logging error: {e}")

    resp = _chat_ollama(ollama_messages, stream=stream)
    if resp.status_code != 200:
        return jsonify({"error": resp.text or "Ollama error"}), resp.status_code

    if stream:
        return _stream_response(resp, model)
    return _nonstream_response(resp, model)


def _nonstream_response(ollama_resp: requests.Response, model: str):
    """Parse Ollama JSON response and return OpenAI chat completion object."""
    data = ollama_resp.json()
    content = (data.get("message") or {}).get("content", "")

    # Логируем ответ модели (только превью).
    try:
        preview = content[:RAG_LOG_PREVIEW_CHARS]
        logging.info(
            "RAG response (non-stream): model=%s, content_chars=%d, preview=%r",
            model,
            len(content),
            preview,
        )
    except Exception:
        pass
    return jsonify(
        {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        }
    )


def _stream_response(ollama_resp: requests.Response, model: str):
    """Convert Ollama NDJSON stream to OpenAI SSE stream."""

    def generate():
        # Для стриминга собираем короткий превью-лог ответа.
        preview = ""
        oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        for line in ollama_resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content", "")
            done = obj.get("done", False)
            if content:
                if len(preview) < RAG_LOG_PREVIEW_CHARS:
                    # Пополняем превью до лимита символов.
                    space_left = RAG_LOG_PREVIEW_CHARS - len(preview)
                    preview += content[:space_left]
                chunk = {
                    "id": oid,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            if done:
                # Как только стрим закончился — логируем превью ответа.
                try:
                    logging.info(
                        "RAG response (stream): model=%s, preview_chars=%d, preview=%r",
                        model,
                        len(preview),
                        preview,
                    )
                except Exception:
                    pass
                final = {
                    "id": oid,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(final)}\n\n"
                break
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
