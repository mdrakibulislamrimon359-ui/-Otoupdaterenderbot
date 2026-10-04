# ============================================================
# RJ TEAM BANGLADESH - PREMIUM AI BOT
# Owner: @RJteam1
# Gemini + Telegram + Firebase + Multi-Group Auto Post
# ============================================================

import os
import re
import json
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

from google import genai
from google.genai import types

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "RJteam1"
).strip().lstrip("@")

ADMIN_USER_ID = os.getenv(
    "ADMIN_USER_ID",
    ""
).strip()

TARGET_CHAT_ID = os.getenv(
    "TARGET_CHAT_ID",
    ""
).strip()

AUTOPOST_FILE = os.getenv(
    "AUTOPOST_FILE",
    "autoposts.json"
)

AUTOPOST_ENABLED = os.getenv(
    "AUTOPOST_ENABLED",
    "true"
).lower() in (
    "1",
    "true",
    "yes",
    "on",
)

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    ""
).strip()

AUTOPOST_FIREBASE_COLLECTION = os.getenv(
    "AUTOPOST_FIREBASE_COLLECTION",
    "rj_bot_config"
).strip()

AUTOPOST_FIREBASE_DOCUMENT = os.getenv(
    "AUTOPOST_FIREBASE_DOCUMENT",
    "autopost"
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).strip()

BD = ZoneInfo("Asia/Dhaka")

OWNER_USERNAME = "@RJteam1"
CHANNEL_USERNAME = "@RJteam123890"


# ============================================================
# GEMINI MODELS
# ============================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
]


SYSTEM_PROMPT = """
You are RJ Team Bangladesh Premium AI Bot.

Always answer naturally in Bangla unless the user explicitly
asks for another language.

Be friendly, helpful, concise and natural.

For funny messages, be playful.
For emotional messages, be empathetic.
For translation requests, translate accurately.

Never claim that an action was completed unless the bot
actually performed that action.
"""


ABOUT_TEXT = f"""
🤖 RJ TEAM BANGLADESH - PREMIUM AI BOT

✨ Gemini AI Assistant
📢 Multi Group Auto Post
🔥 Firebase Data Storage
🌐 Translation Support

👑 Owner: {OWNER_USERNAME}
📢 Channel: {CHANNEL_USERNAME}

🏴 RJ Team Bangladesh Hacker Community
"""


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# GLOBAL VARIABLES
# ============================================================

gemini_client = None
firebase_db = None

user_last_ai_reply = {}

autopost_data = {
    "enabled": AUTOPOST_ENABLED,
    "groups": {},
    "posts": [],
}


# ============================================================
# FIREBASE
# ============================================================

def init_firebase():

    global firebase_db

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.warning(
            "FIREBASE_SERVICE_ACCOUNT_JSON not found. "
            "Using local storage."
        )
        return

    try:

        service_account = json.loads(
            FIREBASE_SERVICE_ACCOUNT_JSON
        )

        if not firebase_admin._apps:

            cred = credentials.Certificate(
                service_account
            )

            firebase_admin.initialize_app(
                cred
            )

        firebase_db = firestore.client()

        logger.info(
            "Firebase connected successfully."
        )

    except Exception as e:

        firebase_db = None

        logger.exception(
            "Firebase initialization failed: %s",
            e
        )


def firebase_ref():

    if firebase_db is None:
        return None

    return (
        firebase_db
        .collection(
            AUTOPOST_FIREBASE_COLLECTION
        )
        .document(
            AUTOPOST_FIREBASE_DOCUMENT
        )
    )


def firebase_load():

    ref = firebase_ref()

    if ref is None:
        return None

    try:

        snap = ref.get()

        if not snap.exists:
            return None

        return snap.to_dict()

    except Exception as e:

        logger.error(
            "Firebase load error: %s",
            e
        )

        return None


def firebase_save(data):

    ref = firebase_ref()

    if ref is None:
        return False

    try:

        ref.set(data)

        return True

    except Exception as e:

        logger.error(
            "Firebase save error: %s",
            e
        )

        return False


# ============================================================
# LOCAL STORAGE
# ============================================================

def save_local():

    try:

        with open(
            AUTOPOST_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                autopost_data,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:

        logger.error(
            "Local save error: %s",
            e
        )


def save_autopost_data():

    save_local()

    firebase_save(
        autopost_data
    )


def load_local():

    if not os.path.exists(
        AUTOPOST_FILE
    ):
        return False

    try:

        with open(
            AUTOPOST_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(data, dict):

            autopost_data[
                "enabled"
            ] = data.get(
                "enabled",
                AUTOPOST_ENABLED
            )

            autopost_data[
                "groups"
            ] = data.get(
                "groups",
                {}
            )

            autopost_data[
                "posts"
            ] = data.get(
                "posts",
                []
            )

            return True

    except Exception as e:

        logger.error(
            "Local load error: %s",
            e
        )

    return False


def normalize_post_ids(
    save=True
):

    for index, post in enumerate(
        autopost_data["posts"],
        start=1
    ):

        post["id"] = index

    if save:
        save_autopost_data()


def load_autopost_data():

    remote = firebase_load()

    if remote:

        autopost_data[
            "enabled"
        ] = remote.get(
            "enabled",
            AUTOPOST_ENABLED
        )

        autopost_data[
            "groups"
        ] = remote.get(
            "groups",
            {}
        )

        autopost_data[
            "posts"
        ] = remote.get(
            "posts",
            []
        )

        save_local()

    else:

        load_local()

        if firebase_db is not None:
            firebase_save(
                autopost_data
            )

    normalize_post_ids(
        save=False
    )


# ============================================================
# HELPERS
# ============================================================

def now_bd():

    return datetime.now(BD)


def is_admin(update: Update):

    user = update.effective_user

    if not user:
        return False

    if (
        ADMIN_USER_ID
        and str(user.id)
        == ADMIN_USER_ID
    ):
        return True

    username = (
        user.username
        or ""
    ).lstrip("@").lower()

    return (
        username
        == ADMIN_USERNAME.lower()
    )


def owner_reply(text):

    text = text.strip()

    if text.startswith(
        "জি বস"
    ):
        return text

    return (
        "জি বস, "
        + text
    )


def parse_chat_id(value):

    try:
        return int(
            str(value).strip()
        )
    except Exception:
        return str(value).strip()


def parse_time(value):

    value = value.strip().upper()

    match = re.fullmatch(
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(AM|PM)?",
        value
    )

    if not match:
        return None

    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2)
        or "00"
    )

    ampm = match.group(3)

    if minute > 59:
        return None

    if ampm:

        if hour < 1 or hour > 12:
            return None

        if ampm == "AM":

            if hour == 12:
                hour = 0

        else:

            if hour != 12:
                hour += 12

    elif hour > 23:

        return None

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def extract_time_and_text(
    raw
):

    patterns = [

        r"^\s*"
        r"(\d{1,2}"
        r"(?::\d{2})?"
        r"\s*(?:AM|PM))"
        r"\s+(.+)$",

        r"^\s*"
        r"(\d{1,2}:\d{2})"
        r"\s+(.+)$",
    ]

    for pattern in patterns:

        match = re.match(
            pattern,
            raw,
            re.I | re.S
        )

        if match:

            parsed = parse_time(
                match.group(1)
            )

            if parsed:

                return (
                    parsed,
                    match.group(2).strip()
                )

    return None, None


def active_groups():

    return {
        key: value
        for key, value
        in autopost_data[
            "groups"
        ].items()
        if value.get(
            "active",
            True
        )
    }


# ============================================================
# GEMINI
# ============================================================

def init_gemini():

    global gemini_client

    if not GEMINI_API_KEY:

        logger.warning(
            "GEMINI_API_KEY missing."
        )

        return

    try:

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        logger.info(
            "Gemini initialized."
        )

    except Exception as e:

        logger.exception(
            "Gemini initialization failed: %s",
            e
        )


async def ask_gemini(
    prompt
):

    if gemini_client is None:

        return (
            "দুঃখিত, Gemini API "
            "configure করা নেই।"
        )

    last_error = None

    for model in GEMINI_MODELS:

        try:

            response = await asyncio.to_thread(

                gemini_client
                .models
                .generate_content,

                model=model,

                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=(
                                    SYSTEM_PROMPT
                                    + "\n\nUser:\n"
                                    + prompt
                                )
                            )
                        ],
                    )
                ],
            )

            answer = getattr(
                response,
                "text",
                None
            )

            if answer:

                return answer.strip()

        except Exception as e:

            last_error = e

            logger.warning(
                "Gemini model %s failed: %s",
                model,
                e
            )

            await asyncio.sleep(
                0.5
            )

    logger.error(
        "All Gemini models failed: %s",
        last_error
    )

    return (
        "দুঃখিত, এই মুহূর্তে "
        "AI response পাওয়া যাচ্ছে না। "
        "একটু পরে চেষ্টা করুন।"
    )


# ============================================================
# AUTO POST
# ============================================================

def add_group(
    chat_id,
    title=None
):

    key = str(chat_id)

    if key in autopost_data[
        "groups"
    ]:

        return False

    autopost_data[
        "groups"
    ][key] = {

        "chat_id": chat_id,

        "title": (
            title
            or key
        ),

        "active": True,
    }

    save_autopost_data()

    return True


def delete_group(
    chat_id
):

    key = str(chat_id)

    if key not in autopost_data[
        "groups"
    ]:

        return False

    del autopost_data[
        "groups"
    ][key]

    save_autopost_data()

    return True


def add_post(
    post_time,
    text="",
    photo_id=None,
    group_ids=None
):

    if group_ids is None:

        group_ids = list(
            autopost_data[
                "groups"
            ].keys()
        )

    post = {

        "id": (
            len(
                autopost_data[
                    "posts"
                ]
            )
            + 1
        ),

        "post_time": post_time,

        "text": text,

        "caption": text,

        "photo_id": photo_id,

        "group_ids": [
            str(x)
            for x in group_ids
        ],

        "enabled": True,
    }

    autopost_data[
        "posts"
    ].append(post)

    normalize_post_ids(
        save=False
    )

    save_autopost_data()

    return post


def delete_post(
    post_id
):

    try:

        post_id = int(
            post_id
        )

    except Exception:

        return False

    before = len(
        autopost_data[
            "posts"
        ]
    )

    autopost_data[
        "posts"
    ] = [

        post
        for post
        in autopost_data[
            "posts"
        ]

        if int(
            post.get(
                "id",
                0
            )
        ) != post_id
    ]

    changed = (
        len(
            autopost_data[
                "posts"
            ]
        )
        != before
    )

    if changed:

        normalize_post_ids(
            save=False
        )

        save_autopost_data()

    return changed


def clear_posts():

    autopost_data[
        "posts"
    ] = []

    save_autopost_data()


def format_post(
    post
):

    groups = (
        post.get(
            "group_ids"
        )
        or list(
            autopost_data[
                "groups"
            ].keys()
        )
    )

    status = (
        "ON"
        if post.get(
            "enabled",
            True
        )
        else "OFF"
    )

    text = (
        post.get(
            "text"
        )
        or post.get(
            "caption"
        )
        or ""
    )

    if len(text) > 120:

        text = (
            text[:120]
            + "..."
        )

    return (
        f"🆔 ID: {post.get('id')}\n"
        f"⏰ Time: {post.get('post_time')}\n"
        f"📌 Status: {status}\n"
        f"👥 Groups: {len(groups)}\n"
        f"📝 {text or '[Photo Post]'}"
    )


def list_posts_text():

    posts = autopost_data[
        "posts"
    ]

    if not posts:

        return (
            "📭 কোনো Auto Post নেই।"
        )

    lines = [

        "📢 AUTO POST LIST",

        (
            "Status: "
            + (
                "ON"
                if autopost_data[
                    "enabled"
                ]
                else "OFF"
            )
        ),

        "",
    ]

    for post in posts:

        lines.append(
            format_post(
                post
            )
        )

        lines.append("")

    return "\n".join(
        lines
    )


# ============================================================
# PUBLIC COMMANDS
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [

        [

            InlineKeyboardButton(
                "ℹ️ About",
                callback_data="about"
            ),

            InlineKeyboardButton(
                "🌐 Translate",
                callback_data="translate"
            ),
        ],

        [

            InlineKeyboardButton(
                "📢 Channel",
                url=(
                    "https://t.me/"
                    + CHANNEL_USERNAME
                    .lstrip("@")
                )
            ),

            InlineKeyboardButton(
                "👑 Owner",
                url=(
                    "https://t.me/"
                    + ADMIN_USERNAME
                )
            ),
        ],
    ]

    await update.message.reply_text(

        "🤖 RJ TEAM BANGLADESH "
        "PREMIUM AI BOT\n\n"
        "আপনার মেসেজ পাঠান, "
        "আমি AI দিয়ে উত্তর দেব।",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "📚 HELP\n\n"

        "/start - Start\n"
        "/help - Help\n"
        "/about - About\n"
        "/translate <text> - Translate\n\n"

        "👑 OWNER COMMANDS\n"

        "/autopost\n"
        "/addgroup\n"
        "/groups\n"
        "/delgroup <chat_id>\n"
        "/status\n"
        "/pausegroup <chat_id>\n"
        "/renamegroup <chat_id> <name>\n"
        "/broadcast <text>\n"
        "/list\n"
        "/delete <id>\n"
        "/clear\n"
        "/on\n"
        "/off\n"
        "/test\n"
        "/cancel\n\n"

        "Owner চাইলে SMS দিয়েও "
        "safe bot controls ব্যবহার করতে পারবেন।"
    )


async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        ABOUT_TEXT
    )


async def translate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = " ".join(
        context.args
    ).strip()

    if not text:

        await update.message.reply_text(
            "ব্যবহার:\n"
            "/translate Hello, how are you?"
        )

        return

    result = await ask_gemini(

        "Translate the following text "
        "into natural Bangla. "
        "Return only the translation:\n\n"
        + text
    )

    await update.message.reply_text(
        result
    )


async def translate_last_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    last = user_last_ai_reply.get(
        user_id
    )

    if not last:

        await update.message.reply_text(
            "আগের কোনো AI reply পাওয়া যায়নি।"
        )

        return

    result = await ask_gemini(

        "Translate the following text "
        "into natural Bangla. "
        "Return only the translation:\n\n"
        + last
    )

    await update.message.reply_text(
        result
    )


# ============================================================
# OWNER COMMANDS
# ============================================================

async def autopost_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    await update.message.reply_text(

        owner_reply(

            "Auto Post বর্তমানে "
            + (
                "ON"
                if autopost_data[
                    "enabled"
                ]
                else "OFF"
            )
            + ".\n\n"
            + list_posts_text()
        )
    )


async def addgroup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    chat = update.effective_chat

    if not chat:
        return

    title = (
        chat.title
        or chat.username
        or str(chat.id)
    )

    if add_group(
        chat.id,
        title
    ):

        msg = (
            "এই group Auto Post-এর জন্য "
            "যোগ করা হয়েছে: "
            + title
        )

    else:

        msg = (
            "এই group আগে থেকেই "
            "Auto Post list-এ আছে।"
        )

    await update.message.reply_text(
        owner_reply(msg)
    )


async def groups_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    groups = autopost_data[
        "groups"
    ]

    if not groups:

        await update.message.reply_text(
            owner_reply(
                "কোনো group নেই।"
            )
        )

        return

    lines = [
        "👥 GROUP LIST",
        ""
    ]

    for key, group in groups.items():

        status = (
            "ON"
            if group.get(
                "active",
                True
            )
            else "PAUSED"
        )

        lines.append(

            f"• {group.get('title', key)}\n"
            f"  ID: {key}\n"
            f"  Status: {status}"
        )

    await update.message.reply_text(
        owner_reply(
            "\n".join(lines)
        )
    )


async def delgroup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if not context.args:

        await update.message.reply_text(
            owner_reply(
                "Chat ID দিন।"
            )
        )

        return

    chat_id = parse_chat_id(
        context.args[0]
    )

    if delete_group(
        chat_id
    ):

        msg = (
            "Group delete করা হয়েছে।"
        )

    else:

        msg = (
            "Group পাওয়া যায়নি।"
        )

    await update.message.reply_text(
        owner_reply(msg)
    )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    text = (

        "📊 BOT STATUS\n\n"

        "🤖 Gemini: "
        + (
            "READY"
            if gemini_client
            else "NOT READY"
        )
        + "\n"

        "🔥 Firebase: "
        + (
            "CONNECTED"
            if firebase_db
            else "LOCAL MODE"
        )
        + "\n"

        "📢 Auto Post: "
        + (
            "ON"
            if autopost_data[
                "enabled"
            ]
            else "OFF"
        )
        + "\n"

        f"👥 Groups: "
        f"{len(autopost_data['groups'])}\n"

        f"📝 Posts: "
        f"{len(autopost_data['posts'])}\n"

        "⏰ Bangladesh Time: "
        + now_bd().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )
    )

    await update.message.reply_text(
        owner_reply(text)
    )


async def pausegroup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if not context.args:

        await update.message.reply_text(
            owner_reply(
                "Chat ID দিন।"
            )
        )

        return

    key = str(
        context.args[0]
    )

    if key not in autopost_data[
        "groups"
    ]:

        await update.message.reply_text(
            owner_reply(
                "Group পাওয়া যায়নি।"
            )
        )

        return

    group = autopost_data[
        "groups"
    ][key]

    group["active"] = not group.get(
        "active",
        True
    )

    save_autopost_data()

    status = (
        "চালু"
        if group["active"]
        else "বন্ধ"
    )

    await update.message.reply_text(
        owner_reply(
            "Group Auto Post "
            + status
            + " করা হয়েছে।"
        )
    )


async def renamegroup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) < 2:

        await update.message.reply_text(
            owner_reply(
                "ব্যবহার:\n"
                "/renamegroup CHAT_ID নতুন নাম"
            )
        )

        return

    key = str(
        context.args[0]
    )

    if key not in autopost_data[
        "groups"
    ]:

        await update.message.reply_text(
            owner_reply(
                "Group পাওয়া যায়নি।"
            )
        )

        return

    new_name = " ".join(
        context.args[1:]
    ).strip()

    autopost_data[
        "groups"
    ][key][
        "title"
    ] = new_name

    save_autopost_data()

    await update.message.reply_text(
        owner_reply(
            "Group-এর নাম '"
            + new_name
            + "' করা হয়েছে।"
        )
    )


async def broadcast_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    text = " ".join(
        context.args
    ).strip()

    replied = (
        update.message.reply_to_message
    )

    if replied and not text:

        if replied.text:
            text = replied.text

        elif replied.caption:
            text = replied.caption

    if not text and not (
        replied
        and replied.photo
    ):

        await update.message.reply_text(
            owner_reply(
                "Broadcast করার text "
                "অথবা reply করা message দিন।"
            )
        )

        return

    sent = 0
    failed = 0

    for key in active_groups():

        chat_id = parse_chat_id(
            key
        )

        try:

            if (
                replied
                and replied.photo
            ):

                await context.bot.send_photo(

                    chat_id=chat_id,

                    photo=(
                        replied
                        .photo[-1]
                        .file_id
                    ),

                    caption=(
                        text[:1024]
                        if text
                        else None
                    ),
                )

            else:

                await context.bot.send_message(

                    chat_id=chat_id,

                    text=text[:4096]
                )

            sent += 1

        except Exception as e:

            failed += 1

            logger.warning(
                "Broadcast failed: %s",
                e
            )

    await update.message.reply_text(

        owner_reply(

            f"Broadcast সম্পন্ন। "
            f"সফল: {sent}, "
            f"ব্যর্থ: {failed}"
        )
    )


async def list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    await update.message.reply_text(
        owner_reply(
            list_posts_text()
        )
    )


async def delete_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if not context.args:

        await update.message.reply_text(
            owner_reply(
                "Post ID দিন।"
            )
        )

        return

    post_id = context.args[0]

    if delete_post(
        post_id
    ):

        msg = (
            f"ID {post_id} "
            "Auto Post delete হয়েছে।"
        )

    else:

        msg = (
            f"ID {post_id} "
            "পাওয়া যায়নি।"
        )

    await update.message.reply_text(
        owner_reply(msg)
    )


async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    clear_posts()

    await update.message.reply_text(
        owner_reply(
            "সব Auto Post clear করা হয়েছে।"
        )
    )


async def on_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    autopost_data[
        "enabled"
    ] = True

    save_autopost_data()

    await update.message.reply_text(
        owner_reply(
            "Auto Post চালু করা হয়েছে।"
        )
    )


async def off_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    autopost_data[
        "enabled"
    ] = False

    save_autopost_data()

    await update.message.reply_text(
        owner_reply(
            "Auto Post বন্ধ করা হয়েছে।"
        )
    )


async def test_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    groups = active_groups()

    if not groups:

        await update.message.reply_text(
            owner_reply(
                "কোনো active group নেই।"
            )
        )

        return

    sent = 0

    for key in groups:

        try:

            await context.bot.send_message(

                chat_id=parse_chat_id(
                    key
                ),

                text=(
                    "🧪 RJ TEAM PREMIUM BOT\n"
                    "Auto Post Test"
                )
            )

            sent += 1

        except Exception as e:

            logger.warning(
                "Test failed: %s",
                e
            )

    await update.message.reply_text(

        owner_reply(
            f"Test message "
            f"{sent}টি active group-এ "
            "পাঠানো হয়েছে।"
        )
    )


async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    context.user_data.pop(
        "owner_pending",
        None
    )

    await update.message.reply_text(
        owner_reply(
            "Pending action cancel করা হয়েছে।"
        )
    )


# ============================================================
# OWNER NATURAL LANGUAGE
# ============================================================

async def handle_owner_natural_command(
    update: Update,
    text: str
):

    if not is_admin(update):
        return False

    raw = text.strip()
    low = raw.lower()

    # --------------------------------------------------------
    # AUTO POST OFF
    # --------------------------------------------------------

    if (
        re.search(
            r"\b(auto\s*post|autopost)\b.*"
            r"\b(off|বন্ধ|বন্ধ কর|বন্ধ করে দাও)\b",
            low
        )
        or "অটো পোস্ট বন্ধ" in raw
    ):

        autopost_data[
            "enabled"
        ] = False

        save_autopost_data()

        await update.message.reply_text(
            owner_reply(
                "Auto Post বন্ধ করে দিয়েছি।"
            )
        )

        return True

    # --------------------------------------------------------
    # AUTO POST ON
    # --------------------------------------------------------

    if (
        re.search(
            r"\b(auto\s*post|autopost)\b.*"
            r"\b(on|চালু|চালু কর|চালু করে দাও)\b",
            low
        )
        or "অটো পোস্ট চালু" in raw
    ):

        autopost_data[
            "enabled"
        ] = True

        save_autopost_data()

        await update.message.reply_text(
            owner_reply(
                "Auto Post চালু করে দিয়েছি।"
            )
        )

        return True

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if (
        "status" in low
        or "স্ট্যাটাস" in raw
        or "অবস্থা দেখাও" in raw
    ):

        await status_command(
            update,
            None
        )

        return True

    # --------------------------------------------------------
    # GROUP LIST
    # --------------------------------------------------------

    if (
        "group list" in low
        or "groups list" in low
        or "groups show" in low
        or "গ্রুপ দেখাও" in raw
        or "গ্রুপ লিস্ট" in raw
    ):

        await groups_command(
            update,
            None
        )

        return True

    # --------------------------------------------------------
    # POST LIST
    # --------------------------------------------------------

    if (
        low in {
            "list",
            "show list",
            "auto post list",
            "autopost list"
        }
        or "list দেখাও" in raw
        or "লিস্ট দেখাও" in raw
    ):

        await list_command(
            update,
            None
        )

        return True

    # --------------------------------------------------------
    # DELETE ID
    # --------------------------------------------------------

    delete_match = re.search(

        r"(?:id|আইডি)"
        r"\s*#?\s*(\d+)"
        r".*?"
        r"(?:delete|ডিলিট|মুছে|remove)",

        raw,
        re.I
    )

    if not delete_match:

        delete_match = re.search(

            r"(?:delete|ডিলিট|remove|মুছে)"
            r".*?"
            r"(?:id|আইডি)"
            r"\s*#?\s*(\d+)",

            raw,
            re.I
        )

    if delete_match:

        post_id = (
            delete_match.group(1)
        )

        if delete_post(
            post_id
        ):

            msg = (
                f"ID {post_id} "
                "Auto Post delete করে দিয়েছি।"
            )

        else:

            msg = (
                f"ID {post_id} "
                "পাওয়া যায়নি।"
            )

        await update.message.reply_text(
            owner_reply(msg)
        )

        return True

    # --------------------------------------------------------
    # CLEAR ALL
    # --------------------------------------------------------

    if (
        ("all" in low or "সব" in raw)
        and (
            "auto post" in low
            or "autopost" in low
            or "অটো পোস্ট" in raw
        )
        and any(
            word in low
            for word in [
                "delete",
                "clear",
                "remove"
            ]
        )
    ):

        clear_posts()

        await update.message.reply_text(
            owner_reply(
                "সব Auto Post মুছে দিয়েছি।"
            )
        )

        return True

    # --------------------------------------------------------
    # ADD CURRENT GROUP
    # --------------------------------------------------------

    if (
        "add group" in low
        or "group add" in low
        or "গ্রুপ add" in low
        or "গ্রুপ যোগ" in raw
    ):

        chat = update.effective_chat

        if chat and add_group(
            chat.id,
            chat.title
            or str(chat.id)
        ):

            msg = (
                "এই group Auto Post "
                "list-এ যোগ করে দিয়েছি।"
            )

        else:

            msg = (
                "এই group আগে থেকেই "
                "list-এ আছে।"
            )

        await update.message.reply_text(
            owner_reply(msg)
        )

        return True

    # --------------------------------------------------------
    # BROADCAST
    # --------------------------------------------------------

    if (
        low.startswith(
            "broadcast "
        )
        or raw.startswith(
            "ব্রডকাস্ট "
        )
    ):

        if low.startswith(
            "broadcast "
        ):

            broadcast_text = (
                raw[
                    len("broadcast "):
                ].strip()
            )

        else:

            broadcast_text = (
                raw[
                    len("ব্রডকাস্ট "):
                ].strip()
            )

        if not broadcast_text:

            await update.message.reply_text(
                owner_reply(
                    "Broadcast message-টা দিন।"
                )
            )

            return True

        sent = 0
        failed = 0

        for key in active_groups():

            try:

                await update.get_bot().send_message(

                    chat_id=parse_chat_id(
                        key
                    ),

                    text=broadcast_text[
                        :4096
                    ]
                )

                sent += 1

            except Exception as e:

                failed += 1

                logger.warning(
                    "Natural broadcast failed: %s",
                    e
                )

        await update.message.reply_text(

            owner_reply(

                f"Broadcast শেষ। "
                f"সফল: {sent}, "
                f"ব্যর্থ: {failed}"
            )
        )

        return True

    # --------------------------------------------------------
    # PAUSE / RESUME GROUP
    # --------------------------------------------------------

    pause_match = re.search(

        r"(?:pause|resume|toggle|বন্ধ|চালু)"
        r".*?"
        r"(?:group|গ্রুপ)"
        r"\s*(-?\d+)",

        raw,
        re.I
    )

    if pause_match:

        key = (
            pause_match.group(1)
        )

        if key not in autopost_data[
            "groups"
        ]:

            await update.message.reply_text(
                owner_reply(
                    "এই group পাওয়া যায়নি।"
                )
            )

            return True

        group = autopost_data[
            "groups"
        ][key]

        group[
            "active"
        ] = not group.get(
            "active",
            True
        )

        save_autopost_data()

        await update.message.reply_text(

            owner_reply(

                "Group Auto Post "
                + (
                    "চালু"
                    if group["active"]
                    else "বন্ধ"
                )
                + " করে দিয়েছি।"
            )
        )

        return True

    # --------------------------------------------------------
    # SCHEDULED AUTO POST
    # Example:
    # 8:30 PM আজকের পোস্ট
    # auto post 8:30 PM আজকের পোস্ট
    # --------------------------------------------------------

    schedule_source = raw

    match = re.search(

        r"(?:auto\s*post|autopost|অটো\s*পোস্ট)"
        r"\s+(.+)",

        raw,
        re.I
    )

    if match:

        schedule_source = (
            match.group(1).strip()
        )

    post_time, post_text = (
        extract_time_and_text(
            schedule_source
        )
    )

    if post_time and post_text:

        groups = list(
            autopost_data[
                "groups"
            ].keys()
        )

        # If no group is configured,
        # use the current group.
        if not groups:

            chat = update.effective_chat

            if chat:

                add_group(
                    chat.id,
                    chat.title
                    or str(chat.id)
                )

                groups = [
                    str(chat.id)
                ]

        post = add_post(

            post_time=post_time,

            text=post_text,

            group_ids=groups
        )

        await update.message.reply_text(

            owner_reply(

                "Auto Post তৈরি করে দিয়েছি.\n"
                f"🆔 ID: {post['id']}\n"
                f"⏰ Time: {post_time}\n"
                f"👥 Groups: {len(groups)}\n"
                f"📝 {post_text}"
            )
        )

        return True

    return False


# ============================================================
# CALLBACK BUTTONS
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if query.data == "about":

        await query.message.reply_text(
            ABOUT_TEXT
        )

    elif query.data == "translate":

        await query.message.reply_text(

            "🌐 Translation\n\n"
            "আপনার text translate করতে:\n"
            "/translate আপনার text"
        )


# ============================================================
# NORMAL MESSAGE HANDLER
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text

    if not text:
        return

    # Owner commands first.
    if is_admin(update):

        handled = (
            await handle_owner_natural_command(
                update,
                text
            )
        )

        if handled:
            return

    # Normal Gemini reply.
    answer = await ask_gemini(
        text
    )

    user_id = (
        update.effective_user.id
    )

    user_last_ai_reply[
        user_id
    ] = answer

    # Every Owner AI reply gets "বস".
    if is_admin(update):

        answer = owner_reply(
            answer
        )

    keyboard = [

        [

            InlineKeyboardButton(
                "🌐 Translate",
                callback_data="translate"
            )

        ]

    ]

    await update.message.reply_text(

        answer,

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# AUTO POST WORKER
# ============================================================

async def auto_post_worker(
    application
):

    logger.info(
        "Auto Post worker started."
    )

    last_sent = set()

    while True:

        try:

            await asyncio.sleep(
                20
            )

            if not autopost_data.get(
                "enabled",
                True
            ):

                continue

            current = now_bd()

            current_hm = (
                current.strftime(
                    "%H:%M"
                )
            )

            date_key = (
                current.strftime(
                    "%Y-%m-%d"
                )
            )

            for post in list(
                autopost_data.get(
                    "posts",
                    []
                )
            ):

                if not post.get(
                    "enabled",
                    True
                ):

                    continue

                if post.get(
                    "post_time"
                ) != current_hm:

                    continue

                marker = (
                    f"{date_key}:"
                    f"{post.get('id')}"
                )

                if marker in last_sent:

                    continue

                group_ids = (
                    post.get(
                        "group_ids"
                    )
                    or list(
                        autopost_data[
                            "groups"
                        ].keys()
                    )
                )

                for key in group_ids:

                    group = (
                        autopost_data[
                            "groups"
                        ].get(
                            str(key)
                        )
                    )

                    if (
                        group
                        and not group.get(
                            "active",
                            True
                        )
                    ):

                        continue

                    chat_id = (
                        parse_chat_id(
                            key
                        )
                    )

                    try:

                        photo_id = (
                            post.get(
                                "photo_id"
                            )
                        )

                        text = (
                            post.get(
                                "text"
                            )
                            or post.get(
                                "caption"
                            )
                            or ""
                        )

                        if photo_id:

                            await application.bot.send_photo(

                                chat_id=chat_id,

                                photo=photo_id,

                                caption=(
                                    text[:1024]
                                    if text
                                    else None
                                )
                            )

                        else:

                            await application.bot.send_message(

                                chat_id=chat_id,

                                text=text[:4096]
                            )

                    except Exception as e:

                        logger.warning(

                            "Auto Post failed "
                            "for %s: %s",

                            chat_id,
                            e
                        )

                last_sent.add(
                    marker
                )

            # Prevent unlimited memory growth.
            if len(last_sent) > 5000:

                last_sent = set(
                    list(last_sent)[-1000:]
                )

        except asyncio.CancelledError:

            break

        except Exception as e:

            logger.exception(
                "Auto Post worker error: %s",
                e
            )

            await asyncio.sleep(
                10
            )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "Unhandled Telegram error: %s",
        context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable "
            "is missing."
        )

    init_firebase()

    load_autopost_data()

    init_gemini()

    application = (
        Application
        .builder()
        .token(
            BOT_TOKEN
        )
        .build()
    )

    # --------------------------------------------------------
    # PUBLIC
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    application.add_handler(
        CommandHandler(
            "about",
            about_command
        )
    )

    application.add_handler(
        CommandHandler(
            "translate",
            translate_command
        )
    )

    application.add_handler(
        CommandHandler(
            "translate_last",
            translate_last_command
        )
    )

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "autopost",
            autopost_command
        )
    )

    application.add_handler(
        CommandHandler(
            "addgroup",
            addgroup_command
        )
    )

    application.add_handler(
        CommandHandler(
            "groups",
            groups_command
        )
    )

    application.add_handler(
        CommandHandler(
            "delgroup",
            delgroup_command
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status_command
        )
    )

    application.add_handler(
        CommandHandler(
            "pausegroup",
            pausegroup_command
        )
    )

    application.add_handler(
        CommandHandler(
            "renamegroup",
            renamegroup_command
        )
    )

    application.add_handler(
        CommandHandler(
            "broadcast",
            broadcast_command
        )
    )

    application.add_handler(
        CommandHandler(
            "list",
            list_command
        )
    )

    application.add_handler(
        CommandHandler(
            "delete",
            delete_command
        )
    )

    application.add_handler(
        CommandHandler(
            "clear",
            clear_command
        )
    )

    application.add_handler(
        CommandHandler(
            "on",
            on_command
        )
    )

    application.add_handler(
        CommandHandler(
            "off",
            off_command
        )
    )

    application.add_handler(
        CommandHandler(
            "test",
            test_command
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
        )
    )

    # --------------------------------------------------------
    # BUTTONS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    application.add_handler(

        MessageHandler(

            filters.TEXT
            & ~filters.COMMAND,

            handle_message
        )
    )

    application.add_error_handler(
        error_handler
    )

    async def post_init(app):

        app.create_task(
            auto_post_worker(
                app
            )
        )

    application.post_init = (
        post_init
    )

    logger.info(
        "RJ Premium Bot starting..."
    )

    # --------------------------------------------------------
    # RENDER WEBHOOK
    # --------------------------------------------------------

    if RENDER_EXTERNAL_URL:

        base_url = (
            RENDER_EXTERNAL_URL
            .rstrip("/")
        )

        webhook_path = (
            "/telegram/"
            + BOT_TOKEN
        )

        logger.info(
            "Starting webhook mode."
        )

        application.run_webhook(

            listen="0.0.0.0",

            port=PORT,

            url_path=webhook_path,

            webhook_url=(
                base_url
                + webhook_path
            )
        )

    # --------------------------------------------------------
    # LOCAL / RENDER POLLING
    # --------------------------------------------------------

    else:

        logger.info(
            "Starting polling mode."
        )

        application.run_polling(

            allowed_updates=(
                Update.ALL_TYPES
            ),

            drop_pending_updates=False
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
