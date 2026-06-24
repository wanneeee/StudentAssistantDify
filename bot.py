"""
Telegram bot for NTU Student Assistant.
Forwards messages to Dify Chatflow and returns the response.

Each Telegram user gets their own Dify conversation_id so context is maintained.
"""

import os
import httpx
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELE_BOT_TOKEN", "")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")

# Stores conversation_id per Telegram user so Dify remembers context
# { telegram_user_id: dify_conversation_id }
user_conversations: dict[int, str] = {}


# ── Dify chat helper ──────────────────────────────────────────────────────────

def ask_dify(user_id: int, message: str) -> str:
    """Send a message to Dify Chatflow and return the reply text."""
    conversation_id = user_conversations.get(user_id, "")

    payload = {
        "inputs": {},
        "query": message,
        "response_mode": "blocking",
        "conversation_id": conversation_id,
        "user": str(user_id),
    }

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{DIFY_BASE_URL}/chat-messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            # Save conversation_id for follow-up messages
            new_conv_id = data.get("conversation_id", "")
            if new_conv_id:
                user_conversations[user_id] = new_conv_id

            return data.get("answer", "Sorry, I didn't get a response.")

    except httpx.HTTPStatusError as e:
        return f"Dify error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Could not reach Dify: {str(e)}"


# ── Telegram command handlers ─────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Clear any previous conversation so this is a fresh start
    user_conversations.pop(user.id, None)

    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📅 My Timetable"), KeyboardButton("➕ Add Course")],
            [KeyboardButton("✅ My Todos"), KeyboardButton("➕ Add Todo")],
            [KeyboardButton("💡 Suggest Revision Plan")],
        ],
        resize_keyboard=True,
    )

    await update.message.reply_text(
        f"Hi {user.first_name}! 👋 I'm your NTU Student Assistant.\n\n"
        "I can help you manage your timetable and todos, and suggest a daily revision schedule.\n\n"
        "Use the buttons below or just type naturally!",
        reply_markup=keyboard,
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear conversation history with Dify."""
    user_conversations.pop(update.effective_user.id, None)
    await update.message.reply_text("Conversation reset. Starting fresh! 🔄")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Here's what you can do:\n\n"
        "📅 *My Timetable* — view your weekly schedule\n"
        "➕ *Add Course* — add a course by course code + index\n"
        "✅ *My Todos* — view pending tasks\n"
        "➕ *Add Todo* — add a new task\n"
        "💡 *Suggest Revision Plan* — get an AI-generated study plan\n\n"
        "Or just type anything naturally and I'll understand!\n\n"
        "/reset — start a new conversation\n"
        "/help — show this message",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all text messages (including keyboard buttons) to Dify."""
    user_id = update.effective_user.id
    text = update.message.text

    # Show typing indicator while waiting for Dify
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    reply = ask_dify(user_id, text)
    await update.message.reply_text(reply)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELE_BOT_TOKEN not set in .env")
    if not DIFY_API_KEY:
        raise ValueError("DIFY_API_KEY not set in .env")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running... Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
