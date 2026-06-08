import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from telegram import Update
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
    def __init__(self, token: str, bindings_file: str = ""):
        self._token = token
        self._bindings_file = Path(bindings_file) if bindings_file else Path("bindings.json")
        self._bindings: dict[str, set[int]] = {}
        self._application: Application | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._load_bindings()

    def _load_bindings(self) -> None:
        if self._bindings_file.exists():
            try:
                data = json.loads(self._bindings_file.read_text())
                self._bindings = {k: set(v) for k, v in data.items()}
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Failed to load bindings file: %s", exc)
                self._bindings = {}

    def _save_bindings(self) -> None:
        data = {k: sorted(v) for k, v in self._bindings.items() if v}
        self._bindings_file.write_text(json.dumps(data, indent=2))

    def _get_chats_for_event(self, event: str) -> set[int]:
        category = event_category(event)
        chats: set[int] = set()
        if category and category in self._bindings:
            chats.update(self._bindings[category])
        if "all" in self._bindings:
            chats.update(self._bindings["all"])
        return chats

    def notify(self, event: str, success: bool, message: str, extra: dict[str, Any] | None = None) -> None:
        chats = self._get_chats_for_event(event)
        if not chats:
            return
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

        logger.info("Notifying %d chat(s) for event=%s", len(chats), event)
        for chat_id in chats:
            if self._loop and self._application:
                asyncio.run_coroutine_threadsafe(
                    self._application.bot.send_message(
                        chat_id=chat_id,
                        text=body,
                        parse_mode=ParseMode.HTML,
                    ),
                    self._loop,
                )

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"Chat ID: <code>{chat_id}</code>\n\n"
            "Commands:\n"
            "/bind &lt;category&gt; \u2014 subscribe to category\n"
            "/unbind &lt;category&gt; \u2014 unsubscribe\n"
            "/status \u2014 show current subscriptions for this chat\n"
            "/categories \u2014 list available categories\n\n"
            "Categories: " + ", ".join(CATEGORIES) + ", all",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_bind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not context.args:
            await update.message.reply_text("Usage: /bind &lt;category&gt;", parse_mode=ParseMode.HTML)
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
        chat_id = update.effective_chat.id
        self._bindings.setdefault(category, set()).add(chat_id)
        self._save_bindings()
        label = CATEGORIES.get(category, "All")
        await update.message.reply_text(f"\u2705 Subscribed to <b>{label}</b>.", parse_mode=ParseMode.HTML)

    async def _cmd_unbind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not context.args:
            await update.message.reply_text("Usage: /unbind &lt;category&gt;", parse_mode=ParseMode.HTML)
            return
        category = context.args[0].lower()
        if category == "*":
            category = "all"
        chat_id = update.effective_chat.id
        if category in self._bindings and chat_id in self._bindings[category]:
            self._bindings[category].discard(chat_id)
            if not self._bindings[category]:
                del self._bindings[category]
            self._save_bindings()
            label = CATEGORIES.get(category, "All")
            await update.message.reply_text(f"\u2705 Unsubscribed from <b>{label}</b>.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("You are not subscribed to that category.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        subs = []
        for category in sorted(self._bindings):
            if chat_id in self._bindings[category]:
                label = CATEGORIES.get(category, "All")
                subs.append(f"\u2022 {label}")
        if subs:
            await update.message.reply_text(
                "Your subscriptions:\n" + "\n".join(subs),
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text("No active subscriptions. Use /bind to subscribe.")

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
