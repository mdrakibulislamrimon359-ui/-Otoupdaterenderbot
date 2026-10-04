# ============================================================
# 👑 RJ TEAM BANGLADESH - PREMIUM AI BOT
# 💎 VIP GOLD MAX EDITION
# ============================================================
#
# FEATURES
# ------------------------------------------------------------
# ✅ Gemini AI Chat
# ✅ Owner: @RJteam1
# ✅ Owner কে সব Reply-তে "বস" বলা হবে
# ✅ Owner normal SMS -> Gemini AI
# ✅ Owner SMS -> Group ON/OFF
# ✅ Specific User ID -> SMS ON/OFF
# ✅ Explicit Group Post
# ✅ /post
# ✅ /broadcast
# ✅ /sendmsg
# ✅ /addgroup
# ✅ /delgroup
# ✅ /groups
# ✅ /test
# ✅ Auto Post ON/OFF
# ✅ Scheduled Auto Post
# ✅ Add/Delete/List/Clear Posts
# ✅ Photo Scheduled Post
# ✅ Firebase + Local JSON Backup
# ✅ User Registry
# ✅ Translate
# ✅ Translate Last
# ✅ Render Health Server
# ✅ Bangladesh Timezone
# ============================================================

import os
import re
import json
import html
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
# 👑 BASIC CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "RJteam1"
).strip().lstrip("@")

ADMIN_USER_ID_RAW = os.getenv(
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
# 🇧🇩 BANGLADESH TIME
# ============================================================

BD = ZoneInfo("Asia/Dhaka")


# ============================================================
# 👑 OWNER
# ============================================================

OWNER_USERNAME = "@" + ADMIN_USERNAME

try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_RAW) if ADMIN_USER_ID_RAW else None
except Exception:
    ADMIN_USER_ID = None


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


# ============================================================
# 🧠 AI PROMPTS
# ============================================================

SYSTEM_PROMPT = """
তুমি RJ TEAM BANGLADESH-এর Premium AI Assistant।

তোমার আচরণ:
- স্বাভাবিক, ভদ্র এবং বন্ধুসুলভ হবে।
- বাংলা প্রশ্নের উত্তর বাংলায় দেবে।
- Banglish হলে সহজ Banglish/বাংলায় উত্তর দিতে পারো।
- প্রয়োজন হলে English ব্যবহার করবে।
- উত্তর পরিষ্কার ও সুন্দর হবে।
- অযথা অনেক বড় উত্তর দেবে না।
- ব্যবহারকারী যদি প্রযুক্তি/কোডিং প্রশ্ন করে, ধাপে ধাপে সাহায্য করবে।
- ভুল তথ্য বানিয়ে বলবে না।
- Owner @RJteam1-এর সাথে কথা বলার সময় তাকে "বস" বলে সম্বোধন করবে।
"""

POST_SYSTEM_PROMPT = """
তুমি RJ TEAM BANGLADESH-এর Premium Social Post Writer।

কাজ:
- দেওয়া তথ্য থেকে সুন্দর Telegram/Group post তৈরি করা।
- Premium এবং সুন্দর Unicode emoji ব্যবহার করা।
- পরিষ্কার heading এবং spacing রাখা।
- কোনো তথ্য নিজের থেকে বানিয়ে যোগ করা যাবে না।
- অযথা অতিরিক্ত লম্বা করা যাবে না।
- ব্যবহারকারীর মূল বক্তব্য ঠিক রাখতে হবে।
"""


# ============================================================
# 🌐 GLOBALS
# ============================================================

gemini_client = None
firebase_db = None

scheduler_task = None
health_thread = None

user_last_ai_reply = {}

OWNER_SMS_TO_GROUP = False

USER_SMS_TO_GROUP = {}

USER_REGISTRY = {}


# ============================================================
# 📦 DEFAULT DATA
# ============================================================

autopost_data = {
    "enabled": AUTOPOST_ENABLED,
    "groups": {},
    "posts": [],
    "owner_sms_to_group": False,
    "user_sms_to_group": {},
    "user_registry": {},
}


# ============================================================
# 💎 PREMIUM UI
# ============================================================

def vip_header(title="RJ TEAM BANGLADESH"):
    return (
        "╔════════════════════════════╗\n"
        f"        👑 {title}\n"
        "╚════════════════════════════╝"
    )


def vip_footer():
    return (
        "\n\n━━━━━━━━━━━━━━━━━━━━\n"
        "💎 RJ TEAM BANGLADESH\n"
        "👑 PREMIUM AI EXPERIENCE\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


def success_box(message):
    return (
        "╔════════════════════════════╗\n"
        "        ✅ SUCCESS\n"
        "╚════════════════════════════╝\n\n"
        f"{message}"
        f"{vip_footer()}"
    )


def error_box(message):
    return (
        "╔════════════════════════════╗\n"
        "        ❌ ERROR\n"
        "╚════════════════════════════╝\n\n"
        f"{message}"
        f"{vip_footer()}"
    )


def info_box(message):
    return (
        "╔════════════════════════════╗\n"
        "        💎 INFORMATION\n"
        "╚════════════════════════════╝\n\n"
        f"{message}"
        f"{vip_footer()}"
    )


def owner_reply(message):
    return (
        "👑 বস,\n\n"
        f"{message}"
        f"{vip_footer()}"
    )


# ============================================================
# 🔐 OWNER CHECK
# ============================================================

def is_owner(user):
    if not user:
        return False

    # ID is strongest check
    if ADMIN_USER_ID is not None:
        if user.id == ADMIN_USER_ID:
            return True

    username = (user.username or "").strip().lstrip("@").lower()

    if username and username == ADMIN_USERNAME.lower():
        return True

    return False


# ============================================================
# 🔥 FIREBASE
# ============================================================

def init_firebase():
    global firebase_db

    if firebase_db is not None:
        return firebase_db

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        logging.info("Firebase disabled: FIREBASE_SERVICE_ACCOUNT_JSON missing.")
        return None

    try:
        if not firebase_admin._apps:
            service_account_info = json.loads(
                FIREBASE_SERVICE_ACCOUNT_JSON
            )

            cred = credentials.Certificate(
                service_account_info
            )

            firebase_admin.initialize_app(cred)

        firebase_db = firestore.client()

        logging.info("Firebase connected successfully.")

    except Exception as e:
        logging.exception(
            "Firebase initialization failed: %s",
            e
        )

        firebase_db = None

    return firebase_db


# ============================================================
# 💾 LOCAL SAVE
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
        logging.exception(
            "Local save failed: %s",
            e
        )

        return False


# ============================================================
# 📂 LOCAL LOAD
# ============================================================

def load_local():
    global autopost_data
    global OWNER_SMS_TO_GROUP
    global USER_SMS_TO_GROUP
    global USER_REGISTRY

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

        OWNER_SMS_TO_GROUP = bool(
            autopost_data.get(
                "owner_sms_to_group",
                AUTOPOST_ENABLED
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
            str(k): v
            for k, v in autopost_data.get(
                "user_registry",
                {}
            ).items()
        }

    except Exception as e:
        logging.exception(
            "Local load failed: %s",
            e
        )


# ============================================================
# ☁️ FIREBASE LOAD
# ============================================================

def firebase_load():
    global autopost_data
    global OWNER_SMS_TO_GROUP
    global USER_SMS_TO_GROUP
    global USER_REGISTRY

    db = init_firebase()

    if db is None:
        return

    try:
        ref = (
            db.collection(
                AUTOPOST_FIREBASE_COLLECTION
            )
            .document(
                AUTOPOST_FIREBASE_DOCUMENT
            )
        )

        snap = ref.get()

        if not snap.exists:
            return

        data = snap.to_dict() or {}

        if isinstance(data, dict):
            autopost_data.update(data)

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
            str(k): v
            for k, v in autopost_data.get(
                "user_registry",
                {}
            ).items()
        }

        logging.info("Firebase data loaded.")

    except Exception as e:
        logging.exception(
            "Firebase load failed: %s",
            e
        )


# ============================================================
# ☁️ FIREBASE SAVE
# ============================================================

def firebase_save():
    db = init_firebase()

    if db is None:
        return False

    try:
        (
            db.collection(
                AUTOPOST_FIREBASE_COLLECTION
            )
            .document(
                AUTOPOST_FIREBASE_DOCUMENT
            )
            .set(
                autopost_data
            )
        )

        return True

    except Exception as e:
        logging.exception(
            "Firebase save failed: %s",
            e
        )

        return False


# ============================================================
# 💾 SAVE EVERYTHING
# ============================================================

def save_all():
    global autopost_data

    autopost_data["owner_sms_to_group"] = OWNER_SMS_TO_GROUP
    autopost_data["user_sms_to_group"] = USER_SMS_TO_GROUP
    autopost_data["user_registry"] = USER_REGISTRY

    save_local()

    try:
        firebase_save()
    except Exception:
        pass


# ============================================================
# 👤 USER REGISTRY
# ============================================================

def register_user(user):
    if not user:
        return

    uid = str(user.id)

    username = (
        f"@{user.username}"
        if user.username
        else ""
    )

    name = " ".join(
        x for x in [
            user.first_name or "",
            user.last_name or ""
        ]
        if x
    ).strip()

    USER_REGISTRY[uid] = {
        "user_id": user.id,
        "username": username,
        "name": name,
        "updated_at": datetime.now(BD).isoformat(),
    }

    # Username lookup
    if username:
        USER_REGISTRY[
            username.lower()
        ] = {
            "user_id": user.id,
            "username": username,
            "name": name,
            "updated_at": datetime.now(BD).isoformat(),
        }

    autopost_data[
        "user_registry"
    ] = USER_REGISTRY


# ============================================================
# 🤖 GEMINI INIT
# ============================================================

def init_gemini():
    global gemini_client

    if gemini_client is not None:
        return gemini_client

    if not GEMINI_API_KEY:
        logging.error(
            "GEMINI_API_KEY is missing."
        )
        return None

    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        logging.info(
            "Gemini client initialized."
        )

        return gemini_client

    except Exception as e:
        logging.exception(
            "Gemini initialization failed: %s",
            e
        )

        gemini_client = None
        return None


# ============================================================
# 🧠 GEMINI AI
# ============================================================

async def ask_gemini(
    prompt,
    system_prompt=SYSTEM_PROMPT
):
    client = init_gemini()

    if client is None:
        return (
            "দুঃখিত, বস। 😔\n"
            "Gemini API এখন সংযুক্ত নেই।\n"
            "Render Environment Variables থেকে "
            "GEMINI_API_KEY ঠিক আছে কিনা দেখুন।"
        )

    last_error = None

    for model_name in GEMINI_MODELS:

        try:

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=config,
            )

            text = getattr(
                response,
                "text",
                None
            )

            if text:
                return text.strip()

        except Exception as e:
            last_error = e

            logging.warning(
                "Gemini model failed: %s -> %s",
                model_name,
                e
            )

            continue

    logging.exception(
        "All Gemini models failed: %s",
        last_error
    )

    return (
        "দুঃখিত 😔\n"
        "এই মুহূর্তে AI সার্ভারে সমস্যা হচ্ছে। "
        "কিছুক্ষণ পরে আবার চেষ্টা করুন।"
    )


# ============================================================
# ✍️ AI POST WRITER
# ============================================================

async def create_ai_post(text):
    result = await ask_gemini(
        text,
        POST_SYSTEM_PROMPT
    )

    return result


# ============================================================
# ⏰ TIME PARSER
# ============================================================

def parse_time(value):
    value = value.strip().upper()

    formats = [
        "%H:%M",
        "%I:%M %p",
        "%I %p",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt
            ).strftime("%H:%M")

        except ValueError:
            continue

    return None


# ============================================================
# 🆔 POST ID
# ============================================================

def next_post_id():
    posts = autopost_data.get(
        "posts",
        []
    )

    ids = []

    for post in posts:
        try:
            ids.append(
                int(post.get("id", 0))
            )
        except Exception:
            pass

    return max(ids, default=0) + 1


# ============================================================
# 👑 OWNER ONLY CHECK
# ============================================================

async def require_owner(update):
    user = update.effective_user

    if not is_owner(user):

        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ এই Control শুধুমাত্র Owner-এর জন্য।"
            )

        return False

    return True


# ============================================================
# 👥 ADD CURRENT GROUP
# ============================================================

async def add_current_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_owner(update):
        return

    chat = update.effective_chat

    if chat is None:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        await update.effective_message.reply_text(
            error_box(
                "বস, `/addgroup` শুধুমাত্র Group-এর ভিতর "
                "থেকে ব্যবহার করতে পারবেন।"
            )
        )
        return

    chat_id = str(chat.id)

    autopost_data.setdefault(
        "groups",
        {}
    )

    autopost_data["groups"][chat_id] = {
        "id": chat.id,
        "title": chat.title or "Unnamed Group",
        "type": chat.type,
        "added_at": datetime.now(BD).isoformat(),
        "active": True,
    }

    save_all()

    await update.effective_message.reply_text(
        success_box(
            "📌 Group successfully connected!\n\n"
            f"🏷️ Group: {chat.title or 'Unnamed'}\n"
            f"🆔 Group ID: {chat.id}\n\n"
            "✅ Auto Post : Ready\n"
            "✅ Broadcast : Ready\n"
            "✅ AI Post   : Ready\n"
            "✅ Group Sync: Active"
        )
    )


# ============================================================
# 👥 GROUP LIST
# ============================================================

async def groups_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_owner(update):
        return

    groups = autopost_data.get(
        "groups",
        {}
    )

    if not groups:
        await update.effective_message.reply_text(
            info_box(
                "এখনো কোনো Group যুক্ত করা হয়নি।\n\n"
                "যে Group-এ Bot আছে সেখানে:\n"
                "`/addgroup`"
            )
        )
        return

    lines = [
        vip_header("GROUP PANEL"),
        ""
    ]

    for index, (gid, data) in enumerate(
        groups.items(),
        1
    ):
        lines.append(
            f"💎 {index}. "
            f"{data.get('title', 'Unknown')}\n"
            f"🆔 {gid}\n"
            f"📡 Active: "
            f"{'YES' if data.get('active', True) else 'NO'}"
        )

    lines.append(vip_footer())

    await update.effective_message.reply_text(
        "\n\n".join(lines)
    )


# ============================================================
# ❌ DELETE GROUP
# ============================================================

async def delgroup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_owner(update):
        return

    args = context.args

    if args:
        group_id = args[0]
    else:
        group_id = str(
            update.effective_chat.id
        )

    if group_id in autopost_data.get(
        "groups",
        {}
    ):

        name = autopost_data[
            "groups"
        ][group_id].get(
            "title",
            "Group"
        )

        del autopost_data[
            "groups"
        ][group_id]

        save_all()

        await update.effective_message.reply_text(
            success_box(
                f"🗑️ Group removed.\n\n"
                f"🏷️ {name}\n"
                f"🆔 {group_id}"
            )
        )

        return

    await update.effective_message.reply_text(
        error_box(
            "এই Group বর্তমানে তালিকায় নেই।"
        )
    )


# ============================================================
# 📢 SEND TEXT TO GROUPS
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

    for gid, data in list(groups.items()):

        if not data.get(
            "active",
            True
        ):
            continue

        try:
            chat_id = int(gid)

            if (
                exclude_chat_id is not None
                and chat_id == exclude_chat_id
            ):
                continue

            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
            )

            sent += 1

        except Exception as e:
            failed += 1

            logging.warning(
                "Group send failed %s: %s",
                gid,
                e
            )

    return sent, failed


# ============================================================
# 📸 SEND PHOTO TO GROUPS
# ============================================================

async def send_photo_to_groups(
    context,
    photo_file_id,
    caption=""
):

    groups = autopost_data.get(
        "groups",
        {}
    )

    sent = 0
    failed = 0

    for gid, data in list(groups.items()):

        if not data.get(
            "active",
            True
        ):
            continue

        try:
            await context.bot.send_photo(
                chat_id=int(gid),
                photo=photo_file_id,
                caption=caption[:1024]
            )

            sent += 1

        except Exception as e:
            failed += 1

            logging.warning(
                "Photo send failed %s: %s",
                gid,
                e
            )

    return sent, failed


# ============================================================
# 📝 EXPLICIT GROUP POST PARSER
# ============================================================

def extract_group_post(text):

    if not text:
        return None

    patterns = [
        r"^গ্রুপে\s*পোস্ট\s*করো\s*[:：]\s*(.+)$",
        r"^গ্রুপে\s*পোস্ট\s*করুন\s*[:：]\s*(.+)$",
        r"^group\s*এ\s*পোস্ট\s*করো\s*[:：]\s*(.+)$",
        r"^group\s*post\s*[:：]\s*(.+)$",
        r"^post\s*to\s*group\s*[:：]\s*(.+)$",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


# ============================================================
# 📢 OWNER NATURAL CONTROL
# ============================================================

async def owner_text_control(
    update,
    context,
    text
):

    global OWNER_SMS_TO_GROUP
    global USER_SMS_TO_GROUP

    raw = text.strip()
    low = raw.lower()

    # --------------------------------------------------------
    # Explicit group post
    # --------------------------------------------------------

    explicit_post = extract_group_post(raw)

    if explicit_post:

        ai_post = await create_ai_post(
            explicit_post
        )

        sent, failed = await send_to_groups(
            context,
            ai_post
        )

        await update.effective_message.reply_text(
            owner_reply(
                "📢 Group Post সম্পন্ন হয়েছে।\n\n"
                f"✅ Sent: {sent}\n"
                f"❌ Failed: {failed}"
            )
        )

        return True

    # --------------------------------------------------------
    # Owner SMS -> Group OFF
    # --------------------------------------------------------

    off_phrases = [
        "ওনার এসএমএস টু গ্রুপ অফ",
        "ওনার sms to group off",
        "owner sms to group off",
        "sms to group off",
        "sms group off",
        "owner group sms off",
    ]

    if low in off_phrases:

        OWNER_SMS_TO_GROUP = False
        save_all()

        await update.effective_message.reply_text(
            owner_reply(
                "🔴 Owner SMS → Group এখন OFF।\n\n"
                "এখন আপনার সাধারণ SMS-এর উত্তর "
                "Gemini AI থেকে আসবে।\n\n"
                "Group-এ সরাসরি পোস্ট করতে লিখুন:\n"
                "গ্রুপে পোস্ট করো: আপনার বার্তা"
            )
        )

        return True

    # --------------------------------------------------------
    # Owner SMS -> Group ON
    # --------------------------------------------------------

    on_phrases = [
        "ওনার এসএমএস টু গ্রুপ অন",
        "ওনার sms to group on",
        "owner sms to group on",
        "sms to group on",
        "sms group on",
        "owner group sms on",
    ]

    if low in on_phrases:

        OWNER_SMS_TO_GROUP = True
        save_all()

        await update.effective_message.reply_text(
            owner_reply(
                "🟢 Owner SMS → Group এখন ON।\n\n"
                "এখন আপনার সাধারণ SMS AI দিয়ে "
                "Premium Post তৈরি করে সক্রিয় Group-গুলোতে "
                "পাঠানো হবে।"
            )
        )

        return True

    # --------------------------------------------------------
    # Owner SMS STATUS
    # --------------------------------------------------------

    status_phrases = [
        "ওনার এসএমএস স্ট্যাটাস",
        "owner sms status",
        "sms to group status",
        "sms status",
        "owner status",
    ]

    if low in status_phrases:

        await update.effective_message.reply_text(
            owner_reply(
                "📊 Owner SMS Control\n\n"
                f"📢 SMS → Group: "
                f"{'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n"
                f"👥 Groups: "
                f"{len(autopost_data.get('groups', {}))}\n"
                f"⏰ Auto Post: "
                f"{'🟢 ON' if autopost_data.get('enabled') else '🔴 OFF'}"
            )
        )

        return True

    # --------------------------------------------------------
    # User ID SMS ON/OFF
    # Example: 123456789 sms on
    # --------------------------------------------------------

    user_match = re.match(
        r"^(-?\d+)\s+sms\s+(on|off)$",
        low
    )

    if user_match:

        user_id = user_match.group(1)
        action = user_match.group(2)

        # Private Telegram user IDs are normally positive.
        # Negative IDs are group IDs, so reject them here.
        if int(user_id) <= 0:

            await update.effective_message.reply_text(
                owner_reply(
                    "❌ এটি User ID নয়।\n"
                    "শুধু ব্যক্তিগত User ID ব্যবহার করুন।"
                )
            )

            return True

        USER_SMS_TO_GROUP[user_id] = (
            action == "on"
        )

        save_all()

        await update.effective_message.reply_text(
            owner_reply(
                f"👤 User ID: {user_id}\n\n"
                f"SMS → Group: "
                f"{'🟢 ON' if action == 'on' else '🔴 OFF'}"
            )
        )

        return True

    # --------------------------------------------------------
    # User ID SMS STATUS
    # --------------------------------------------------------

    user_status_match = re.match(
        r"^(-?\d+)\s+sms\s+status$",
        low
    )

    if user_status_match:

        user_id = user_status_match.group(1)

        status = USER_SMS_TO_GROUP.get(
            user_id,
            False
        )

        await update.effective_message.reply_text(
            owner_reply(
                f"👤 User ID: {user_id}\n\n"
                f"📢 SMS → Group: "
                f"{'🟢 ON' if status else '🔴 OFF'}"
            )
        )

        return True

    # --------------------------------------------------------
    # Auto Post ON
    # --------------------------------------------------------

    auto_on = [
        "auto post on",
        "autopost on",
        "অটো পোস্ট অন",
        "অটোপোস্ট অন",
    ]

    if low in auto_on:

        autopost_data["enabled"] = True
        save_all()

        await update.effective_message.reply_text(
            owner_reply(
                "🟢 Auto Post চালু হয়েছে।"
            )
        )

        return True

    # --------------------------------------------------------
    # Auto Post OFF
    # --------------------------------------------------------

    auto_off = [
        "auto post off",
        "autopost off",
        "অটো পোস্ট অফ",
        "অটোপোস্ট অফ",
    ]

    if low in auto_off:

        autopost_data["enabled"] = False
        save_all()

        await update.effective_message.reply_text(
            owner_reply(
                "🔴 Auto Post বন্ধ হয়েছে।"
            )
        )

        return True

    # --------------------------------------------------------
    # Group add natural command
    # --------------------------------------------------------

    if low in [
        "group add",
        "add group",
        "গ্রুপ যোগ করো",
        "গ্রুপ অ্যাড করো",
    ]:

        await add_current_group(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # Natural scheduled post
    #
    # Example:
    # schedule 08:00 | Good morning
    # add post 10:30 PM | Hello
    # --------------------------------------------------------

    schedule_match = re.match(
        r"^(?:schedule|add\s*post|পোস্ট\s*যোগ)\s+"
        r"([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)"
        r"\s*(?:\||-)\s*(.+)$",
        raw,
        re.IGNORECASE
    )

    if schedule_match:

        time_value = parse_time(
            schedule_match.group(1)
        )

        post_text = schedule_match.group(2).strip()

        if not time_value:

            await update.effective_message.reply_text(
                owner_reply(
                    "⏰ সময় সঠিক নয়।\n\n"
                    "উদাহরণ:\n"
                    "`08:00 | Good Morning`\n"
                    "`08:30 PM | Good Night`"
                )
            )

            return True

        post = {
            "id": next_post_id(),
            "post_time": time_value,
            "text": post_text,
            "photo_file_id": "",
            "enabled": True,
            "last_run_date": "",
        }

        autopost_data.setdefault(
            "posts",
            []
        ).append(post)

        save_all()

        await update.effective_message.reply_text(
            owner_reply(
                "⏰ Scheduled Post যুক্ত হয়েছে।\n\n"
                f"🆔 Post ID: {post['id']}\n"
                f"🕐 Time: {post['post_time']}\n"
                f"🟢 Status: ON"
            )
        )

        return True

    return False


# ============================================================
# 🟢 AUTO POST ON COMMAND
# ============================================================

async def on_command(
    update,
    context
):

    if not await require_owner(update):
        return

    autopost_data["enabled"] = True
    save_all()

    await update.effective_message.reply_text(
        owner_reply(
            "🟢 Auto Post চালু হয়েছে।"
        )
    )


# ============================================================
# 🔴 AUTO POST OFF COMMAND
# ============================================================

async def off_command(
    update,
    context
):

    if not await require_owner(update):
        return

    autopost_data["enabled"] = False
    save_all()

    await update.effective_message.reply_text(
        owner_reply(
            "🔴 Auto Post বন্ধ হয়েছে।"
        )
    )


# ============================================================
# 📊 STATUS
# ============================================================

async def status_command(
    update,
    context
):

    if not await require_owner(update):
        return

    groups = autopost_data.get(
        "groups",
        {}
    )

    posts = autopost_data.get(
        "posts",
        []
    )

    await update.effective_message.reply_text(
        owner_reply(
            "📊 PREMIUM STATUS\n\n"
            f"📡 Groups: {len(groups)}\n"
            f"📝 Posts: {len(posts)}\n"
            f"⏰ Auto Post: "
            f"{'🟢 ON' if autopost_data.get('enabled') else '🔴 OFF'}\n"
            f"📢 Owner SMS → Group: "
            f"{'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n"
            f"👤 Controlled Users: "
            f"{len(USER_SMS_TO_GROUP)}"
        )
    )


# ============================================================
# 📊 SMS STATUS
# ============================================================

async def smsstatus_command(
    update,
    context
):

    if not await require_owner(update):
        return

    lines = [
        vip_header("SMS CONTROL"),
        "",
        "👑 Owner SMS → Group: "
        + (
            "🟢 ON"
            if OWNER_SMS_TO_GROUP
            else "🔴 OFF"
        ),
        "",
    ]

    if USER_SMS_TO_GROUP:

        for uid, enabled in USER_SMS_TO_GROUP.items():

            lines.append(
                f"👤 {uid} → "
                f"{'🟢 ON' if enabled else '🔴 OFF'}"
            )

    else:
        lines.append(
            "ℹ️ কোনো User SMS control নেই।"
        )

    lines.append(
        vip_footer()
    )

    await update.effective_message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# 📝 LIST POSTS
# ============================================================

async def list_command(
    update,
    context
):

    if not await require_owner(update):
        return

    posts = autopost_data.get(
        "posts",
        []
    )

    if not posts:

        await update.effective_message.reply_text(
            info_box(
                "কোনো Scheduled Post নেই।"
            )
        )

        return

    lines = [
        vip_header("AUTO POST LIST"),
        ""
    ]

    for post in posts:

        post_type = (
            "📸 PHOTO"
            if post.get("photo_file_id")
            else "📝 TEXT"
        )

        lines.append(
            f"🆔 ID: {post.get('id')}\n"
            f"🕐 Time: {post.get('post_time')}\n"
            f"📦 Type: {post_type}\n"
            f"📡 Status: "
            f"{'🟢 ON' if post.get('enabled', True) else '🔴 OFF'}\n"
            f"💬 {post.get('text', '')[:300]}"
        )

        lines.append(
            "━━━━━━━━━━━━━━━━━━━━"
        )

    await update.effective_message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# 🗑️ DELETE POST
# ============================================================

async def delete_command(
    update,
    context
):

    if not await require_owner(update):
        return

    if not context.args:

        await update.effective_message.reply_text(
            owner_reply(
                "ব্যবহার:\n"
                "`/delete POST_ID`\n\n"
                "উদাহরণ:\n"
                "`/delete 1`"
            )
        )

        return

    try:
        post_id = int(
            context.args[0]
        )

    except ValueError:

        await update.effective_message.reply_text(
            error_box(
                "Post ID সঠিক নয়।"
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

    if len(autopost_data["posts"]) == old_count:

        await update.effective_message.reply_text(
            error_box(
                f"Post ID {post_id} পাওয়া যায়নি।"
            )
        )

        return

    save_all()

    await update.effective_message.reply_text(
        owner_reply(
            f"🗑️ Post ID {post_id} সফলভাবে Delete হয়েছে।"
        )
    )


# ============================================================
# 🧹 CLEAR POSTS
# ============================================================

async def clear_command(
    update,
    context
):

    if not await require_owner(update):
        return

    autopost_data["posts"] = []

    save_all()

    await update.effective_message.reply_text(
        owner_reply(
            "🧹 সব Scheduled Post Clear করা হয়েছে।"
        )
    )


# ============================================================
# ⏰ ADD POST
# ============================================================

async def addpost_command(
    update,
    context
):

    if not await require_owner(update):
        return

    raw = update.effective_message.text or ""

    content = raw.split(
        " ",
        1
    )

    if len(content) < 2:

        await update.effective_message.reply_text(
            owner_reply(
                "ব্যবহার:\n\n"
                "`/addpost 08:00 | আপনার বার্তা`\n\n"
                "PM example:\n"
                "`/addpost 08:30 PM | Good Night`"
            )
        )

        return

    value = content[1].strip()

    match = re.match(
        r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)"
        r"\s*\|\s*(.+)$",
        value,
        re.IGNORECASE
    )

    if not match:

        await update.effective_message.reply_text(
            error_box(
                "Format ভুল।\n\n"
                "সঠিক:\n"
                "`/addpost 08:00 | Good Morning`"
            )
        )

        return

    post_time = parse_time(
        match.group(1)
    )

    post_text = match.group(2).strip()

    if not post_time:

        await update.effective_message.reply_text(
            error_box(
                "সময় সঠিক নয়।"
            )
        )

        return

    post = {
        "id": next_post_id(),
        "post_time": post_time,
        "text": post_text,
        "photo_file_id": "",
        "enabled": True,
        "last_run_date": "",
    }

    autopost_data.setdefault(
        "posts",
        []
    ).append(post)

    save_all()

    await update.effective_message.reply_text(
        owner_reply(
            "⏰ Scheduled Post Added!\n\n"
            f"🆔 ID: {post['id']}\n"
            f"🕐 Time: {post['post_time']}\n"
            f"📝 Text: {post['text']}"
        )
    )


# ============================================================
# 📸 ADD PHOTO POST
# ============================================================

async def addphoto_command(
    update,
    context
):

    if not await require_owner(update):
        return

    message = update.effective_message

    if not message.photo:

        await message.reply_text(
            owner_reply(
                "📸 আগে একটি Photo পাঠান।\n\n"
                "Photo-এর Caption এমন রাখুন:\n"
                "`08:30 PM | আপনার Caption`"
            )
        )

        return

    caption = (
        message.caption or ""
    ).strip()

    match = re.match(
        r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)"
        r"\s*\|\s*(.*)$",
        caption,
        re.IGNORECASE
    )

    if not match:

        await message.reply_text(
            error_box(
                "Photo Caption Format ভুল।\n\n"
                "উদাহরণ:\n"
                "`08:30 PM | আজকের বিশেষ পোস্ট`"
            )
        )

        return

    post_time = parse_time(
        match.group(1)
    )

    post_text = match.group(2).strip()

    if not post_time:

        await message.reply_text(
            error_box(
                "সময় সঠিক নয়।"
            )
        )

        return

    photo_id = message.photo[-1].file_id

    post = {
        "id": next_post_id(),
        "post_time": post_time,
        "text": post_text,
        "photo_file_id": photo_id,
        "enabled": True,
        "last_run_date": "",
    }

    autopost_data.setdefault(
        "posts",
        []
    ).append(post)

    save_all()

    await message.reply_text(
        owner_reply(
            "📸 Photo Scheduled Post Added!\n\n"
            f"🆔 ID: {post['id']}\n"
            f"🕐 Time: {post['post_time']}\n"
            "🟢 Status: ON"
        )
    )


# ============================================================
# 📢 /POST
# ============================================================

async def post_command(
    update,
    context
):

    if not await require_owner(update):
        return

    message = update.effective_message

    text = message.text or ""

    parts = text.split(
        " ",
        1
    )

    if len(parts) < 2:

        await message.reply_text(
            owner_reply(
                "ব্যবহার:\n"
                "`/post আপনার বার্তা`"
            )
        )

        return

    raw = parts[1].strip()

    ai_post = await create_ai_post(
        raw
    )

    sent, failed = await send_to_groups(
        context,
        ai_post
    )

    await message.reply_text(
        owner_reply(
            "📢 Group Post Complete!\n\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}"
        )
    )


# ============================================================
# 📣 BROADCAST
# ============================================================

async def broadcast_command(
    update,
    context
):

    if not await require_owner(update):
        return

    message = update.effective_message

    text = message.text or ""

    parts = text.split(
        " ",
        1
    )

    if len(parts) < 2:

        await message.reply_text(
            owner_reply(
                "╔══════════════════════════╗\n"
                "       👑 BROADCAST PANEL\n"
                "╚══════════════════════════╝\n\n"
                "💎 সকল সক্রিয় Group-এ একসাথে\n"
                "📢 Premium Broadcast পাঠানোর সুবিধা।\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📝 ব্যবহার পদ্ধতি\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "`/broadcast আপনার বার্তা`\n\n"
                "✨ উদাহরণ:\n"
                "`/broadcast আজকের বিশেষ ঘোষণা সবাইকে জানানো হলো।`\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🛡️ শুধুমাত্র Owner\n"
                "👑 @RJteam1\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
        )

        return

    broadcast_text = parts[1].strip()

    sent, failed = await send_to_groups(
        context,
        broadcast_text
    )

    await message.reply_text(
        owner_reply(
            "📣 Broadcast Complete!\n\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}"
        )
    )


# ============================================================
# 💬 SEND MESSAGE TO USER
# ============================================================

async def sendmsg_command(
    update,
    context
):

    if not await require_owner(update):
        return

    message = update.effective_message

    text = message.text or ""

    parts = text.split(
        " ",
        2
    )

    if len(parts) < 3:

        await message.reply_text(
            owner_reply(
                "ব্যবহার:\n\n"
                "`/sendmsg USER_ID আপনার বার্তা`\n\n"
                "অথবা registered username:\n"
                "`/sendmsg @username আপনার বার্তা`"
            )
        )

        return

    target = parts[1].strip()
    send_text = parts[2].strip()

    target_data = None

    if target.startswith("@"):

        target_data = USER_REGISTRY.get(
            target.lower()
        )

    else:

        target_data = USER_REGISTRY.get(
            target
        )

    if not target_data:

        await message.reply_text(
            owner_reply(
                "❌ এই User Bot-এর সাথে আগে "
                "ইন্টার‌্যাক্ট করেনি।\n\n"
                "User-কে আগে Bot-এ `/start` দিতে হবে।"
            )
        )

        return

    target_id = target_data.get(
        "user_id"
    )

    try:

        await context.bot.send_message(
            chat_id=int(target_id),
            text=send_text
        )

        await message.reply_text(
            owner_reply(
                "✅ Message পাঠানো হয়েছে।\n\n"
                f"👤 User ID: {target_id}"
            )
        )

    except Exception as e:

        logging.exception(
            "sendmsg failed: %s",
            e
        )

        await message.reply_text(
            error_box(
                "Message পাঠানো যায়নি।\n"
                "User Bot-কে Block করেছে কিনা অথবা "
                "Bot-এর সাথে Start করেছে কিনা পরীক্ষা করুন।"
            )
        )


# ============================================================
# 🧪 TEST
# ============================================================

async def test_command(
    update,
    context
):

    if not await require_owner(update):
        return

    test_text = (
        "╔════════════════════════════╗\n"
        "       👑 RJ TEAM TEST\n"
        "╚════════════════════════════╝\n\n"
        "💎 Group connection successful.\n"
        "📡 Premium AI Bot is active.\n"
        "🇧🇩 Bangladesh Time System Active."
    )

    sent, failed = await send_to_groups(
        context,
        test_text
    )

    await update.effective_message.reply_text(
        owner_reply(
            "🧪 Test Complete!\n\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}"
        )
    )


# ============================================================
# 🌐 TRANSLATE
# ============================================================

async def translate_command(
    update,
    context
):

    message = update.effective_message

    text = message.text or ""

    parts = text.split(
        " ",
        2
    )

    if len(parts) < 3:

        await message.reply_text(
            info_box(
                "ব্যবহার:\n\n"
                "`/translate bn Hello brother`\n"
                "`/translate en আমি ভালো আছি`"
            )
        )

        return

    language = parts[1]
    source_text = parts[2]

    prompt = (
        f"Translate the following text into {language}. "
        "Return only the translation.\n\n"
        f"{source_text}"
    )

    result = await ask_gemini(
        prompt
    )

    user_last_ai_reply[
        message.from_user.id
    ] = result

    await message.reply_text(
        "🌐 TRANSLATION\n\n"
        + result
    )


# ============================================================
# 🔁 TRANSLATE LAST
# ============================================================

async def translate_last_command(
    update,
    context
):

    message = update.effective_message

    if not context.args:

        await message.reply_text(
            info_box(
                "ব্যবহার:\n"
                "`/translate_last bn`"
            )
        )

        return

    language = context.args[0]

    last = user_last_ai_reply.get(
        message.from_user.id
    )

    if not last:

        await message.reply_text(
            error_box(
                "আপনার কোনো আগের AI Reply পাওয়া যায়নি।"
            )
        )

        return

    result = await ask_gemini(
        f"Translate this into {language}. "
        f"Return only the translation:\n\n{last}"
    )

    await message.reply_text(
        "🔁 TRANSLATED LAST REPLY\n\n"
        + result
    )


# ============================================================
# ❌ CANCEL
# ============================================================

async def cancel_command(
    update,
    context
):

    if not await require_owner(update):
        return

    await update.effective_message.reply_text(
        owner_reply(
            "❌ কোনো pending operation ছিল না।"
        )
    )


# ============================================================
# ℹ️ ABOUT
# ============================================================

async def about_command(
    update,
    context
):

    await update.effective_message.reply_text(
        vip_header("ABOUT RJ TEAM") +
        "\n\n"
        "👑 RJ TEAM BANGLADESH\n"
        "💎 Premium AI Bot\n"
        "🤖 Gemini AI Powered\n"
        "🇧🇩 Bangladesh Timezone\n"
        "📡 Multi Group System\n"
        "🔥 Firebase Backup\n"
        + vip_footer()
    )


# ============================================================
# 🆘 HELP
# ============================================================

async def help_command(
    update,
    context
):

    user = update.effective_user

    if is_owner(user):

        text = (
            vip_header("OWNER CONTROL") +
            "\n\n"
            "👑 বস, আপনার Premium Control List:\n\n"

            "📌 GROUP\n"
            "/addgroup — Current Group Add\n"
            "/groups — Group List\n"
            "/delgroup — Group Remove\n"
            "/test — Group Test\n\n"

            "📌 POST\n"
            "/post — AI Group Post\n"
            "/broadcast — Broadcast\n"
            "/addpost — Scheduled Post\n"
            "/addphoto — Photo Scheduled Post\n"
            "/list — Post List\n"
            "/delete ID — Delete Post\n"
            "/clear — Clear Posts\n\n"

            "📌 AUTO POST\n"
            "/on — Auto Post ON\n"
            "/off — Auto Post OFF\n"
            "/autopost — Status\n"
            "/status — Full Status\n\n"

            "📌 USER\n"
            "/sendmsg USER_ID message\n"
            "123456789 sms on\n"
            "123456789 sms off\n"
            "123456789 sms status\n\n"

            "📌 AI\n"
            "/translate bn text\n"
            "/translate_last bn\n\n"

            "💎 Natural Control-ও কাজ করবে।\n"
            "উদাহরণ:\n"
            "`owner sms to group on`\n"
            "`owner sms to group off`\n"
            "`গ্রুপে পোস্ট করো: আপনার লেখা`\n"
            "`schedule 08:00 | Good Morning`"
        )

    else:

        text = (
            vip_header("PREMIUM AI HELP") +
            "\n\n"
            "🤖 আমাকে যেকোনো প্রশ্ন করতে পারেন।\n\n"
            "🌐 Translation:\n"
            "`/translate bn Hello`\n\n"
            "ℹ️ About:\n"
            "`/about`"
        )

    await update.effective_message.reply_text(
        text
    )


# ============================================================
# 🚀 START
# ============================================================

async def start_command(
    update,
    context
):

    user = update.effective_user

    register_user(user)

    save_all()

    if is_owner(user):

        text = (
            "👑 বস, Welcome Back!\n\n"
            "💎 RJ TEAM BANGLADESH Premium AI Bot\n"
            "🤖 Gemini AI: Ready\n"
            "📡 Group System: Ready\n"
            "🔥 Firebase: "
            f"{'Connected' if firebase_db else 'Backup Mode'}\n\n"
            "🛡️ আপনার সব Premium Control সক্রিয় আছে।\n"
            "/help লিখলে Control List দেখতে পারবেন।"
        )

    else:

        text = (
            vip_header("WELCOME") +
            "\n\n"
            "🤖 RJ TEAM Premium AI Bot-এ স্বাগতম।\n\n"
            "💬 আপনার প্রশ্ন লিখুন।\n"
            "আমি AI দিয়ে উত্তর দেওয়ার চেষ্টা করব।\n\n"
            "/help — Help\n"
            "/about — About"
            + vip_footer()
        )

    await update.effective_message.reply_text(
        text
    )


# ============================================================
# 💬 NORMAL TEXT MESSAGE
# ============================================================

async def normal_message(
    update,
    context
):

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    text = (
        message.text or ""
    ).strip()

    if not text:
        return

    register_user(user)

    # Save registry
    save_all()

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------

    if is_owner(user):

        handled = await owner_text_control(
            update,
            context,
            text
        )

        if handled:
            return

        # Owner SMS -> Group ON
        if OWNER_SMS_TO_GROUP:

            ai_post = await create_ai_post(
                text
            )

            sent, failed = await send_to_groups(
                context,
                ai_post
            )

            await message.reply_text(
                owner_reply(
                    "📢 আপনার SMS থেকে Premium AI Post তৈরি করে "
                    "Group-এ পাঠানো হয়েছে।\n\n"
                    f"✅ Sent: {sent}\n"
                    f"❌ Failed: {failed}"
                )
            )

            return

        # Owner normal AI
        answer = await ask_gemini(
            "Owner @RJteam1 বলেছেন:\n\n"
            + text
        )

        user_last_ai_reply[
            user.id
        ] = answer

        await message.reply_text(
            owner_reply(
                answer
            )
        )

        return

    # --------------------------------------------------------
    # NORMAL USER
    # --------------------------------------------------------

    user_id = str(
        user.id
    )

    if USER_SMS_TO_GROUP.get(
        user_id,
        False
    ):

        ai_post = await create_ai_post(
            text
        )

        sent, failed = await send_to_groups(
            context,
            ai_post
        )

        await message.reply_text(
            "💎 আপনার মেসেজ থেকে Premium Post তৈরি করা হয়েছে।\n\n"
            f"📢 Group Sent: {sent}"
        )

        return

    # --------------------------------------------------------
    # NORMAL AI REPLY
    # --------------------------------------------------------

    answer = await ask_gemini(
        text
    )

    user_last_ai_reply[
        user.id
    ] = answer

    await message.reply_text(
        answer
    )


# ============================================================
# 📸 PHOTO HANDLER
# ============================================================

async def photo_handler(
    update,
    context
):

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    register_user(user)
    save_all()

    caption = (
        message.caption or ""
    ).strip()

    photo_id = message.photo[-1].file_id

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------

    if is_owner(user):

        # Scheduled photo format:
        # 08:30 PM | Caption
        schedule_match = re.match(
            r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)"
            r"\s*\|\s*(.*)$",
            caption,
            re.IGNORECASE
        )

        if schedule_match:

            post_time = parse_time(
                schedule_match.group(1)
            )

            post_text = schedule_match.group(2).strip()

            if post_time:

                post = {
                    "id": next_post_id(),
                    "post_time": post_time,
                    "text": post_text,
                    "photo_file_id": photo_id,
                    "enabled": True,
                    "last_run_date": "",
                }

                autopost_data.setdefault(
                    "posts",
                    []
                ).append(post)

                save_all()

                await message.reply_text(
                    owner_reply(
                        "📸 Photo Scheduled Post Added!\n\n"
                        f"🆔 ID: {post['id']}\n"
                        f"🕐 Time: {post_time}\n"
                        "🟢 Status: ON"
                    )
                )

                return

        # Explicit group caption
        explicit = extract_group_post(
            caption
        )

        if explicit:

            ai_caption = await create_ai_post(
                explicit
            )

            sent, failed = await send_photo_to_groups(
                context,
                photo_id,
                ai_caption
            )

            await message.reply_text(
                owner_reply(
                    "📸 Photo Group Post Complete!\n\n"
                    f"✅ Sent: {sent}\n"
                    f"❌ Failed: {failed}"
                )
            )

            return

        # Owner SMS -> Group
        if OWNER_SMS_TO_GROUP:

            base = caption or (
                "এই ছবিটি RJ TEAM BANGLADESH-এর পক্ষ থেকে।"
            )

            ai_caption = await create_ai_post(
                base
            )

            sent, failed = await send_photo_to_groups(
                context,
                photo_id,
                ai_caption
            )

            await message.reply_text(
                owner_reply(
                    "📸 Photo Group Post Complete!\n\n"
                    f"✅ Sent: {sent}\n"
                    f"❌ Failed: {failed}"
                )
            )

            return

        await message.reply_text(
            owner_reply(
                "📸 Photo পেয়েছি, বস।\n\n"
                "Group-এ সরাসরি দিতে চাইলে Caption-এ লিখুন:\n"
                "`গ্রুপে পোস্ট করো: আপনার Caption`"
            )
        )

        return

    # --------------------------------------------------------
    # NORMAL USER PHOTO
    # --------------------------------------------------------

    user_id = str(
        user.id
    )

    if USER_SMS_TO_GROUP.get(
        user_id,
        False
    ):

        base = caption or (
            "একটি নতুন Photo Post"
        )

        ai_caption = await create_ai_post(
            base
        )

        sent, failed = await send_photo_to_groups(
            context,
            photo_id,
            ai_caption
        )

        await message.reply_text(
            "📸 Premium Photo Post তৈরি হয়েছে।\n\n"
            f"📢 Group Sent: {sent}"
        )

        return

    await message.reply_text(
        "📸 Photo received successfully."
    )


# ============================================================
# ⏰ AUTO POST WORKER
# ============================================================

async def autopost_worker(
    application
):

    logging.info(
        "Auto-post worker started."
    )

    while True:

        try:

            if autopost_data.get(
                "enabled",
                True
            ):

                now = datetime.now(BD)

                current_time = now.strftime(
                    "%H:%M"
                )

                today = now.strftime(
                    "%Y-%m-%d"
                )

                posts = autopost_data.get(
                    "posts",
                    []
                )

                changed = False

                for post in posts:

                    if not post.get(
                        "enabled",
                        True
                    ):
                        continue

                    if post.get(
                        "post_time"
                    ) != current_time:
                        continue

                    if post.get(
                        "last_run_date",
                        ""
                    ) == today:
                        continue

                    try:

                        photo_id = post.get(
                            "photo_file_id",
                            ""
                        )

                        post_text = post.get(
                            "text",
                            ""
                        )

                        if photo_id:

                            await send_photo_to_groups(
                                application,
                                photo_id,
                                post_text
                            )

                        else:

                            await send_to_groups(
                                application,
                                post_text
                            )

                        post[
                            "last_run_date"
                        ] = today

                        changed = True

                    except Exception as e:

                        logging.exception(
                            "Auto post failed: %s",
                            e
                        )

                if changed:
                    save_all()

        except Exception as e:

            logging.exception(
                "Auto worker error: %s",
                e
            )

        await asyncio.sleep(
            20
        )


# ============================================================
# 🌐 RENDER HEALTH SERVER
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
            b"RJ TEAM BANGLADESH PREMIUM AI BOT is running."
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def start_health_server():

    global health_thread

    try:

        server = HTTPServer(
            (
                "0.0.0.0",
                PORT
            ),
            HealthHandler
        )

        health_thread = Thread(
            target=server.serve_forever,
            daemon=True
        )

        health_thread.start()

        logging.info(
            "Health server started on port %s",
            PORT
        )

    except Exception as e:

        logging.exception(
            "Health server failed: %s",
            e
        )


# ============================================================
# 🚀 POST INIT
# ============================================================

async def post_init(
    application
):

    global scheduler_task

    init_firebase()

    # Firebase first, local backup second
    firebase_load()

    if not autopost_data.get(
        "groups"
    ):
        load_local()

    # --------------------------------------------------------
    # TARGET_CHAT_ID
    # Optional automatic group IDs
    # --------------------------------------------------------

    if TARGET_CHAT_ID:

        for raw_id in TARGET_CHAT_ID.split(","):

            raw_id = raw_id.strip()

            if not raw_id:
                continue

            try:
                chat_id = int(raw_id)

                # Only negative IDs are accepted as groups.
                if chat_id >= 0:
                    logging.warning(
                        "Ignoring TARGET_CHAT_ID %s: "
                        "not a group/supergroup ID.",
                        chat_id
                    )
                    continue

                key = str(chat_id)

                autopost_data.setdefault(
                    "groups",
                    {}
                )

                if key not in autopost_data["groups"]:

                    autopost_data[
                        "groups"
                    ][key] = {
                        "id": chat_id,
                        "title": "Configured Group",
                        "type": "group",
                        "added_at": datetime.now(BD).isoformat(),
                        "active": True,
                    }

            except Exception:
                logging.warning(
                    "Invalid TARGET_CHAT_ID: %s",
                    raw_id
                )

    save_all()

    if scheduler_task is None:

        scheduler_task = asyncio.create_task(
            autopost_worker(
                application.bot
            )
        )

    logging.info(
        "RJ TEAM BANGLADESH bot initialized."
    )


# ============================================================
# 🔘 CALLBACK
# ============================================================

async def callback_handler(
    update,
    context
):

    query = update.callback_query

    if query:
        await query.answer()


# ============================================================
# ⚠️ ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context
):

    logging.exception(
        "Telegram update error:",
        exc_info=context.error
    )


# ============================================================
# 🚀 MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    logging.basicConfig(
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        level=logging.INFO
    )

    # Load local first
    load_local()

    # Initialize services
    init_firebase()
    init_gemini()

    # Render health server
    start_health_server()

    # --------------------------------------------------------
    # APPLICATION
    # --------------------------------------------------------

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # --------------------------------------------------------
    # BASIC COMMANDS
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

    # --------------------------------------------------------
    # GROUP
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # AUTO POST
    # --------------------------------------------------------

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
            "status",
            status_command
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
            "smsstatus",
            smsstatus_command
        )
    )

    # --------------------------------------------------------
    # POSTS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "post",
            post_command
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
            "addpost",
            addpost_command
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
            "test",
            test_command
        )
    )

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "sendmsg",
            sendmsg_command
        )
    )

    # --------------------------------------------------------
    # TRANSLATION
    # --------------------------------------------------------

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
            "cancel",
            cancel_command
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
            photo_handler
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            normal_message
        )
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    logging.info(
        "=================================================="
    )

    logging.info(
        "👑 RJ TEAM BANGLADESH PREMIUM AI BOT"
    )

    logging.info(
        "👑 Owner: @%s",
        ADMIN_USERNAME
    )

    logging.info(
        "💎 Bot is starting..."
    )

    logging.info(
        "=================================================="
    )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
