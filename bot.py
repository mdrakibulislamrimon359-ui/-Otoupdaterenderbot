# ============================================================
# 👑 RJ TEAM BANGLADESH - PREMIUM AI BOT
# 💎 VIP GOLD MAX EDITION
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
# ⚙️ CONFIGURATION
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
)

AUTOPOST_ENABLED = os.getenv(
    "AUTOPOST_ENABLED",
    "true"
).lower() == "true"

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    ""
).strip()

AUTOPOST_FIREBASE_COLLECTION = os.getenv(
    "AUTOPOST_FIREBASE_COLLECTION",
    "rj_bot_config"
)

AUTOPOST_FIREBASE_DOCUMENT = os.getenv(
    "AUTOPOST_FIREBASE_DOCUMENT",
    "autopost"
)

PORT = int(
    os.getenv("PORT", "10000")
)

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).strip()

BD = ZoneInfo("Asia/Dhaka")

OWNER_USERNAME = "@" + ADMIN_USERNAME


# ============================================================
# 🤖 GEMINI MODELS
# ============================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
]


SYSTEM_PROMPT = """
You are RJ Team Bangladesh Premium AI Assistant.

Always answer naturally and helpfully.

Language:
- If user writes Bangla/Banglish, answer in Bangla/Banglish.
- If user writes English, answer in English unless Bangla is clearly preferred.

Style:
- Premium
- Friendly
- Clear
- Short when possible
- Detailed when necessary
- Never invent facts
- Use useful emojis naturally
- Do not overuse emojis
- Never claim to have performed an action unless it actually happened.

The bot belongs to RJ Team Bangladesh.
Owner username: @RJteam1.
"""


POST_SYSTEM_PROMPT = """
You are the official RJ Team Bangladesh social post writer.

Create attractive premium Telegram/social-media posts.

Style:
- Bangla/Banglish according to input
- VIP premium
- Gold/luxury visual style using Unicode symbols and emojis
- Clear spacing
- Attractive headings
- Do not invent facts
- Do not create fake claims
- Keep the original meaning
"""


# ============================================================
# 🌟 PREMIUM UI
# ============================================================

GOLD = "━━━━━━━━━━━━━━━━━━━━"

def vip_header(title="RJ TEAM BANGLADESH"):
    return (
        "╔══════════════════════════╗\n"
        f"   👑 {title}\n"
        "      💎 VIP PREMIUM\n"
        "╚══════════════════════════╝"
    )


def vip_footer():
    return (
        "\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👑 RJ TEAM BANGLADESH\n"
        "💎 PREMIUM AI EXPERIENCE\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


def success_box(title, body):
    return (
        "╔══════════════════════════╗\n"
        f"  🟡 {title}\n"
        "╚══════════════════════════╝\n\n"
        f"{body}"
        "\n\n✨ সম্পন্ন হয়েছে।"
        + vip_footer()
    )


def error_box(body):
    return (
        "╔══════════════════════════╗\n"
        "  🔴 PREMIUM ALERT\n"
        "╚══════════════════════════╝\n\n"
        f"⚠️ {body}"
        "\n\n💡 অনুগ্রহ করে আবার চেষ্টা করুন।"
        + vip_footer()
    )


def info_box(title, body):
    return (
        "╔══════════════════════════╗\n"
        f"  💎 {title}\n"
        "╚══════════════════════════╝\n\n"
        f"{body}"
        + vip_footer()
    )


def owner_reply(body):
    return (
        "╔══════════════════════════╗\n"
        "   👑 OWNER PREMIUM PANEL\n"
        "╚══════════════════════════╝\n\n"
        f"💛 বস, {body}"
        + vip_footer()
    )


# ============================================================
# 🌐 GLOBAL STATE
# ============================================================

gemini_client = None
firebase_db = None

user_last_ai_reply = {}

OWNER_SMS_TO_GROUP = False

USER_SMS_TO_GROUP = {}

USER_REGISTRY = {}

scheduler_task = None

autopost_data = {
    "enabled": AUTOPOST_ENABLED,
    "groups": {},
    "posts": [],
    "owner_sms_to_group": False,
    "user_sms_to_group": {},
    "user_registry": {},
}


# ============================================================
# 📝 LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("RJ_TEAM_BOT")


# ============================================================
# 🔥 FIREBASE
# ============================================================

def init_firebase():

    global firebase_db

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.info("Firebase service account not configured.")
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
                if os.path.exists(
                    FIREBASE_SERVICE_ACCOUNT_JSON
                ):
                    cred = credentials.Certificate(
                        FIREBASE_SERVICE_ACCOUNT_JSON
                    )

                    firebase_admin.initialize_app(
                        cred
                    )
                else:
                    raise

        firebase_db = firestore.client()

        logger.info("Firebase initialized.")

    except Exception as e:
        logger.exception(
            "Firebase initialization failed: %s",
            e
        )


def firebase_load():

    global autopost_data

    if firebase_db is None:
        return

    try:

        ref = (
            firebase_db
            .collection(AUTOPOST_FIREBASE_COLLECTION)
            .document(AUTOPOST_FIREBASE_DOCUMENT)
        )

        snap = ref.get()

        if snap.exists:

            data = snap.to_dict()

            if isinstance(data, dict):

                autopost_data.update(data)

                logger.info(
                    "Loaded Auto Post data from Firebase."
                )

    except Exception as e:

        logger.exception(
            "Firebase load failed: %s",
            e
        )


def firebase_save():

    if firebase_db is None:
        return

    try:

        ref = (
            firebase_db
            .collection(AUTOPOST_FIREBASE_COLLECTION)
            .document(AUTOPOST_FIREBASE_DOCUMENT)
        )

        ref.set(
            autopost_data,
            merge=True
        )

    except Exception as e:

        logger.exception(
            "Firebase save failed: %s",
            e
        )


# ============================================================
# 💾 LOCAL STORAGE
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

        logger.exception(
            "Local save failed: %s",
            e
        )


def save_all():

    save_local()
    firebase_save()


def load_local():

    global autopost_data

    if not os.path.exists(AUTOPOST_FILE):
        return

    try:

        with open(
            AUTOPOST_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(data, dict):
            autopost_data.update(data)

    except Exception as e:

        logger.exception(
            "Local load failed: %s",
            e
        )


# ============================================================
# 👤 USER REGISTRY
# ============================================================

def register_user(user):

    if not user:
        return

    uid = str(user.id)

    USER_REGISTRY[uid] = {
        "id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_seen": datetime.now(BD).isoformat()
    }

    autopost_data["user_registry"] = USER_REGISTRY

    save_all()


# ============================================================
# 🔐 OWNER CHECK
# ============================================================

def is_owner(user):

    if not user:
        return False

    username = (
        user.username or ""
    ).strip().lstrip("@").lower()

    if username == ADMIN_USERNAME.lower():
        return True

    if ADMIN_USER_ID:

        try:
            return int(user.id) == int(
                ADMIN_USER_ID
            )
        except Exception:
            pass

    return False


# ============================================================
# 🤖 GEMINI INIT
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
            "Gemini client initialized."
        )

    except Exception as e:

        logger.exception(
            "Gemini initialization failed: %s",
            e
        )


async def ask_gemini(prompt):

    if gemini_client is None:

        return (
            "🔴 Gemini AI বর্তমানে প্রস্তুত নয়।\n\n"
            "⚙️ GEMINI_API_KEY configuration "
            "চেক করুন।"
        )

    for model in GEMINI_MODELS:

        try:

            result = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=(
                                    SYSTEM_PROMPT
                                    + "\n\nUSER:\n"
                                    + prompt
                                )
                            )
                        ]
                    )
                ]
            )

            answer = getattr(
                result,
                "text",
                None
            )

            if answer:
                return answer.strip()

        except Exception as e:

            logger.warning(
                "Gemini model %s failed: %s",
                model,
                e
            )

    return (
        "🔴 দুঃখিত বস, এই মুহূর্তে AI response "
        "দেওয়া সম্ভব হচ্ছে না।\n\n"
        "⏳ একটু পরে আবার চেষ্টা করুন।"
    )


async def create_ai_post(prompt):

    if gemini_client is None:
        return await ask_gemini(prompt)

    for model in GEMINI_MODELS:

        try:

            result = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=(
                                    POST_SYSTEM_PROMPT
                                    + "\n\nPOST REQUEST:\n"
                                    + prompt
                                )
                            )
                        ]
                    )
                ]
            )

            answer = getattr(
                result,
                "text",
                None
            )

            if answer:
                return answer.strip()

        except Exception as e:

            logger.warning(
                "Post model failed: %s",
                e
            )

    return prompt


# ============================================================
# 📋 TIME PARSER
# ============================================================

def parse_time(value):

    value = value.strip().upper()

    patterns = [
        "%I:%M %p",
        "%I %p",
        "%H:%M",
    ]

    for fmt in patterns:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            return dt.strftime(
                "%H:%M"
            )

        except ValueError:
            continue

    return None


# ============================================================
# 👥 GROUP MANAGEMENT
# ============================================================

async def add_current_group(update):

    chat = update.effective_chat

    if not chat:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):

        await update.message.reply_text(
            error_box(
                "এই কমান্ডটি শুধুমাত্র Group/Supergroup-এ ব্যবহার করা যাবে।"
            )
        )
        return

    chat_id = str(chat.id)

    autopost_data.setdefault(
        "groups",
        {}
    )

    autopost_data["groups"][chat_id] = {
        "title": chat.title or "Unnamed Group",
        "enabled": True
    }

    save_all()

    await update.message.reply_text(
        success_box(
            "GROUP ADDED",
            f"🟢 গ্রুপ: <b>{chat.title}</b>\n"
            f"🆔 ID: <code>{chat.id}</code>\n\n"
            "📢 এখন এই গ্রুপ Auto Post-এর জন্য প্রস্তুত।"
        ),
        parse_mode="HTML"
    )


async def groups_command(update, context):

    groups = autopost_data.get(
        "groups",
        {}
    )

    if not groups:

        await update.message.reply_text(
            info_box(
                "GROUP LIST",
                "📭 এখনো কোনো Group যুক্ত করা হয়নি।\n\n"
                "➕ একটি Group-এ গিয়ে /addgroup ব্যবহার করুন।"
            )
        )
        return

    text = (
        "╔══════════════════════════╗\n"
        "     📋 CONNECTED GROUPS\n"
        "╚══════════════════════════╝\n\n"
    )

    for i, (gid, data) in enumerate(
        groups.items(),
        1
    ):

        status = (
            "🟢 ACTIVE"
            if data.get("enabled", True)
            else "🔴 OFF"
        )

        text += (
            f"🥇 <b>{i}. {data.get('title', 'Group')}</b>\n"
            f"🆔 <code>{gid}</code>\n"
            f"📡 {status}\n\n"
        )

    await update.message.reply_text(
        text + vip_footer(),
        parse_mode="HTML"
    )


async def delgroup_command(update, context):

    if not is_owner(update.effective_user):
        await update.message.reply_text(
            error_box(
                "এই সুবিধাটি শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    if not context.args:

        await update.message.reply_text(
            info_box(
                "GROUP REMOVE",
                "ব্যবহার:\n"
                "<code>/delgroup GROUP_ID</code>"
            ),
            parse_mode="HTML"
        )
        return

    gid = context.args[0]

    groups = autopost_data.get(
        "groups",
        {}
    )

    if gid not in groups:

        await update.message.reply_text(
            error_box(
                "এই Group ID তালিকায় পাওয়া যায়নি।"
            )
        )
        return

    title = groups[gid].get(
        "title",
        "Group"
    )

    del groups[gid]

    save_all()

    await update.message.reply_text(
        success_box(
            "GROUP REMOVED",
            f"🗑️ <b>{title}</b>\n"
            f"🆔 <code>{gid}</code>\n\n"
            "এই Group আর Auto Post পাবে না।"
        ),
        parse_mode="HTML"
    )


# ============================================================
# 📝 AUTO POST CRUD
# ============================================================

def next_post_id():

    posts = autopost_data.get(
        "posts",
        []
    )

    if not posts:
        return 1

    return max(
        int(p.get("id", 0))
        for p in posts
    ) + 1


async def list_command(update, context):

    posts = autopost_data.get(
        "posts",
        []
    )

    if not posts:

        await update.message.reply_text(
            info_box(
                "AUTO POST LIST",
                "📭 কোনো Auto Post সংরক্ষিত নেই।"
            )
        )
        return

    text = (
        "╔══════════════════════════╗\n"
        "       📝 AUTO POST LIST\n"
        "╚══════════════════════════╝\n\n"
    )

    for p in posts:

        status = (
            "🟢 ACTIVE"
            if p.get("enabled", True)
            else "🔴 OFF"
        )

        text += (
            f"🆔 <b>{p.get('id')}</b>\n"
            f"⏰ সময়: <b>{p.get('time')}</b>\n"
            f"📡 {status}\n"
            f"💬 {p.get('caption', '')[:200]}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
        )

    await update.message.reply_text(
        text + vip_footer(),
        parse_mode="HTML"
    )


async def delete_command(update, context):

    if not is_owner(update.effective_user):

        await update.message.reply_text(
            error_box(
                "এই সুবিধাটি শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    if not context.args:

        await update.message.reply_text(
            info_box(
                "DELETE AUTO POST",
                "ব্যবহার:\n"
                "<code>/delete ID</code>"
            ),
            parse_mode="HTML"
        )
        return

    try:
        post_id = int(
            context.args[0]
        )
    except ValueError:

        await update.message.reply_text(
            error_box(
                "সঠিক Post ID দিন।"
            )
        )
        return

    posts = autopost_data.get(
        "posts",
        []
    )

    old_count = len(posts)

    autopost_data["posts"] = [
        p for p in posts
        if int(p.get("id", 0)) != post_id
    ]

    if len(
        autopost_data["posts"]
    ) == old_count:

        await update.message.reply_text(
            error_box(
                f"Post ID {post_id} পাওয়া যায়নি।"
            )
        )
        return

    save_all()

    await update.message.reply_text(
        success_box(
            "AUTO POST DELETED",
            f"🗑️ Post ID <b>{post_id}</b> সফলভাবে মুছে দেওয়া হয়েছে।"
        ),
        parse_mode="HTML"
    )


async def clear_command(update, context):

    if not is_owner(update.effective_user):

        await update.message.reply_text(
            error_box(
                "এই সুবিধাটি শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    autopost_data["posts"] = []

    save_all()

    await update.message.reply_text(
        success_box(
            "AUTO POST CLEARED",
            "🧹 সকল Auto Post মুছে দেওয়া হয়েছে।"
        )
    )


# ============================================================
# 🟢 AUTO POST ON/OFF
# ============================================================

async def on_command(update, context):

    if not is_owner(update.effective_user):
        await update.message.reply_text(
            error_box(
                "Auto Post control শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    autopost_data["enabled"] = True

    save_all()

    await update.message.reply_text(
        success_box(
            "AUTO POST ON",
            "🟢 Auto Post এখন সক্রিয়।\n\n"
            "📅 নির্ধারিত সময় অনুযায়ী Post পাঠানো হবে।"
        )
    )


async def off_command(update, context):

    if not is_owner(update.effective_user):
        await update.message.reply_text(
            error_box(
                "Auto Post control শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    autopost_data["enabled"] = False

    save_all()

    await update.message.reply_text(
        success_box(
            "AUTO POST OFF",
            "🔴 Auto Post সাময়িকভাবে বন্ধ করা হয়েছে।"
        )
    )


# ============================================================
# 📊 STATUS
# ============================================================

async def status_command(update, context):

    groups = autopost_data.get(
        "groups",
        {}
    )

    posts = autopost_data.get(
        "posts",
        []
    )

    active_groups = sum(
        1
        for x in groups.values()
        if x.get("enabled", True)
    )

    active_posts = sum(
        1
        for x in posts
        if x.get("enabled", True)
    )

    auto_status = (
        "🟢 ACTIVE"
        if autopost_data.get("enabled")
        else "🔴 OFF"
    )

    owner_sms = (
        "🟢 ON"
        if OWNER_SMS_TO_GROUP
        else "🔴 OFF"
    )

    text = (
        "╔══════════════════════════╗\n"
        "       📊 PREMIUM STATUS\n"
        "╚══════════════════════════╝\n\n"
        f"🤖 AI Engine: {'🟢 READY' if gemini_client else '🔴 OFF'}\n"
        f"📅 Auto Post: {auto_status}\n"
        f"👥 Groups: <b>{len(groups)}</b>\n"
        f"🟢 Active Groups: <b>{active_groups}</b>\n"
        f"📝 Total Posts: <b>{len(posts)}</b>\n"
        f"📌 Active Posts: <b>{active_posts}</b>\n"
        f"💬 Owner SMS→Group: {owner_sms}\n"
        f"👤 Registered Users: <b>{len(USER_REGISTRY)}</b>\n"
        f"🔥 Firebase: {'🟢 CONNECTED' if firebase_db else '⚪ NOT CONFIGURED'}\n\n"
        "🕘 Timezone: Asia/Dhaka"
    )

    await update.message.reply_text(
        text + vip_footer(),
        parse_mode="HTML"
    )


# ============================================================
# 💬 SMS STATUS
# ============================================================

async def smsstatus_command(update, context):

    if not is_owner(update.effective_user):

        await update.message.reply_text(
            error_box(
                "SMS Control শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    user_settings = USER_SMS_TO_GROUP

    text = (
        "╔══════════════════════════╗\n"
        "       💬 SMS CONTROL\n"
        "╚══════════════════════════╝\n\n"
        f"👑 Owner SMS→Group: "
        f"{'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n\n"
        f"👤 User Rules: <b>{len(user_settings)}</b>\n"
    )

    for uid, enabled in list(
        user_settings.items()
    )[:20]:

        text += (
            f"\n🆔 <code>{uid}</code> → "
            f"{'🟢 ON' if enabled else '🔴 OFF'}"
        )

    await update.message.reply_text(
        text + vip_footer(),
        parse_mode="HTML"
    )


# ============================================================
# 📢 SEND TO GROUPS
# ============================================================

async def send_to_groups(
    context,
    text,
    exclude_chat_id=None
):

    groups = autopost_data.get(
        "groups",
        {}
    )

    sent = 0
    failed = 0

    for gid, data in groups.items():

        if not data.get(
            "enabled",
            True
        ):
            continue

        if (
            exclude_chat_id
            and str(exclude_chat_id) == str(gid)
        ):
            continue

        try:

            await context.bot.send_message(
                chat_id=int(gid),
                text=text
            )

            sent += 1

        except Exception as e:

            failed += 1

            logger.warning(
                "Group send failed %s: %s",
                gid,
                e
            )

    return sent, failed


# ============================================================
# 📢 EXPLICIT GROUP POST
# ============================================================

def extract_group_post(text):

    patterns = [
        r"^গ্রুপে পোস্ট করো\s*:\s*(.+)$",
        r"^গ্রুপ এ পোস্ট করো\s*:\s*(.+)$",
        r"^group এ পোস্ট করো\s*:\s*(.+)$",
        r"^group এ post করো\s*:\s*(.+)$",
        r"^group post\s*:\s*(.+)$",
    ]

    for pattern in patterns:

        match = re.match(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


# ============================================================
# 👑 OWNER NATURAL CONTROLS
# ============================================================

async def owner_text_control(
    update,
    context,
    raw
):

    global OWNER_SMS_TO_GROUP

    text = raw.strip()
    low = text.lower()

    # --------------------------------------------------------
    # Explicit Group Post
    # --------------------------------------------------------

    post_request = extract_group_post(text)

    if post_request:

        generated = await create_ai_post(
            post_request
        )

        sent, failed = await send_to_groups(
            context,
            generated
        )

        await update.message.reply_text(
            owner_reply(
                "আপনার নির্দেশ অনুযায়ী Group Post তৈরি করে পাঠানো হয়েছে।\n\n"
                f"📢 সফল Group: <b>{sent}</b>\n"
                f"⚠️ Failed: <b>{failed}</b>"
            ),
            parse_mode="HTML"
        )

        return True

    # --------------------------------------------------------
    # Owner SMS OFF
    # --------------------------------------------------------

    off_words = [
        "ওনার এসএমএস টু গ্রুপ অফ",
        "ওনার sms to group off",
        "owner sms to group off",
        "sms to group off",
        "sms group off",
    ]

    if any(
        x in low
        for x in off_words
    ):

        OWNER_SMS_TO_GROUP = False

        autopost_data[
            "owner_sms_to_group"
        ] = False

        save_all()

        await update.message.reply_text(
            owner_reply(
                "আপনার <b>SMS → Group</b> সিস্টেম এখন 🔴 OFF করা হয়েছে।\n\n"
                "💬 এখন আপনার সাধারণ SMS-এর উত্তর AI থেকে আসবে।\n\n"
                "📢 Group-এ নির্দিষ্ট Post পাঠাতে লিখুন:\n"
                "<code>গ্রুপে পোস্ট করো: আপনার লেখা</code>"
            ),
            parse_mode="HTML"
        )

        return True

    # --------------------------------------------------------
    # Owner SMS ON
    # --------------------------------------------------------

    on_words = [
        "ওনার এসএমএস টু গ্রুপ অন",
        "ওনার sms to group on",
        "owner sms to group on",
        "sms to group on",
        "sms group on",
    ]

    if any(
        x in low
        for x in on_words
    ):

        OWNER_SMS_TO_GROUP = True

        autopost_data[
            "owner_sms_to_group"
        ] = True

        save_all()

        await update.message.reply_text(
            owner_reply(
                "আপনার <b>SMS → Group</b> সিস্টেম এখন 🟢 ON করা হয়েছে।\n\n"
                "📢 আপনার পরবর্তী সাধারণ SMS AI দিয়ে Premium Post হিসেবে তৈরি হয়ে সক্রিয় Group-গুলোতে যাবে।"
            ),
            parse_mode="HTML"
        )

        return True

    # --------------------------------------------------------
    # Owner SMS STATUS
    # --------------------------------------------------------

    if (
        "ওনার এসএমএস স্ট্যাটাস" in low
        or "owner sms status" in low
        or "sms to group status" in low
        or "sms status" == low
    ):

        await update.message.reply_text(
            owner_reply(
                f"বর্তমান <b>SMS → Group</b> status: "
                f"{'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}"
            ),
            parse_mode="HTML"
        )

        return True

    # --------------------------------------------------------
    # User ID SMS ON/OFF
    # Example: 123456789 sms on
    # --------------------------------------------------------

    match = re.match(
        r"^(-?\d+)\s+sms\s+(on|off)$",
        low
    )

    if match:

        user_id = match.group(1)
        value = match.group(2) == "on"

        USER_SMS_TO_GROUP[user_id] = value

        autopost_data[
            "user_sms_to_group"
        ] = USER_SMS_TO_GROUP

        save_all()

        await update.message.reply_text(
            owner_reply(
                f"User <code>{user_id}</code>-এর "
                f"SMS → Group system "
                f"{'🟢 ON' if value else '🔴 OFF'} করা হয়েছে।"
            ),
            parse_mode="HTML"
        )

        return True

    # --------------------------------------------------------
    # User ID SMS STATUS
    # --------------------------------------------------------

    match = re.match(
        r"^(-?\d+)\s+sms\s+status$",
        low
    )

    if match:

        user_id = match.group(1)

        value = USER_SMS_TO_GROUP.get(
            user_id,
            False
        )

        await update.message.reply_text(
            owner_reply(
                f"User <code>{user_id}</code>-এর "
                f"SMS → Group: "
                f"{'🟢 ON' if value else '🔴 OFF'}"
            ),
            parse_mode="HTML"
        )

        return True

    # --------------------------------------------------------
    # Auto Post Natural ON/OFF
    # --------------------------------------------------------

    if low in (
        "auto post on",
        "autopost on",
        "অটো পোস্ট অন",
        "অটোপোস্ট অন",
    ):

        autopost_data["enabled"] = True

        save_all()

        await update.message.reply_text(
            owner_reply(
                "Auto Post এখন 🟢 ON।"
            )
        )

        return True

    if low in (
        "auto post off",
        "autopost off",
        "অটো পোস্ট অফ",
        "অটোপোস্ট অফ",
    ):

        autopost_data["enabled"] = False

        save_all()

        await update.message.reply_text(
            owner_reply(
                "Auto Post এখন 🔴 OFF।"
            )
        )

        return True

    # --------------------------------------------------------
    # Natural Status
    # --------------------------------------------------------

    if low in (
        "status",
        "স্ট্যাটাস",
        "বট স্ট্যাটাস",
    ):

        await status_command(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # If Owner SMS→Group OFF:
    # normal AI chat
    # --------------------------------------------------------

    if not OWNER_SMS_TO_GROUP:

        answer = await ask_gemini(
            raw
        )

        user_last_ai_reply[
            update.effective_user.id
        ] = answer

        await update.message.reply_text(
            (
                "╔══════════════════════════╗\n"
                "       🤖 PREMIUM AI\n"
                "╚══════════════════════════╝\n\n"
                f"{answer}"
                + vip_footer()
            )
        )

        return True

    # --------------------------------------------------------
    # Owner SMS→Group ON
    # --------------------------------------------------------

    generated = await create_ai_post(
        raw
    )

    sent, failed = await send_to_groups(
        context,
        generated
    )

    await update.message.reply_text(
        owner_reply(
            "আপনার SMS-টি Premium AI Post হিসেবে তৈরি করা হয়েছে।\n\n"
            f"📢 সফল Group: <b>{sent}</b>\n"
            f"⚠️ Failed: <b>{failed}</b>\n\n"
            "💎 Group Post সম্পন্ন।"
        ),
        parse_mode="HTML"
    )

    return True


# ============================================================
# 👤 NORMAL MESSAGE
# ============================================================

async def normal_message(update, context):

    if not update.message:
        return

    user = update.effective_user

    register_user(user)

    raw = (
        update.message.text or ""
    ).strip()

    if not raw:
        return

    # Owner
    if is_owner(user):

        await owner_text_control(
            update,
            context,
            raw
        )

        return

    # User SMS→Group
    user_id = str(user.id)

    if USER_SMS_TO_GROUP.get(
        user_id,
        False
    ):

        generated = await create_ai_post(
            raw
        )

        sent, failed = await send_to_groups(
            context,
            generated
        )

        await update.message.reply_text(
            (
                "╔══════════════════════════╗\n"
                "      💎 PREMIUM POST\n"
                "╚══════════════════════════╝\n\n"
                "✨ আপনার SMS Premium Post হিসেবে "
                "প্রসেস করা হয়েছে।\n\n"
                f"📢 সফল Group: <b>{sent}</b>\n"
                f"⚠️ Failed: <b>{failed}</b>"
                + vip_footer()
            ),
            parse_mode="HTML"
        )

        return

    # Normal AI
    answer = await ask_gemini(
        raw
    )

    user_last_ai_reply[
        user.id
    ] = answer

    await update.message.reply_text(
        (
            "╔══════════════════════════╗\n"
            "       🤖 RJ PREMIUM AI\n"
            "╚══════════════════════════╝\n\n"
            f"{answer}"
            + vip_footer()
        )
    )


# ============================================================
# 📸 PHOTO HANDLER
# ============================================================

async def photo_handler(update, context):

    if not update.message:
        return

    user = update.effective_user

    register_user(user)

    caption = (
        update.message.caption or ""
    ).strip()

    # Owner
    if is_owner(user):

        explicit = extract_group_post(
            caption
        )

        if explicit:

            generated = await create_ai_post(
                explicit
            )

            photo_id = (
                update.message.photo[-1].file_id
            )

            sent = 0
            failed = 0

            for gid, data in autopost_data.get(
                "groups",
                {}
            ).items():

                if not data.get(
                    "enabled",
                    True
                ):
                    continue

                try:

                    await context.bot.send_photo(
                        chat_id=int(gid),
                        photo=photo_id,
                        caption=generated[:1024]
                    )

                    sent += 1

                except Exception:
                    failed += 1

            await update.message.reply_text(
                owner_reply(
                    f"📸 Photo Post সফলভাবে পাঠানো হয়েছে।\n\n"
                    f"📢 সফল Group: <b>{sent}</b>\n"
                    f"⚠️ Failed: <b>{failed}</b>"
                ),
                parse_mode="HTML"
            )

            return

        if OWNER_SMS_TO_GROUP:

            generated = await create_ai_post(
                caption or "এই Photo-এর জন্য একটি সুন্দর Premium Post তৈরি করুন।"
            )

            photo_id = (
                update.message.photo[-1].file_id
            )

            sent = 0

            for gid, data in autopost_data.get(
                "groups",
                {}
            ).items():

                if not data.get(
                    "enabled",
                    True
                ):
                    continue

                try:

                    await context.bot.send_photo(
                        chat_id=int(gid),
                        photo=photo_id,
                        caption=generated[:1024]
                    )

                    sent += 1

                except Exception:
                    pass

            await update.message.reply_text(
                owner_reply(
                    f"📸 Photo Premium Post হিসেবে "
                    f"<b>{sent}</b>টি Group-এ পাঠানো হয়েছে।"
                ),
                parse_mode="HTML"
            )

            return

        await update.message.reply_text(
            owner_reply(
                "📸 Photo পেয়েছি।\n\n"
                "Group-এ পাঠাতে Caption-এ লিখুন:\n"
                "<code>গ্রুপে পোস্ট করো: আপনার লেখা</code>"
            ),
            parse_mode="HTML"
        )

        return

    # Normal user photo with SMS→Group
    if USER_SMS_TO_GROUP.get(
        str(user.id),
        False
    ):

        generated = await create_ai_post(
            caption or "এই Photo-এর জন্য একটি Premium Post তৈরি করুন।"
        )

        photo_id = (
            update.message.photo[-1].file_id
        )

        sent = 0

        for gid, data in autopost_data.get(
            "groups",
            {}
        ).items():

            if not data.get(
                "enabled",
                True
            ):
                continue

            try:

                await context.bot.send_photo(
                    chat_id=int(gid),
                    photo=photo_id,
                    caption=generated[:1024]
                )

                sent += 1

            except Exception:
                pass

        await update.message.reply_text(
            info_box(
                "PHOTO SENT",
                f"📸 Photo Premium Post হিসেবে "
                f"<b>{sent}</b>টি Group-এ পাঠানো হয়েছে।"
            ),
            parse_mode="HTML"
        )

        return

    await update.message.reply_text(
        info_box(
            "PHOTO RECEIVED",
            "📸 আপনার Photo পেয়েছি।\n\n"
            "💬 Caption সহ পাঠালে AI সেটি বুঝে "
            "উত্তর দিতে পারবে।"
        ),
        parse_mode="HTML"
    )


# ============================================================
# 🚀 START
# ============================================================

async def start_command(update, context):

    register_user(
        update.effective_user
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📖 Help",
                callback_data="help"
            ),
            InlineKeyboardButton(
                "👑 About",
                callback_data="about"
            )
        ],
        [
            InlineKeyboardButton(
                "🤖 AI Chat",
                callback_data="ai"
            )
        ]
    ]

    await update.message.reply_text(
        (
            "╔══════════════════════════╗\n"
            "   👑 RJ TEAM BANGLADESH\n"
            "      💎 VIP PREMIUM AI\n"
            "╚══════════════════════════╝\n\n"
            "🌟 আপনাকে আন্তরিক স্বাগতম!\n\n"
            "🤖 আমি আপনার Premium AI Assistant।\n\n"
            "💬 আমাকে যেকোনো প্রশ্ন করতে পারেন।\n"
            "🧠 AI-এর মাধ্যমে উত্তর পাবেন।\n"
            "📢 Owner-এর জন্য রয়েছে Advanced Group Control।\n"
            "📅 রয়েছে Premium Auto Post System।\n"
            "🌐 রয়েছে Translation System।\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📖 সকল সুবিধা দেখতে /help ব্যবহার করুন।\n"
            "━━━━━━━━━━━━━━━━━━━━"
            + vip_footer()
        ),
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# 📖 HELP
# ============================================================

async def help_command(update, context):

    text = (
        "╔══════════════════════════╗\n"
        "       👑 RJ TEAM BANGLADESH\n"
        "          💎 VIP HELP\n"
        "╚══════════════════════════╝\n\n"

        "🤖 <b>AI SYSTEM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/start — 🤝 বট চালু করুন\n"
        "/help — 📖 সকল সুবিধা দেখুন\n"
        "/about — 👑 Bot সম্পর্কে জানুন\n"
        "/translate — 🌐 অনুবাদ করুন\n"
        "/translate_last — 🔄 সর্বশেষ AI উত্তর অনুবাদ\n\n"

        "📅 <b>AUTO POST</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/autopost — ⚙️ Auto Post Panel\n"
        "/on — 🟢 Auto Post চালু\n"
        "/off — 🔴 Auto Post বন্ধ\n"
        "/list — 📝 Post তালিকা\n"
        "/delete ID — 🗑️ Post Delete\n"
        "/clear — 🧹 সব Post Clear\n\n"

        "👑 <b>OWNER CONTROL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/addgroup — ➕ Group যুক্ত করুন\n"
        "/groups — 📋 Group List\n"
        "/delgroup ID — ❌ Group Remove\n"
        "/status — 📊 System Status\n"
        "/smsstatus — 💬 SMS Status\n"
        "/broadcast — 📢 Broadcast\n"
        "/sendmsg ID MESSAGE — 💌 User Message\n"
        "/test — 🧪 Test Post\n"
        "/cancel — ↩️ Current Action Cancel\n\n"

        "💬 <b>SMART SMS CONTROL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Owner SMS → AI উত্তর\n"
        "Owner SMS → Group Post\n"
        "Specific User → Group Post\n\n"

        "📢 সরাসরি Group Post:\n"
        "<code>গ্রুপে পোস্ট করো: আপনার লেখা</code>\n\n"

        "🔐 <b>OWNER</b>\n"
        f"👑 {OWNER_USERNAME}\n\n"

        "✨ Premium • Smart • Secure"
    )

    await update.message.reply_text(
        text + vip_footer(),
        parse_mode="HTML"
    )


# ============================================================
# ℹ️ ABOUT
# ============================================================

async def about_command(update, context):

    await update.message.reply_text(
        (
            "╔══════════════════════════╗\n"
            "       👑 ABOUT RJ TEAM\n"
            "╚══════════════════════════╝\n\n"
            "💎 RJ Team Bangladesh Premium AI Bot\n\n"
            "🤖 Gemini AI\n"
            "📢 Multi Group System\n"
            "📅 Auto Post\n"
            "🔥 Firebase Backup\n"
            "💾 Local Backup\n"
            "🌐 Translation\n"
            "👑 Owner Control\n"
            "🛡️ Smart Permission System\n\n"
            f"👑 Owner: {OWNER_USERNAME}"
            + vip_footer()
        )
    )


# ============================================================
# 🌐 TRANSLATE
# ============================================================

async def translate_command(update, context):

    if not context.args:

        await update.message.reply_text(
            info_box(
                "TRANSLATE",
                "ব্যবহার:\n"
                "<code>/translate আপনার লেখা</code>"
            ),
            parse_mode="HTML"
        )
        return

    source = " ".join(
        context.args
    )

    answer = await ask_gemini(
        "Translate the following text into natural Bangla. "
        "Return only the translated text.\n\n"
        + source
    )

    await update.message.reply_text(
        (
            "╔══════════════════════════╗\n"
            "        🌐 TRANSLATION\n"
            "╚══════════════════════════╝\n\n"
            f"{answer}"
            + vip_footer()
        )
    )


async def translate_last_command(update, context):

    uid = update.effective_user.id

    answer = user_last_ai_reply.get(
        uid
    )

    if not answer:

        await update.message.reply_text(
            error_box(
                "আপনার জন্য কোনো সর্বশেষ AI উত্তর পাওয়া যায়নি।"
            )
        )
        return

    translated = await ask_gemini(
        "Translate this into natural Bangla. "
        "Return only translation.\n\n"
        + answer
    )

    await update.message.reply_text(
        (
            "╔══════════════════════════╗\n"
            "      🔄 LAST AI TRANSLATION\n"
            "╚══════════════════════════╝\n\n"
            f"{translated}"
            + vip_footer()
        )
    )


# ============================================================
# 💌 SEND MESSAGE
# ============================================================

async def sendmsg_command(update, context):

    if not is_owner(
        update.effective_user
    ):

        await update.message.reply_text(
            error_box(
                "এই command শুধুমাত্র Owner ব্যবহার করতে পারবেন।"
            )
        )
        return

    if len(context.args) < 2:

        await update.message.reply_text(
            info_box(
                "SEND MESSAGE",
                "ব্যবহার:\n"
                "<code>/sendmsg USER_ID MESSAGE</code>\n\n"
                "উদাহরণ:\n"
                "<code>/sendmsg 123456789 Hello</code>"
            ),
            parse_mode="HTML"
        )
        return

    target = context.args[0]

    message = " ".join(
        context.args[1:]
    )

    target_id = None

    if target.lstrip("-").isdigit():

        target_id = int(target)

    else:

        username = target.lstrip("@").lower()

        for data in USER_REGISTRY.values():

            if (
                data.get(
                    "username",
                    ""
                ).lower()
                == username
            ):

                target_id = int(
                    data["id"]
                )

                break

    if target_id is None:

        await update.message.reply_text(
            error_box(
                "এই User-এর ID/Username registry-তে পাওয়া যায়নি।"
            )
        )
        return

    try:

        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "╔══════════════════════════╗\n"
                "       👑 RJ TEAM MESSAGE\n"
                "╚══════════════════════════╝\n\n"
                f"{message}"
                + vip_footer()
            )
        )

        await update.message.reply_text(
            success_box(
                "MESSAGE SENT",
                f"💌 User <code>{target_id}</code>-কে "
                "Premium message পাঠানো হয়েছে।"
            ),
            parse_mode="HTML"
        )

    except Exception as e:

        logger.warning(
            "sendmsg failed: %s",
            e
        )

        await update.message.reply_text(
            error_box(
                "User-কে message পাঠানো যায়নি। "
                "User আগে Bot-এ Start/Interaction করেছে কি না দেখুন।"
            )
        )


# ============================================================
# 📢 BROADCAST
# ============================================================

async def broadcast_command(update, context):

    if not is_owner(
        update.effective_user
    ):

        await update.message.reply_text(
            error_box(
                "Broadcast শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    if not context.args:

        await update.message.reply_text(
            info_box(
                "BROADCAST",
                "ব্যবহার:\n"
                "<code>/broadcast আপনার বার্তা</code>"
            ),
            parse_mode="HTML"
        )
        return

    message = " ".join(
        context.args
    )

    text = (
        "╔══════════════════════════╗\n"
        "       📢 RJ TEAM BROADCAST\n"
        "╚══════════════════════════╝\n\n"
        f"{message}"
        + vip_footer()
    )

    sent, failed = await send_to_groups(
        context,
        text
    )

    await update.message.reply_text(
        owner_reply(
            f"Broadcast সম্পন্ন।\n\n"
            f"📢 সফল: <b>{sent}</b>\n"
            f"⚠️ Failed: <b>{failed}</b>"
        ),
        parse_mode="HTML"
    )


# ============================================================
# 🧪 TEST
# ============================================================

async def test_command(update, context):

    if not is_owner(
        update.effective_user
    ):

        await update.message.reply_text(
            error_box(
                "Test command শুধুমাত্র Owner-এর জন্য।"
            )
        )
        return

    text = (
        "╔══════════════════════════╗\n"
        "       🧪 RJ TEAM TEST\n"
        "╚══════════════════════════╝\n\n"
        "💎 Premium Group Test Message\n\n"
        "🟡 Gold System: ONLINE\n"
        "🤖 AI System: ONLINE\n"
        "📢 Group System: ONLINE\n"
        "📅 Auto Post: ONLINE\n"
        + vip_footer()
    )

    sent, failed = await send_to_groups(
        context,
        text
    )

    await update.message.reply_text(
        owner_reply(
            f"Test সম্পন্ন।\n\n"
            f"📢 সফল: <b>{sent}</b>\n"
            f"⚠️ Failed: <b>{failed}</b>"
        ),
        parse_mode="HTML"
    )


# ============================================================
# ↩️ CANCEL
# ============================================================

async def cancel_command(update, context):

    await update.message.reply_text(
        info_box(
            "CANCEL",
            "↩️ বর্তমানে বাতিল করার মতো কোনো pending action নেই।"
        )
    )


# ============================================================
# 📅 AUTO POST WORKER
# ============================================================

async def autopost_worker(app):

    while True:

        try:

            if not autopost_data.get(
                "enabled",
                True
            ):

                await asyncio.sleep(20)
                continue

            now = datetime.now(BD)

            current_time = now.strftime(
                "%H:%M"
            )

            today = now.strftime(
                "%Y-%m-%d"
            )

            changed = False

            for post in autopost_data.get(
                "posts",
                []
            ):

                if not post.get(
                    "enabled",
                    True
                ):
                    continue

                if post.get(
                    "time"
                ) != current_time:
                    continue

                if post.get(
                    "last_sent"
                ) == today:
                    continue

                caption = post.get(
                    "caption",
                    ""
                )

                photo_id = post.get(
                    "photo_id"
                )

                for gid, data in autopost_data.get(
                    "groups",
                    {}
                ).items():

                    if not data.get(
                        "enabled",
                        True
                    ):
                        continue

                    try:

                        if photo_id:

                            await app.bot.send_photo(
                                chat_id=int(gid),
                                photo=photo_id,
                                caption=caption[:1024]
                            )

                        else:

                            await app.bot.send_message(
                                chat_id=int(gid),
                                text=caption[:4096]
                            )

                    except Exception as e:

                        logger.warning(
                            "Scheduled post failed: %s",
                            e
                        )

                post["last_sent"] = today

                changed = True

            if changed:
                save_all()

        except Exception as e:

            logger.exception(
                "Auto post worker error: %s",
                e
            )

        await asyncio.sleep(20)


# ============================================================
# 🏥 RENDER HEALTH SERVER
# ============================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"RJ TEAM BANGLADESH PREMIUM AI BOT - ONLINE"
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def start_health_server():

    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    server.serve_forever()


# ============================================================
# 🚀 POST INIT
# ============================================================

async def post_init(application):

    global scheduler_task

    scheduler_task = asyncio.create_task(
        autopost_worker(application)
    )

    logger.info(
        "Premium Auto Post worker started."
    )


# ============================================================
# 🔘 CALLBACK BUTTONS
# ============================================================

async def callback_handler(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if query.data == "help":

        text = (
            "📖 /help ব্যবহার করে সকল Premium command দেখতে পারবেন।\n\n"
            "👑 Owner: @RJteam1"
        )

        await query.message.reply_text(
            text + vip_footer()
        )

    elif query.data == "about":

        await query.message.reply_text(
            (
                "👑 <b>RJ TEAM BANGLADESH</b>\n\n"
                "💎 Premium AI Bot\n"
                "🤖 Gemini AI\n"
                "📢 Multi Group\n"
                "📅 Auto Post"
                + vip_footer()
            ),
            parse_mode="HTML"
        )

    elif query.data == "ai":

        await query.message.reply_text(
            info_box(
                "AI CHAT",
                "💬 আপনার প্রশ্ন লিখুন।\n"
                "🤖 Premium AI উত্তর দেবে।"
            )
        )


# ============================================================
# 🔧 MAIN
# ============================================================

def main():

    global OWNER_SMS_TO_GROUP
    global USER_SMS_TO_GROUP
    global USER_REGISTRY

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    load_local()

    OWNER_SMS_TO_GROUP = autopost_data.get(
        "owner_sms_to_group",
        False
    )

    USER_SMS_TO_GROUP = autopost_data.get(
        "user_sms_to_group",
        {}
    )

    USER_REGISTRY = autopost_data.get(
        "user_registry",
        {}
    )

    init_firebase()
    firebase_load()

    OWNER_SMS_TO_GROUP = autopost_data.get(
        "owner_sms_to_group",
        OWNER_SMS_TO_GROUP
    )

    USER_SMS_TO_GROUP = autopost_data.get(
        "user_sms_to_group",
        USER_SMS_TO_GROUP
    )

    USER_REGISTRY = autopost_data.get(
        "user_registry",
        USER_REGISTRY
    )

    init_gemini()

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
    # Commands
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

    application.add_handler(
        CommandHandler(
            "autopost",
            status_command
        )
    )

    application.add_handler(
        CommandHandler(
            "addgroup",
            add_current_group
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
            "smsstatus",
            smsstatus_command
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
            "sendmsg",
            sendmsg_command
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
    # Callback
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # --------------------------------------------------------
    # Photo
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_handler
        )
    )

    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            normal_message
        )
    )

    logger.info(
        "👑 RJ TEAM BANGLADESH PREMIUM AI BOT STARTING..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# ▶️ START
# ============================================================

if __name__ == "__main__":
    main()
