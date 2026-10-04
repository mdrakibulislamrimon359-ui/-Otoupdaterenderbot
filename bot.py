# ============================================================
# RJ TEAM BANGLADESH - PREMIUM AI BOT
# COMPLETE MERGED VERSION
# ============================================================

import os
import re
import json
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

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
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("RJ_TEAM_BOT")


# ============================================================
# ENVIRONMENT
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
    "autopost.json"
).strip()

AUTOPOST_ENABLED = os.getenv(
    "AUTOPOST_ENABLED",
    "true"
).lower() in ("1", "true", "yes", "on")

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
    os.getenv("PORT", "10000")
)

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).strip()


# ============================================================
# TIMEZONE
# ============================================================

BD = ZoneInfo("Asia/Dhaka")


# ============================================================
# OWNER
# ============================================================

OWNER_USERNAME = "@" + ADMIN_USERNAME


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


# ============================================================
# SYSTEM PROMPTS
# ============================================================

SYSTEM_PROMPT = """
You are RJ Team Bangladesh Premium AI Bot.

You are a friendly and helpful AI assistant.

Rules:
- Reply naturally in Bangla when the user writes Bangla/Banglish.
- You may use English when appropriate.
- Keep answers clear and useful.
- Do not claim that an action was performed unless the bot actually performed it.
- Never pretend to have sent a message, changed a setting, or posted something unless the code actually did it.
- Do not provide harmful or illegal instructions.
- When the owner talks normally, behave like a normal AI assistant.
"""

POST_SYSTEM_PROMPT = """
You are the official social media post writer for RJ Team Bangladesh.

Convert the owner's instruction into a polished Bangla social-media style post.

Rules:
- Make it attractive.
- Use suitable emojis.
- Keep the original meaning.
- Do not invent prices, links, dates, facts, or offers.
- Do not mention that AI generated the post.
- Output ONLY the final post.
"""


# ============================================================
# ABOUT
# ============================================================

ABOUT_TEXT = """
🤖 RJ TEAM BANGLADESH - PREMIUM AI BOT

✨ Gemini AI Chat
✨ Smart Auto Post
✨ Multi Group Support
✨ Scheduled Posts
✨ Firebase Storage
✨ Owner Controls
✨ Broadcast System
✨ Translation System

👑 Owner: @RJteam1
🇧🇩 Bangladesh
"""


# ============================================================
# GLOBALS
# ============================================================

gemini_client = None
firebase_db = None

user_last_ai_reply = {}

autopost_data = {
    "enabled": AUTOPOST_ENABLED,
    "groups": {},
    "posts": [],
    "owner_sms_to_group": False,
    "user_sms_to_group": {},
    "user_registry": {},
}

OWNER_SMS_TO_GROUP = False
USER_SMS_TO_GROUP = {}
USER_REGISTRY = {}

scheduler_task = None


# ============================================================
# BASIC HELPERS
# ============================================================

def now_bd():
    return datetime.now(BD)


def is_admin(update: Update):
    user = update.effective_user

    if not user:
        return False

    username = (user.username or "").strip().lstrip("@")

    if username.lower() == ADMIN_USERNAME.lower():
        return True

    if ADMIN_USER_ID:
        try:
            if str(user.id) == str(ADMIN_USER_ID):
                return True
        except Exception:
            pass

    return False


def owner_reply(text):
    return f"👑 বস,\n\n{text}"


def parse_chat_id(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def is_real_group_chat(chat):
    if not chat:
        return False

    return chat.type in (
        "group",
        "supergroup",
    )


def clean_text(text):
    return (text or "").strip()


# ============================================================
# FIREBASE
# ============================================================

def init_firebase():
    global firebase_db

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.info("Firebase disabled: FIREBASE_SERVICE_ACCOUNT_JSON not found.")
        return

    try:
        if not firebase_admin._apps:
            try:
                service_account = json.loads(
                    FIREBASE_SERVICE_ACCOUNT_JSON
                )

                cred = credentials.Certificate(
                    service_account
                )

                firebase_admin.initialize_app(cred)

            except Exception:
                # Some Render setups provide a file path instead.
                if os.path.exists(FIREBASE_SERVICE_ACCOUNT_JSON):
                    cred = credentials.Certificate(
                        FIREBASE_SERVICE_ACCOUNT_JSON
                    )

                    firebase_admin.initialize_app(cred)
                else:
                    raise

        firebase_db = firestore.client()

        logger.info("Firebase initialized successfully.")

    except Exception as e:
        logger.exception(
            "Firebase initialization failed: %s",
            e
        )

        firebase_db = None


def firebase_load():
    if firebase_db is None:
        return None

    try:
        ref = (
            firebase_db
            .collection(AUTOPOST_FIREBASE_COLLECTION)
            .document(AUTOPOST_FIREBASE_DOCUMENT)
        )

        snap = ref.get()

        if snap.exists:
            return snap.to_dict()

    except Exception as e:
        logger.exception(
            "Firebase load failed: %s",
            e
        )

    return None


def firebase_save(data):
    if firebase_db is None:
        return False

    try:
        ref = (
            firebase_db
            .collection(AUTOPOST_FIREBASE_COLLECTION)
            .document(AUTOPOST_FIREBASE_DOCUMENT)
        )

        ref.set(data)

        return True

    except Exception as e:
        logger.exception(
            "Firebase save failed: %s",
            e
        )

        return False


# ============================================================
# NORMALIZE DATA
# ============================================================

def normalize_autopost_data(data):
    if not isinstance(data, dict):
        data = {}

    data.setdefault("enabled", AUTOPOST_ENABLED)
    data.setdefault("groups", {})
    data.setdefault("posts", [])

    data.setdefault(
        "owner_sms_to_group",
        False
    )

    data.setdefault(
        "user_sms_to_group",
        {}
    )

    data.setdefault(
        "user_registry",
        {}
    )

    if not isinstance(data["groups"], dict):
        data["groups"] = {}

    if not isinstance(data["posts"], list):
        data["posts"] = []

    if not isinstance(
        data["user_sms_to_group"],
        dict
    ):
        data["user_sms_to_group"] = {}

    if not isinstance(
        data["user_registry"],
        dict
    ):
        data["user_registry"] = {}

    # Normalize post IDs to 1..N
    for index, post in enumerate(
        data["posts"],
        start=1
    ):
        if not isinstance(post, dict):
            data["posts"][index - 1] = {
                "id": index,
                "post_time": "08:00",
                "text": "",
                "caption": "",
                "photo_id": None,
                "group_ids": [],
                "enabled": True,
            }
            continue

        post["id"] = index
        post.setdefault("post_time", "08:00")
        post.setdefault("text", "")
        post.setdefault("caption", "")
        post.setdefault("photo_id", None)
        post.setdefault("group_ids", [])
        post.setdefault("enabled", True)

    return data


# ============================================================
# LOCAL SAVE / LOAD
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

        return True

    except Exception as e:
        logger.exception(
            "Local save failed: %s",
            e
        )

        return False


def save_autopost_data():
    global autopost_data

    autopost_data = normalize_autopost_data(
        autopost_data
    )

    save_local()
    firebase_save(autopost_data)


def load_autopost_data():
    global autopost_data
    global OWNER_SMS_TO_GROUP
    global USER_SMS_TO_GROUP
    global USER_REGISTRY

    firebase_data = firebase_load()

    if firebase_data:
        autopost_data = firebase_data

    elif os.path.exists(AUTOPOST_FILE):

        try:
            with open(
                AUTOPOST_FILE,
                "r",
                encoding="utf-8"
            ) as f:
                autopost_data = json.load(f)

        except Exception as e:
            logger.exception(
                "Local data load failed: %s",
                e
            )

            autopost_data = {}

    autopost_data = normalize_autopost_data(
        autopost_data
    )

    OWNER_SMS_TO_GROUP = bool(
        autopost_data.get(
            "owner_sms_to_group",
            False
        )
    )

    USER_SMS_TO_GROUP = {
        str(k): bool(v)
        for k, v in autopost_data.get(
            "user_sms_to_group",
            {}
        ).items()
    }

    USER_REGISTRY = {
        str(k): int(v)
        for k, v in autopost_data.get(
            "user_registry",
            {}
        ).items()
        if str(v).lstrip("-").isdigit()
    }


# ============================================================
# SMS SETTINGS
# ============================================================

def save_sms_settings():
    autopost_data[
        "owner_sms_to_group"
    ] = OWNER_SMS_TO_GROUP

    autopost_data[
        "user_sms_to_group"
    ] = USER_SMS_TO_GROUP

    autopost_data[
        "user_registry"
    ] = USER_REGISTRY

    save_autopost_data()


def register_user(user):
    if not user:
        return

    user_id = str(user.id)

    username = (
        user.username or ""
    ).strip().lstrip("@").lower()

    USER_REGISTRY[user_id] = user.id

    if username:
        USER_REGISTRY[
            "@" + username
        ] = user.id

    save_sms_settings()


def is_user_sms_to_group_enabled(user_id):
    return USER_SMS_TO_GROUP.get(
        str(user_id),
        False
    )


# ============================================================
# TIME PARSER
# ============================================================

def parse_time(value):
    if not value:
        return None

    value = value.strip().upper()

    patterns = [
        r"^(\d{1,2}):(\d{2})\s*(AM|PM)$",
        r"^(\d{1,2})\s*(AM|PM)$",
        r"^(\d{1,2}):(\d{2})$",
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            value
        )

        if not match:
            continue

        try:
            if len(match.groups()) == 3:
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3)

                if ampm == "PM" and hour != 12:
                    hour += 12

                if ampm == "AM" and hour == 12:
                    hour = 0

            elif len(match.groups()) == 2:
                hour = int(match.group(1))
                minute = 0
                ampm = match.group(2)

                if ampm == "PM" and hour != 12:
                    hour += 12

                if ampm == "AM" and hour == 12:
                    hour = 0

            else:
                hour = int(match.group(1))
                minute = int(match.group(2))

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"

        except Exception:
            pass

    return None


def extract_time_and_text(text):
    text = clean_text(text)

    patterns = [
        r"(?:auto\s*post\s*)?(\d{1,2}:\d{2}\s*(?:AM|PM))\s+(.+)$",
        r"(?:auto\s*post\s*)?(\d{1,2}\s*(?:AM|PM))\s+(.+)$",
    ]

    for pattern in patterns:

        match = re.match(
            pattern,
            text,
            flags=re.I
        )

        if match:
            post_time = parse_time(
                match.group(1)
            )

            post_text = match.group(2).strip()

            if post_time and post_text:
                return post_time, post_text

    return None, None


# ============================================================
# GEMINI
# ============================================================

def init_gemini():
    global gemini_client

    if not GEMINI_API_KEY:
        logger.error(
            "GEMINI_API_KEY is missing."
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

        gemini_client = None


async def ask_gemini(text):
    if not gemini_client:
        return (
            "⚠️ Gemini AI এখন চালু নেই।\n"
            "GEMINI_API_KEY এবং Render settings চেক করুন।"
        )

    text = clean_text(text)

    if not text:
        return "কী জানতে চান বস?"

    last_error = None

    for model_name in GEMINI_MODELS:

        try:
            response = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=SYSTEM_PROMPT
                                + "\n\nUser message:\n"
                                + text
                            )
                        ]
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
                "Gemini model failed %s: %s",
                model_name,
                e
            )

            continue

    return (
        "⚠️ AI উত্তর দিতে পারছে না।\n"
        "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
    )


async def create_ai_post(text):
    if not gemini_client:
        return clean_text(text)

    last_error = None

    for model_name in GEMINI_MODELS:

        try:
            response = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=POST_SYSTEM_PROMPT
                                + "\n\nOwner instruction:\n"
                                + text
                            )
                        ]
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
                "Post AI failed %s: %s",
                model_name,
                e
            )

    return clean_text(text)


# ============================================================
# GROUP MANAGEMENT
# ============================================================

def clean_invalid_groups():
    removed = []

    groups = autopost_data.get(
        "groups",
        {}
    )

    for key, group in list(
        groups.items()
    ):

        try:
            chat_id = int(
                group.get(
                    "chat_id",
                    key
                )
            )

            # Telegram groups/supergroups normally have
            # negative IDs.
            if chat_id >= 0:
                removed.append(key)
                del groups[key]

        except Exception:
            removed.append(key)
            del groups[key]

    if removed:
        save_autopost_data()

    return removed


def add_group(chat):
    if not is_real_group_chat(chat):
        return False, (
            "এই chat টি group/supergroup নয়।"
        )

    chat_id = chat.id

    if chat_id >= 0:
        return False, (
            "Invalid group ID."
        )

    autopost_data.setdefault(
        "groups",
        {}
    )

    autopost_data["groups"][
        str(chat_id)
    ] = {
        "chat_id": chat_id,
        "title": chat.title or "Unknown Group",
        "active": True,
    }

    save_autopost_data()

    return True, (
        f"✅ Group added.\n\n"
        f"📌 {chat.title}\n"
        f"🆔 {chat_id}"
    )


def delete_group(chat_id):
    chat_id = parse_chat_id(chat_id)

    if chat_id is None:
        return False

    groups = autopost_data.get(
        "groups",
        {}
    )

    key = str(chat_id)

    if key not in groups:
        return False

    del groups[key]

    # Remove from post-specific group lists too.
    for post in autopost_data.get(
        "posts",
        []
    ):
        post["group_ids"] = [
            str(x)
            for x in post.get(
                "group_ids",
                []
            )
            if str(x) != key
        ]

    save_autopost_data()

    return True


def active_groups():
    clean_invalid_groups()

    result = []

    for key, group in autopost_data.get(
        "groups",
        {}
    ).items():

        if not group.get(
            "active",
            True
        ):
            continue

        try:
            chat_id = int(
                group.get(
                    "chat_id",
                    key
                )
            )

            if chat_id < 0:
                result.append(
                    {
                        "chat_id": chat_id,
                        "title": group.get(
                            "title",
                            "Unknown Group"
                        ),
                    }
                )

        except Exception:
            continue

    return result


# ============================================================
# POSTS
# ============================================================

def add_post(
    post_time,
    text,
    photo_id=None,
    group_ids=None
):
    posts = autopost_data.setdefault(
        "posts",
        []
    )

    new_id = len(posts) + 1

    post = {
        "id": new_id,
        "post_time": post_time,
        "text": text,
        "caption": text,
        "photo_id": photo_id,
        "group_ids": group_ids or [],
        "enabled": True,
    }

    posts.append(post)

    autopost_data["posts"] = normalize_autopost_data(
        autopost_data
    )["posts"]

    save_autopost_data()

    return post


def delete_post(post_id):
    try:
        post_id = int(post_id)
    except Exception:
        return False

    posts = autopost_data.get(
        "posts",
        []
    )

    if post_id < 1 or post_id > len(posts):
        return False

    del posts[post_id - 1]

    autopost_data["posts"] = normalize_autopost_data(
        autopost_data
    )["posts"]

    save_autopost_data()

    return True


def clear_posts():
    autopost_data["posts"] = []

    save_autopost_data()


def list_posts_text():
    posts = autopost_data.get(
        "posts",
        []
    )

    if not posts:
        return "📭 কোনো Auto Post নেই।"

    lines = [
        "📋 RJ Team Auto Posts",
        "",
    ]

    for post in posts:
        status = (
            "🟢 ON"
            if post.get("enabled", True)
            else "🔴 OFF"
        )

        text = (
            post.get("text")
            or post.get("caption")
            or ""
        )

        text = text.replace(
            "\n",
            " "
        )

        if len(text) > 80:
            text = text[:80] + "..."

        lines.append(
            f"#{post['id']} | "
            f"⏰ {post.get('post_time')}"
        )

        lines.append(
            f"{status} | {text}"
        )

        lines.append("")

    return "\n".join(lines)


# ============================================================
# SEND POST TO GROUPS
# ============================================================

async def send_post_to_groups(
    application,
    text,
    photo_id=None,
    specific_group_ids=None
):
    groups = active_groups()

    if specific_group_ids:
        allowed = {
            str(x)
            for x in specific_group_ids
        }

        groups = [
            g
            for g in groups
            if str(g["chat_id"])
            in allowed
        ]

    sent = 0
    failed = 0

    if not groups:
        return 0, 0

    for group in groups:

        chat_id = group["chat_id"]

        try:
            if photo_id:

                await application.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=text[:1024]
                )

            else:

                await application.bot.send_message(
                    chat_id=chat_id,
                    text=text[:4096]
                )

            sent += 1

        except Exception as e:
            failed += 1

            logger.warning(
                "Group send failed %s: %s",
                chat_id,
                e
            )

    return sent, failed


# ============================================================
# EXPLICIT GROUP POST
# ============================================================

def extract_explicit_group_post(text):
    """
    Examples:

    group এ পোস্ট করো: আজ শুভ সন্ধ্যা
    গ্রুপে পোস্ট করো: আজকের খবর
    গ্রুপে দাও: নতুন অফার
    post to group: hello
    group post: hello
    """

    patterns = [
        r"^(?:group|গ্রুপ)\s*(?:এ|তে)?\s*পোস্ট\s*করো\s*[:\-]\s*(.+)$",
        r"^গ্রুপে\s*পোস্ট\s*করো\s*[:\-]\s*(.+)$",
        r"^গ্রুপে\s*দাও\s*[:\-]\s*(.+)$",
        r"^post\s+to\s+group\s*[:\-]\s*(.+)$",
        r"^group\s+post\s*[:\-]\s*(.+)$",
    ]

    for pattern in patterns:

        match = re.match(
            pattern,
            text.strip(),
            flags=re.I
        )

        if match:
            return match.group(1).strip()

    return None


# ============================================================
# OWNER NATURAL COMMANDS
# ============================================================

async def handle_owner_natural_command(
    update,
    text
):
    global OWNER_SMS_TO_GROUP

    raw = clean_text(text)

    low = raw.lower()

    # --------------------------------------------------------
    # EXPLICIT GROUP POST
    # --------------------------------------------------------

    explicit_post = extract_explicit_group_post(
        raw
    )

    if explicit_post:

        post_text = await create_ai_post(
            explicit_post
        )

        sent, failed = await send_post_to_groups(
            update.get_bot().application,
            post_text
        )

        if sent == 0:
            await update.message.reply_text(
                owner_reply(
                    "কোনো active group পাওয়া যায়নি।\n"
                    "আগে group-এর ভিতর থেকে /addgroup দিন।"
                )
            )
        else:
            await update.message.reply_text(
                owner_reply(
                    f"✅ Group-এ পোস্ট করা হয়েছে।\n\n"
                    f"📤 Sent: {sent}\n"
                    f"❌ Failed: {failed}"
                )
            )

        return True

    # --------------------------------------------------------
    # OWNER SMS TO GROUP OFF
    # --------------------------------------------------------

    off_patterns = [
        "ওনার এসএমএস টু গ্রুপ অফ",
        "ওনার sms to group off",
        "owner sms to group off",
        "sms to group off",
        "sms group off",
    ]

    if any(
        p in low
        for p in off_patterns
    ):
        OWNER_SMS_TO_GROUP = False
        save_sms_settings()

        await update.message.reply_text(
            owner_reply(
                "📴 Owner SMS → Group OFF করা হয়েছে।\n\n"
                "এখন আপনি সাধারণভাবে কথা বললে "
                "Gemini AI উত্তর দেবে।\n\n"
                "Group-এ দিতে চাইলে লিখুন:\n"
                "group এ পোস্ট করো: আপনার লেখা"
            )
        )

        return True

    # --------------------------------------------------------
    # OWNER SMS TO GROUP ON
    # --------------------------------------------------------

    on_patterns = [
        "ওনার এসএমএস টু গ্রুপ অন",
        "ওনার sms to group on",
        "owner sms to group on",
        "sms to group on",
        "sms group on",
    ]

    if any(
        p in low
        for p in on_patterns
    ):
        OWNER_SMS_TO_GROUP = True
        save_sms_settings()

        await update.message.reply_text(
            owner_reply(
                "📲 Owner SMS → Group ON করা হয়েছে।\n\n"
                "এখন আপনার সাধারণ SMS-ও AI সুন্দর করে "
                "Group-এ পোস্ট করবে।"
            )
        )

        return True

    # --------------------------------------------------------
    # SMS STATUS
    # --------------------------------------------------------

    if (
        "ওনার এসএমএস স্ট্যাটাস" in low
        or "owner sms status" in low
        or "sms to group status" in low
        or low == "sms status"
    ):
        status = (
            "🟢 ON"
            if OWNER_SMS_TO_GROUP
            else "🔴 OFF"
        )

        await update.message.reply_text(
            owner_reply(
                f"📲 Owner SMS → Group: {status}"
            )
        )

        return True

    # --------------------------------------------------------
    # USER SMS ON/OFF
    # --------------------------------------------------------

    user_match = re.match(
        r"^(-?\d+)\s+sms\s+(on|off)$",
        raw,
        flags=re.I
    )

    if user_match:

        user_id = user_match.group(1)
        action = user_match.group(2).lower()

        enabled = action == "on"

        USER_SMS_TO_GROUP[
            str(user_id)
        ] = enabled

        save_sms_settings()

        status = (
            "🟢 ON"
            if enabled
            else "🔴 OFF"
        )

        await update.message.reply_text(
            owner_reply(
                f"👤 User ID: {user_id}\n"
                f"📲 SMS → Group: {status}"
            )
        )

        return True

    # --------------------------------------------------------
    # USER SMS STATUS
    # --------------------------------------------------------

    user_status_match = re.match(
        r"^(-?\d+)\s+sms\s+status$",
        raw,
        flags=re.I
    )

    if user_status_match:

        user_id = user_status_match.group(1)

        status = (
            "🟢 ON"
            if is_user_sms_to_group_enabled(
                user_id
            )
            else "🔴 OFF"
        )

        await update.message.reply_text(
            owner_reply(
                f"👤 User ID: {user_id}\n"
                f"📲 SMS → Group: {status}"
            )
        )

        return True

    # --------------------------------------------------------
    # AUTO POST OFF
    # --------------------------------------------------------

    if (
        "auto post off" in low
        or "autopost off" in low
        or "অটো পোস্ট বন্ধ" in low
    ):
        autopost_data["enabled"] = False
        save_autopost_data()

        await update.message.reply_text(
            owner_reply(
                "⛔ Auto Post বন্ধ করা হয়েছে।"
            )
        )

        return True

    # --------------------------------------------------------
    # AUTO POST ON
    # --------------------------------------------------------

    if (
        "auto post on" in low
        or "autopost on" in low
        or "অটো পোস্ট চালু" in low
    ):
        autopost_data["enabled"] = True
        save_autopost_data()

        await update.message.reply_text(
            owner_reply(
                "✅ Auto Post চালু করা হয়েছে।"
            )
        )

        return True

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if low in (
        "status",
        "স্ট্যাটাস",
        "অবস্থা দেখাও",
        "bot status",
    ):
        groups = active_groups()
        posts = autopost_data.get(
            "posts",
            []
        )

        await update.message.reply_text(
            owner_reply(
                f"🤖 Bot Status\n\n"
                f"Auto Post: "
                f"{'🟢 ON' if autopost_data.get('enabled') else '🔴 OFF'}\n"
                f"Owner SMS → Group: "
                f"{'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n"
                f"Active Groups: {len(groups)}\n"
                f"Auto Posts: {len(posts)}\n"
                f"Time: {now_bd().strftime('%I:%M:%S %p')}"
            )
        )

        return True

    # --------------------------------------------------------
    # GROUP LIST
    # --------------------------------------------------------

    if (
        "group list" in low
        or "groups" == low
        or "গ্রুপ লিস্ট" in low
        or "গ্রুপগুলো দেখাও" in low
    ):
        groups = active_groups()

        if not groups:
            message = "📭 কোনো active group নেই।"

        else:
            lines = [
                "📋 Active Groups",
                ""
            ]

            for index, group in enumerate(
                groups,
                start=1
            ):
                lines.append(
                    f"{index}. "
                    f"{group['title']}\n"
                    f"🆔 {group['chat_id']}"
                )

            message = "\n\n".join(lines)

        await update.message.reply_text(
            owner_reply(message)
        )

        return True

    # --------------------------------------------------------
    # POST LIST
    # --------------------------------------------------------

    if (
        low in (
            "list",
            "post list",
            "auto post list",
        )
        or "পোস্ট লিস্ট" in low
    ):
        await update.message.reply_text(
            owner_reply(
                list_posts_text()
            )
        )

        return True

    # --------------------------------------------------------
    # CLEAR POSTS
    # --------------------------------------------------------

    if (
        low in (
            "clear",
            "clear posts",
            "clear all auto posts",
        )
        or "সব অটো পোস্ট মুছে দাও" in low
    ):
        clear_posts()

        await update.message.reply_text(
            owner_reply(
                "🗑️ সব Auto Post মুছে দেওয়া হয়েছে।"
            )
        )

        return True

    # --------------------------------------------------------
    # DELETE POST
    # --------------------------------------------------------

    delete_match = re.search(
        r"(?:delete|del|মুছে|ডিলিট)\s*(?:post)?\s*#?(\d+)",
        raw,
        flags=re.I
    )

    if delete_match:

        post_id = delete_match.group(1)

        if delete_post(post_id):
            result = (
                f"🗑️ Auto Post #{post_id} "
                f"delete করা হয়েছে।"
            )
        else:
            result = (
                f"❌ Auto Post #{post_id} পাওয়া যায়নি।"
            )

        await update.message.reply_text(
            owner_reply(result)
        )

        return True

    # --------------------------------------------------------
    # ADD GROUP
    # --------------------------------------------------------

    if (
        low in (
            "add group",
            "addgroup",
            "গ্রুপ যোগ করো",
            "এই গ্রুপ add করো",
        )
    ):

        chat = update.effective_chat

        if not is_real_group_chat(chat):
            await update.message.reply_text(
                owner_reply(
                    "এই commandটি group-এর ভিতর থেকে "
                    "দিতে হবে।"
                )
            )

            return True

        ok, result = add_group(chat)

        await update.message.reply_text(
            owner_reply(result)
        )

        return True

    # --------------------------------------------------------
    # BROADCAST NATURAL
    # --------------------------------------------------------

    if low.startswith(
        "broadcast:"
    ):

        message = raw.split(
            ":",
            1
        )[1].strip()

        if not message:
            return True

        sent, failed = await send_post_to_groups(
            update.get_bot().application,
            message
        )

        await update.message.reply_text(
            owner_reply(
                f"📢 Broadcast complete.\n\n"
                f"📤 Sent: {sent}\n"
                f"❌ Failed: {failed}"
            )
        )

        return True

    # --------------------------------------------------------
    # SCHEDULE NATURAL POST
    # --------------------------------------------------------

    post_time, post_text = extract_time_and_text(
        raw
    )

    if post_time and post_text:

        ai_post = await create_ai_post(
            post_text
        )

        post = add_post(
            post_time=post_time,
            text=ai_post
        )

        await update.message.reply_text(
            owner_reply(
                f"✅ Auto Post added.\n\n"
                f"🆔 #{post['id']}\n"
                f"⏰ {post_time}\n\n"
                f"{ai_post}"
            )
        )

        return True

    # --------------------------------------------------------
    # UNKNOWN OWNER MESSAGE
    #
    # IMPORTANT:
    # It does NOT automatically post.
    # --------------------------------------------------------

    if not OWNER_SMS_TO_GROUP:

        answer = await ask_gemini(
            raw
        )

        user_last_ai_reply[
            update.effective_user.id
        ] = answer

        await update.message.reply_text(
            owner_reply(answer)
        )

        return True

    # --------------------------------------------------------
    # OWNER SMS TO GROUP IS ON
    # --------------------------------------------------------

    ai_post = await create_ai_post(
        raw
    )

    sent, failed = await send_post_to_groups(
        update.get_bot().application,
        ai_post
    )

    if sent == 0:

        await update.message.reply_text(
            owner_reply(
                "⚠️ SMS → Group ON আছে, "
                "কিন্তু কোনো active group পাওয়া যায়নি।\n\n"
                "Group-এর ভিতর থেকে /addgroup দিন।"
            )
        )

    else:

        await update.message.reply_text(
            owner_reply(
                f"📲 আপনার SMS Group-এ পাঠানো হয়েছে।\n\n"
                f"📤 Sent: {sent}\n"
                f"❌ Failed: {failed}"
            )
        )

    return True


# ============================================================
# COMMAND: START
# ============================================================

async def start_command(
    update,
    context
):
    register_user(
        update.effective_user
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🤖 AI Chat",
                callback_data="ai"
            ),
            InlineKeyboardButton(
                "ℹ️ About",
                callback_data="about"
            ),
        ],
        [
            InlineKeyboardButton(
                "🌐 Translate",
                callback_data="translate"
            ),
        ],
    ]

    await update.message.reply_text(
        "🤖 RJ TEAM BANGLADESH\n\n"
        "স্বাগতম! আপনার যেকোনো প্রশ্ন লিখুন। "
        "আমি AI দিয়ে উত্তর দেব।\n\n"
        "👑 Owner: @RJteam1",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# HELP
# ============================================================

async def help_command(
    update,
    context
):
    if is_admin(update):

        text = """
👑 বস — Owner Commands

🤖 AI:
 /ai প্রশ্ন

📲 SMS → Group:
 ওনার এসএমএস টু গ্রুপ অন
 ওনার এসএমএস টু গ্রুপ অফ
 ওনার এসএমএস স্ট্যাটাস

👤 User SMS:
 USER_ID SMS ON
 USER_ID SMS OFF
 USER_ID SMS STATUS

📤 Direct group post:
 group এ পোস্ট করো: আপনার লেখা

📨 Private message:
 /sendmsg USER_ID message

📢 Broadcast:
/broadcast message

👥 Groups:
/addgroup
/groups
/delgroup CHAT_ID
/pausegroup CHAT_ID
/renamegroup CHAT_ID নতুন নাম

📝 Auto Post:
/autopost
/list
/delete ID
/clear
/on
/off
/test

🌐 AI:
/translate text
/translate_last
"""

    else:

        text = """
🤖 RJ TEAM AI BOT

/ start — Start
/ help — Help
/ about — About
/ translate — Translate
/ translate_last — Translate last AI reply

সাধারণভাবে আপনার প্রশ্ন লিখলেই AI উত্তর দেবে।
"""

    await update.message.reply_text(
        text
    )


# ============================================================
# ABOUT
# ============================================================

async def about_command(
    update,
    context
):
    await update.message.reply_text(
        ABOUT_TEXT
    )


# ============================================================
# TRANSLATE
# ============================================================

async def translate_command(
    update,
    context
):
    text = ""

    if context.args:
        text = " ".join(
            context.args
        )

    if not text:
        await update.message.reply_text(
            "ব্যবহার:\n"
            "/translate Hello, how are you?"
        )
        return

    prompt = (
        "Translate the following text into "
        "natural Bangla. Return only translation:\n\n"
        + text
    )

    answer = await ask_gemini(
        prompt
    )

    await update.message.reply_text(
        answer
    )


# ============================================================
# TRANSLATE LAST
# ============================================================

async def translate_last_command(
    update,
    context
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

    prompt = (
        "Translate the following into natural Bangla. "
        "Return only translation:\n\n"
        + last
    )

    answer = await ask_gemini(
        prompt
    )

    await update.message.reply_text(
        answer
    )


# ============================================================
# /POST
# ============================================================

async def post_command(
    update,
    context
):
    if not is_admin(update):
        await update.message.reply_text(
            "❌ এই command শুধু Owner-এর জন্য।"
        )
        return

    text = ""

    if context.args:
        text = " ".join(
            context.args
        )

    if not text:
        await update.message.reply_text(
            "ব্যবহার:\n"
            "/post আপনার পোস্ট"
        )
        return

    ai_post = await create_ai_post(
        text
    )

    photo_id = None

    if update.message.reply_to_message:
        replied = update.message.reply_to_message

        if replied.photo:
            photo_id = replied.photo[-1].file_id

    sent, failed = await send_post_to_groups(
        update.get_bot().application,
        ai_post,
        photo_id=photo_id
    )

    await update.message.reply_text(
        owner_reply(
            f"📤 Post complete.\n\n"
            f"Sent: {sent}\n"
            f"Failed: {failed}"
        )
    )


# ============================================================
# /AI
# ============================================================

async def ai_command(
    update,
    context
):
    if not is_admin(update):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    text = " ".join(
        context.args
    ).strip()

    if not text:
        await update.message.reply_text(
            "ব্যবহার:\n/ai আপনার প্রশ্ন"
        )
        return

    answer = await ask_gemini(
        text
    )

    user_last_ai_reply[
        update.effective_user.id
    ] = answer

    await update.message.reply_text(
        owner_reply(answer)
    )


# ============================================================
# /ADDGROUP
# ============================================================

async def addgroup_command(
    update,
    context
):
    if not is_admin(update):
        return

    chat = update.effective_chat

    if not is_real_group_chat(chat):
        await update.message.reply_text(
            owner_reply(
                "⚠️ /addgroup অবশ্যই group/supergroup-এর "
                "ভিতর থেকে দিতে হবে।\n\n"
                "Private chat থেকে দিলে user ID "
                "group হিসেবে save হবে না।"
            )
        )
        return

    ok, result = add_group(
        chat
    )

    await update.message.reply_text(
        owner_reply(result)
    )


# ============================================================
# /GROUPS
# ============================================================

async def groups_command(
    update,
    context
):
    if not is_admin(update):
        return

    groups = active_groups()

    if not groups:
        text = "📭 কোনো group নেই।"

    else:
        lines = [
            "📋 RJ Team Groups",
            ""
        ]

        for i, group in enumerate(
            groups,
            start=1
        ):
            lines.append(
                f"{i}. {group['title']}\n"
                f"🆔 {group['chat_id']}"
            )

        text = "\n\n".join(lines)

    await update.message.reply_text(
        owner_reply(text)
    )


# ============================================================
# /DELGROUP
# ============================================================

async def delgroup_command(
    update,
    context
):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text(
            "ব্যবহার:\n/delgroup CHAT_ID"
        )
        return

    chat_id = context.args[0]

    if delete_group(chat_id):
        text = (
            f"✅ Group {chat_id} "
            f"delete করা হয়েছে।"
        )
    else:
        text = (
            f"❌ Group {chat_id} "
            f"পাওয়া যায়নি।"
        )

    await update.message.reply_text(
        owner_reply(text)
    )


# ============================================================
# /STATUS
# ============================================================

async def status_command(
    update,
    context
):
    if not is_admin(update):
        return

    groups = active_groups()
    posts = autopost_data.get(
        "posts",
        []
    )

    await update.message.reply_text(
        owner_reply(
            f"🤖 RJ Team Status\n\n"
            f"Auto Post: "
            f"{'🟢 ON' if autopost_data.get('enabled') else '🔴 OFF'}\n"
            f"Owner SMS → Group: "
            f"{'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n"
            f"Groups: {len(groups)}\n"
            f"Posts: {len(posts)}\n"
            f"Time: {now_bd().strftime('%Y-%m-%d %I:%M:%S %p')}"
        )
    )


# ============================================================
# /PAUSEGROUP
# ============================================================

async def pausegroup_command(
    update,
    context
):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text(
            "ব্যবহার:\n"
            "/pausegroup CHAT_ID"
        )
        return

    chat_id = parse_chat_id(
        context.args[0]
    )

    if chat_id is None:
        await update.message.reply_text(
            "❌ Invalid CHAT_ID"
        )
        return

    group = autopost_data.get(
        "groups",
        {}
    ).get(
        str(chat_id)
    )

    if not group:
        await update.message.reply_text(
            "❌ Group পাওয়া যায়নি।"
        )
        return

    group["active"] = not group.get(
        "active",
        True
    )

    save_autopost_data()

    status = (
        "🟢 Active"
        if group["active"]
        else "🔴 Paused"
    )

    await update.message.reply_text(
        owner_reply(
            f"{group.get('title', 'Group')}\n"
            f"Status: {status}"
        )
    )


# ============================================================
# /RENAMEGROUP
# ============================================================

async def renamegroup_command(
    update,
    context
):
    if not is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "ব্যবহার:\n"
            "/renamegroup CHAT_ID New Name"
        )
        return

    chat_id = context.args[0]
    new_name = " ".join(
        context.args[1:]
    ).strip()

    group = autopost_data.get(
        "groups",
        {}
    ).get(
        str(chat_id)
    )

    if not group:
        await update.message.reply_text(
            "❌ Group পাওয়া যায়নি।"
        )
        return

    group["title"] = new_name

    save_autopost_data()

    await update.message.reply_text(
        owner_reply(
            f"✅ Group name changed:\n"
            f"{new_name}"
        )
    )


# ============================================================
# /BROADCAST
# ============================================================

async def broadcast_command(
    update,
    context
):
    if not is_admin(update):
        return

    message = " ".join(
        context.args
    ).strip()

    if not message:
        await update.message.reply_text(
            "ব্যবহার:\n"
            "/broadcast আপনার message"
        )
        return

    sent, failed = await send_post_to_groups(
        update.get_bot().application,
        message
    )

    await update.message.reply_text(
        owner_reply(
            f"📢 Broadcast complete.\n\n"
            f"📤 Sent: {sent}\n"
            f"❌ Failed: {failed}"
        )
    )


# ============================================================
# /LIST
# ============================================================

async def list_command(
    update,
    context
):
    if not is_admin(update):
        return

    await update.message.reply_text(
        owner_reply(
            list_posts_text()
        )
    )


# ============================================================
# /DELETE
# ============================================================

async def delete_command(
    update,
    context
):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text(
            "ব্যবহার:\n/delete ID"
        )
        return

    post_id = context.args[0]

    if delete_post(post_id):
        text = (
            f"🗑️ Post #{post_id} deleted."
        )
    else:
        text = (
            f"❌ Post #{post_id} not found."
        )

    await update.message.reply_text(
        owner_reply(text)
    )


# ============================================================
# /CLEAR
# ============================================================

async def clear_command(
    update,
    context
):
    if not is_admin(update):
        return

    clear_posts()

    await update.message.reply_text(
        owner_reply(
            "🗑️ সব Auto Posts delete করা হয়েছে।"
        )
    )


# ============================================================
# /ON
# ============================================================

async def on_command(
    update,
    context
):
    if not is_admin(update):
        return

    autopost_data["enabled"] = True
    save_autopost_data()

    await update.message.reply_text(
        owner_reply(
            "🟢 Auto Post ON."
        )
    )


# ============================================================
# /OFF
# ============================================================

async def off_command(
    update,
    context
):
    if not is_admin(update):
        return

    autopost_data["enabled"] = False
    save_autopost_data()

    await update.message.reply_text(
        owner_reply(
            "🔴 Auto Post OFF."
        )
    )


# ============================================================
# /TEST
# ============================================================

async def test_command(
    update,
    context
):
    if not is_admin(update):
        return

    message = (
        "🤖 RJ TEAM BANGLADESH\n\n"
        "✅ Auto Post Test Successful\n"
        f"🕐 {now_bd().strftime('%I:%M %p')}"
    )

    sent, failed = await send_post_to_groups(
        update.get_bot().application,
        message
    )

    await update.message.reply_text(
        owner_reply(
            f"🧪 Test complete.\n\n"
            f"Sent: {sent}\n"
            f"Failed: {failed}"
        )
    )


# ============================================================
# /AUTOPOST
# ============================================================

async def autopost_command(
    update,
    context
):
    if not is_admin(update):
        return

    await update.message.reply_text(
        owner_reply(
            f"📅 Auto Post\n\n"
            f"Status: "
            f"{'🟢 ON' if autopost_data.get('enabled') else '🔴 OFF'}\n"
            f"Groups: {len(active_groups())}\n"
            f"Posts: {len(autopost_data.get('posts', []))}\n\n"
            f"{list_posts_text()}"
        )
    )


# ============================================================
# /SENDMSG
# ============================================================

async def sendmsg_command(
    update,
    context
):
    if not is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            owner_reply(
                "ব্যবহার:\n"
                "/sendmsg USER_ID message\n\n"
                "উদাহরণ:\n"
                "/sendmsg 123456789 Hello"
            )
        )
        return

    target = context.args[0]

    message = " ".join(
        context.args[1:]
    ).strip()

    target_id = None

    # Numeric Telegram ID
    if target.lstrip("-").isdigit():
        target_id = int(target)

    else:
        # Registered username
        username = target.lower()

        if not username.startswith("@"):
            username = "@" + username

        target_id = USER_REGISTRY.get(
            username
        )

    if target_id is None:
        await update.message.reply_text(
            owner_reply(
                "❌ User পাওয়া যায়নি।\n\n"
                "Numeric USER_ID ব্যবহার করুন।\n"
                "User-কে আগে bot /start করতে হবে।"
            )
        )
        return

    try:

        await update.get_bot().send_message(
            chat_id=target_id,
            text=message
        )

        await update.message.reply_text(
            owner_reply(
                f"✅ Message sent.\n"
                f"👤 {target}"
            )
        )

    except Exception as e:

        logger.warning(
            "Private message failed: %s",
            e
        )

        await update.message.reply_text(
            owner_reply(
                "❌ Message পাঠানো যায়নি।\n\n"
                "User আগে bot-এ /start করেছে কি না "
                "চেক করুন।"
            )
        )


# ============================================================
# PHOTO MESSAGE
# ============================================================

async def handle_photo_message(
    update,
    context
):
    register_user(
        update.effective_user
    )

    if not update.message.photo:
        return

    photo_id = update.message.photo[-1].file_id

    caption = (
        update.message.caption or ""
    ).strip()

    # Owner
    if is_admin(update):

        # Explicit group post in caption
        explicit = extract_explicit_group_post(
            caption
        )

        if explicit:

            ai_caption = await create_ai_post(
                explicit
            )

            sent, failed = await send_post_to_groups(
                update.get_bot().application,
                ai_caption,
                photo_id=photo_id
            )

            await update.message.reply_text(
                owner_reply(
                    f"🖼️ Photo post complete.\n\n"
                    f"Sent: {sent}\n"
                    f"Failed: {failed}"
                )
            )

            return

        # Owner SMS-to-group ON
        if OWNER_SMS_TO_GROUP:

            text_for_ai = (
                caption
                if caption
                else
                "এই ছবিটির জন্য একটি সুন্দর "
                "RJ Team Bangladesh পোস্ট তৈরি করুন।"
            )

            ai_caption = await create_ai_post(
                text_for_ai
            )

            sent, failed = await send_post_to_groups(
                update.get_bot().application,
                ai_caption,
                photo_id=photo_id
            )

            await update.message.reply_text(
                owner_reply(
                    f"🖼️ Photo Group-এ পাঠানো হয়েছে.\n\n"
                    f"Sent: {sent}\n"
                    f"Failed: {failed}"
                )
            )

            return

        # OFF: don't auto-post photo
        await update.message.reply_text(
            owner_reply(
                "📴 SMS → Group OFF আছে।\n\n"
                "ছবি Group-এ দিতে caption-এ লিখুন:\n"
                "group এ পোস্ট করো: আপনার লেখা\n\n"
                "অথবা /post ব্যবহার করুন।"
            )
        )

        return

    # Normal user photo
    user_id = update.effective_user.id

    if is_user_sms_to_group_enabled(
        user_id
    ):

        text_for_ai = (
            caption
            if caption
            else
            "এই ছবিটির জন্য একটি সুন্দর "
            "পোস্ট তৈরি করুন।"
        )

        ai_caption = await create_ai_post(
            text_for_ai
        )

        sent, failed = await send_post_to_groups(
            update.get_bot().application,
            ai_caption,
            photo_id=photo_id
        )

        await update.message.reply_text(
            f"📤 Photo processed.\n"
            f"Sent: {sent}\n"
            f"Failed: {failed}"
        )

        return

    await update.message.reply_text(
        "📷 ছবিটি পেয়েছি।"
    )


# ============================================================
# NORMAL MESSAGE
# ============================================================

async def handle_message(
    update,
    context
):
    if not update.message:
        return

    text = (
        update.message.text or ""
    ).strip()

    if not text:
        return

    register_user(
        update.effective_user
    )

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------

    if is_admin(update):

        handled = await handle_owner_natural_command(
            update,
            text
        )

        if handled:
            return

    # --------------------------------------------------------
    # NORMAL USER SMS -> GROUP
    # --------------------------------------------------------

    user_id = update.effective_user.id

    if is_user_sms_to_group_enabled(
        user_id
    ):

        ai_post = await create_ai_post(
            text
        )

        sent, failed = await send_post_to_groups(
            update.get_bot().application,
            ai_post
        )

        await update.message.reply_text(
            f"📤 আপনার message process করা হয়েছে।\n\n"
            f"Sent: {sent}\n"
            f"Failed: {failed}"
        )

        return

    # --------------------------------------------------------
    # NORMAL AI CHAT
    # --------------------------------------------------------

    answer = await ask_gemini(
        text
    )

    user_last_ai_reply[
        user_id
    ] = answer

    await update.message.reply_text(
        answer
    )


# ============================================================
# CALLBACK
# ============================================================

async def callback_handler(
    update,
    context
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    if query.data == "ai":

        await query.message.reply_text(
            "🤖 আমাকে যেকোনো প্রশ্ন লিখে পাঠান।"
        )

    elif query.data == "about":

        await query.message.reply_text(
            ABOUT_TEXT
        )

    elif query.data == "translate":

        await query.message.reply_text(
            "🌐 Translate করতে:\n"
            "/translate আপনার text"
        )


# ============================================================
# AUTO POST WORKER
# ============================================================

async def autopost_worker(
    application
):
    logger.info(
        "Auto Post worker started."
    )

    last_sent = {}

    while True:

        try:

            await asyncio.sleep(
                20
            )

            if not autopost_data.get(
                "enabled",
                False
            ):
                continue

            current = now_bd()

            current_time = current.strftime(
                "%H:%M"
            )

            current_date = current.strftime(
                "%Y-%m-%d"
            )

            for post in autopost_data.get(
                "posts",
                []
            ):

                if not post.get(
                    "enabled",
                    True
                ):
                    continue

                post_time = post.get(
                    "post_time"
                )

                if post_time != current_time:
                    continue

                marker = (
                    f"{current_date}:"
                    f"{post.get('id')}"
                )

                if last_sent.get(
                    marker
                ):
                    continue

                text = (
                    post.get("text")
                    or post.get("caption")
                    or ""
                )

                if not text:
                    continue

                group_ids = post.get(
                    "group_ids",
                    []
                )

                if not group_ids:
                    group_ids = None

                sent, failed = await send_post_to_groups(
                    application,
                    text,
                    photo_id=post.get(
                        "photo_id"
                    ),
                    specific_group_ids=group_ids
                )

                last_sent[marker] = True

                logger.info(
                    "Auto Post #%s sent=%s failed=%s",
                    post.get("id"),
                    sent,
                    failed
                )

        except asyncio.CancelledError:
            break

        except Exception as e:

            logger.exception(
                "Auto Post worker error: %s",
                e
            )

            await asyncio.sleep(
                5
            )


# ============================================================
# POST INIT
# ============================================================

async def post_init(
    application
):
    global scheduler_task

    scheduler_task = asyncio.create_task(
        autopost_worker(
            application
        )
    )

    logger.info(
        "RJ Team bot post_init complete."
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context
):
    logger.exception(
        "Telegram error: %s",
        context.error
    )


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"RJ Team AI Bot is running."
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def start_health_server():
    try:

        server = HTTPServer(
            (
                "0.0.0.0",
                PORT
            ),
            HealthHandler
        )

        logger.info(
            "Health server running on port %s",
            PORT
        )

        server.serve_forever()

    except Exception as e:

        logger.exception(
            "Health server failed: %s",
            e
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    init_firebase()
    load_autopost_data()
    init_gemini()

    # Render health server
    Thread(
        target=start_health_server,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # --------------------------------------------------------
    # PUBLIC COMMANDS
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
    # OWNER COMMANDS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "post",
            post_command
        )
    )

    application.add_handler(
        CommandHandler(
            "ai",
            ai_command
        )
    )

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
            "sendmsg",
            sendmsg_command
        )
    )

    # --------------------------------------------------------
    # CALLBACK
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo_message
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

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "RJ TEAM BANGLADESH AI BOT starting..."
    )

    # Polling is the safest Render setup.
    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
