# Coolify webhook receiver

Минимальный Flask-сервис для изучения уведомлений от Coolify. Telegram-клиент
пока не используется: webhook проверяет общую структуру запроса и выводит весь
JSON payload в лог.

## Запуск

```bash
uv run python main.py
```

По умолчанию сервис слушает `0.0.0.0:8000`. Настройки можно изменить через
переменные окружения `HOST`, `PORT` и `LOG_LEVEL`.

Источник webhook определяется по содержимому JSON, а не по IP-адресу:
обязательны поля `success`, `event` и `message` указанных ниже типов.

Проверка:

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/webhooks/coolify \
  -H 'Content-Type: application/json' \
  -d '{
    "success": true,
    "event": "test",
    "message": "This is a test webhook notification from Coolify.",
    "url": "https://coolify.example.com"
  }'
```

В Coolify откройте `Notifications -> Webhook`, укажите публичный URL вида
`https://alerts.example.com/webhooks/coolify`, включите канал и нажмите
`Send Test Notification`.

## Docker

```bash
docker build -t tg-alerts .
docker run --rm -p 8000:8000 tg-alerts
```

Образ основан на Alpine Linux. Telegram-зависимости не устанавливаются в
контейнер, пока интеграция с Telegram не используется.

## Структура payload

Все события содержат:

- `success` (`boolean`) — успешное событие или ошибка/предупреждение;
- `event` (`string`) — машинный идентификатор события;
- `message` (`string`) — описание для человека.

Дополнительные поля зависят от `event`. Например, deployment содержит
`application_name`, `application_uuid`, `deployment_uuid`, `project`,
`environment` и `fqdn`; событие заполнения диска содержит `server_name`,
`disk_usage` и `threshold`.

Обработчик намеренно принимает неизвестные значения `event`: так новые события
Coolify не потеряются и их фактическую структуру будет видно в логах.

Документация:

- https://coolify.io/docs/knowledge-base/notifications/
- https://coolify.io/docs/knowledge-base/webhook-payloads
