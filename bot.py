import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any

from telegram import ReactionTypeEmoji, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger("coolify_webhook.bot")

CATEGORIES = {
    "deployment": "Deployments",
    "server": "Server",
    "database": "Database",
    "application": "Application",
    "service": "Service",
    "test": "Test",
}

EMOJI_BY_CATEGORY: dict[str, str] = {
    "deployment": "\U0001f680",
    "server": "\U0001f5a5",
    "database": "\U0001f4be",
    "application": "\U0001f4e6",
    "service": "\u2699\ufe0f",
    "test": "\U0001f4e2",
}


def event_category(event: str) -> str:
    prefix = event.split(":")[0] if ":" in event else event
    return prefix if prefix in CATEGORIES else ""


class NotificationBot:
    def __init__(self, token: str, chat_id: int, bindings_file: str = ""):
        self._token = token
        self._chat_id = chat_id
        self._bindings_file = Path(bindings_file) if bindings_file else Path("bindings.json")
        self._topics: dict[str, int] = {}
        self._application: Application | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._load_bindings()

    def _load_bindings(self) -> None:
        if self._bindings_file.exists():
            try:
                data = json.loads(self._bindings_file.read_text())
                self._chat_id = data.get("chat_id", self._chat_id)
                self._topics = data.get("topics", {})
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Failed to load bindings file: %s", exc)

    def _save_bindings(self) -> None:
        data = {"chat_id": self._chat_id, "topics": dict(sorted(self._topics.items()))}
        self._bindings_file.write_text(json.dumps(data, indent=2))

    def _thread_id_for_event(self, event: str) -> int | None:
        category = event_category(event)
        if category and category in self._topics:
            return self._topics[category]
        if "all" in self._topics:
            return self._topics["all"]
        return None

    def notify(self, event: str, success: bool, message: str, extra: dict[str, Any] | None = None) -> None:
        if not self._chat_id:
            return
        thread_id = self._thread_id_for_event(event)
        category = event_category(event)
        emoji = EMOJI_BY_CATEGORY.get(category, "\U0001f514")
        status_icon = "\u2705" if success else "\u274c"
        status_text = "Success" if success else "Failed"

        body = f"{emoji} <b>{event}</b>\n{status_icon} <b>{status_text}</b>\n{message}"

        if extra:
            extra_lines = []
            for key, value in extra.items():
                extra_lines.append(f"{key}: {value}")
            if extra_lines:
                body += "\n\n" + "\n".join(extra_lines)

        logger.info("Notifying chat_id=%s thread_id=%s for event=%s", self._chat_id, thread_id, event)
        if self._loop and self._application:
            kwargs: dict[str, Any] = {
                "chat_id": self._chat_id,
                "text": body,
                "parse_mode": ParseMode.HTML,
            }
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
            asyncio.run_coroutine_threadsafe(
                self._application.bot.send_message(**kwargs),
                self._loop,
            )

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Commands:\n"
            "/bind &lt;category&gt; \u2014 bind this topic to a category\n"
            "/unbind &lt;category&gt; \u2014 unbind\n"
            "/status \u2014 show topic bindings\n"
            "/categories \u2014 list available categories\n\n"
            "Categories: " + ", ".join(CATEGORIES) + ", all\n\n"
            "Send these commands from the topic you want to bind.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_bind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not context.args:
            await update.message.reply_text("Usage: /bind &lt;category&gt;", parse_mode=ParseMode.HTML)
            return

        thread_id = update.effective_message.message_thread_id
        if not thread_id:
            await update.message.reply_text(
                "This command must be sent from a forum topic, not the main chat.",
            )
            return

        category = context.args[0].lower()
        if category == "*":
            category = "all"
        valid = set(CATEGORIES) | {"all"}
        if category not in valid:
            await update.message.reply_text(
                f"Unknown category: <code>{category}</code>\n"
                f"Available: {', '.join(sorted(valid))}",
                parse_mode=ParseMode.HTML,
            )
            return

        self._topics[category] = thread_id
        self._save_bindings()
        label = CATEGORIES.get(category, "All")
        await update.message.set_reaction([ReactionTypeEmoji(emoji="\U0001f44d")])
        await update.message.reply_text(
            f"\u2705 Topic <code>{thread_id}</code> bound to <b>{label}</b>.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_unbind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /unbind &lt;category&gt;", parse_mode=ParseMode.HTML)
            return

        category = context.args[0].lower()
        if category == "*":
            category = "all"

        if category in self._topics:
            del self._topics[category]
            self._save_bindings()
            label = CATEGORIES.get(category, "All")
            await update.message.reply_text(f"\u2705 Unbound <b>{label}</b>.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("No binding for that category.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._topics:
            await update.message.reply_text("No topic bindings configured.")
            return
        lines = [f"Chat: <code>{self._chat_id}</code>", ""]
        for category in sorted(self._topics):
            label = CATEGORIES.get(category, "All")
            thread_id = self._topics[category]
            emoji = EMOJI_BY_CATEGORY.get(category, "")
            lines.append(f"{emoji} <b>{label}</b> \u2192 topic <code>{thread_id}</code>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def _cmd_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        lines = ["Available categories:"]
        for key, label in CATEGORIES.items():
            emoji = EMOJI_BY_CATEGORY.get(key, "")
            lines.append(f"{emoji} <code>{key}</code> \u2014 {label}")
        lines.append(f"\U0001f310 <code>all</code> \u2014 All events")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def _run_bot(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._application = Application.builder().token(self._token).build()
        self._application.add_handler(CommandHandler("start", self._cmd_start))
        self._application.add_handler(CommandHandler("bind", self._cmd_bind))
        self._application.add_handler(CommandHandler("unbind", self._cmd_unbind))
        self._application.add_handler(CommandHandler("status", self._cmd_status))
        self._application.add_handler(CommandHandler("categories", self._cmd_categories))

        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()
        logger.info("Telegram bot started")
        await asyncio.Event().wait()

    def start(self) -> None:
        if not self._token:
            return

        def _thread_target() -> None:
            asyncio.run(self._run_bot())

        self._thread = threading.Thread(target=_thread_target, daemon=True, name="tg-bot")
        self._thread.start()

    def stop(self) -> None:
        if self._application and self._loop:
            async def _shutdown() -> None:
                if self._application:
                    await self._application.updater.stop()
                    await self._application.stop()
                    await self._application.shutdown()

            asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
