# ============================================================
# 👑 RJ TEAM BANGLADESH - PREMIUM AI BOT
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

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ========================= CONFIG ============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "RJteam1").strip().lstrip("@")
ADMIN_USER_ID_RAW = os.getenv("ADMIN_USER_ID", "").strip()
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "").strip()
AUTOPOST_FILE = os.getenv("AUTOPOST_FILE", "autopost.json").strip()
AUTOPOST_ENABLED = os.getenv("AUTOPOST_ENABLED", "true").lower() in ("1","true","yes","on")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
AUTOPOST_FIREBASE_COLLECTION = os.getenv("AUTOPOST_FIREBASE_COLLECTION", "rj_bot_config").strip()
AUTOPOST_FIREBASE_DOCUMENT = os.getenv("AUTOPOST_FIREBASE_DOCUMENT", "autopost").strip()
PORT = int(os.getenv("PORT", "10000"))

BD = ZoneInfo("Asia/Dhaka")
OWNER_USERNAME = "@" + ADMIN_USERNAME

try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_RAW) if ADMIN_USER_ID_RAW else None
except Exception:
    ADMIN_USER_ID = None

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
]

SYSTEM_PROMPT = """
তুমি RJ TEAM BANGLADESH-এর Premium AI Assistant।
স্বাভাবিক, ভদ্র ও বন্ধুসুলভভাবে উত্তর দেবে।
বাংলা প্রশ্নে বাংলায় উত্তর দেবে; Banglish হলে সহজ বাংলায়/Banglish-এ উত্তর দিতে পারো।
প্রযুক্তি/কোডিং প্রশ্নে পরিষ্কারভাবে সাহায্য করবে।
ভুল তথ্য বানিয়ে বলবে না এবং অযথা বড় উত্তর দেবে না।
Owner @RJteam1-এর সাথে কথা বলার সময় তাকে "বস" বলে সম্বোধন করবে।
"""

POST_SYSTEM_PROMPT = """
তুমি RJ TEAM BANGLADESH-এর Premium Telegram Post Writer।
ব্যবহারকারীর দেওয়া কথার মূল অর্থ ঠিক রেখে সুন্দর, সংক্ষিপ্ত ও আকর্ষণীয় বাংলা Telegram/group caption তৈরি করবে।
প্রয়োজনে heading, spacing ও Unicode emoji ব্যবহার করবে।
নিজে থেকে নতুন তথ্য, link, phone number বা দাবি বানাবে না।
"""

gemini_client = None
firebase_db = None
scheduler_task = None
health_thread = None

OWNER_SMS_TO_GROUP = False
USER_SMS_TO_GROUP = {}
USER_REGISTRY = {}
user_last_ai_reply = {}

autopost_data = {
    "enabled": AUTOPOST_ENABLED,
    "groups": {},
    "posts": [],
    "owner_sms_to_group": False,
    "user_sms_to_group": {},
    "user_registry": {},
}

# ========================= UI ================================

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
    return vip_header("SUCCESS") + "\n\n" + message + vip_footer()

def error_box(message):
    return vip_header("ERROR") + "\n\n" + message + vip_footer()

def info_box(message):
    return vip_header("INFORMATION") + "\n\n" + message + vip_footer()

def owner_reply(message):
    return "👑 বস,\n\n" + message + vip_footer()

# ========================= OWNER ==============================

def is_owner(user):
    if not user:
        return False
    if ADMIN_USER_ID is not None and user.id == ADMIN_USER_ID:
        return True
    return bool(user.username) and user.username.lstrip("@").lower() == ADMIN_USERNAME.lower()

async def require_owner(update):
    if not is_owner(update.effective_user):
        if update.effective_message:
            await update.effective_message.reply_text("⛔ এই Control শুধুমাত্র Owner-এর জন্য।")
        return False
    return True

# ========================= STORAGE ============================

def init_firebase():
    global firebase_db
    if firebase_db is not None:
        return firebase_db
    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        return None
    try:
        if not firebase_admin._apps:
            info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
            firebase_admin.initialize_app(credentials.Certificate(info))
        firebase_db = firestore.client()
    except Exception as e:
        logging.exception("Firebase initialization failed: %s", e)
        firebase_db = None
    return firebase_db

def save_local():
    try:
        with open(AUTOPOST_FILE, "w", encoding="utf-8") as f:
            json.dump(autopost_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logging.exception("Local save failed")
        return False

def load_local():
    global autopost_data, OWNER_SMS_TO_GROUP, USER_SMS_TO_GROUP, USER_REGISTRY
    if not os.path.exists(AUTOPOST_FILE):
        return
    try:
        with open(AUTOPOST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            autopost_data.update(data)
        OWNER_SMS_TO_GROUP = bool(autopost_data.get("owner_sms_to_group", False))
        USER_SMS_TO_GROUP = {str(k): bool(v) for k,v in autopost_data.get("user_sms_to_group", {}).items()}
        USER_REGISTRY = {str(k): v for k,v in autopost_data.get("user_registry", {}).items()}
    except Exception:
        logging.exception("Local load failed")

def firebase_load():
    global autopost_data, OWNER_SMS_TO_GROUP, USER_SMS_TO_GROUP, USER_REGISTRY
    db = init_firebase()
    if db is None:
        return
    try:
        snap = db.collection(AUTOPOST_FIREBASE_COLLECTION).document(AUTOPOST_FIREBASE_DOCUMENT).get()
        if not snap.exists:
            return
        data = snap.to_dict() or {}
        if isinstance(data, dict):
            autopost_data.update(data)
        OWNER_SMS_TO_GROUP = bool(autopost_data.get("owner_sms_to_group", False))
        USER_SMS_TO_GROUP = {str(k): bool(v) for k,v in autopost_data.get("user_sms_to_group", {}).items()}
        USER_REGISTRY = {str(k): v for k,v in autopost_data.get("user_registry", {}).items()}
    except Exception:
        logging.exception("Firebase load failed")

def firebase_save():
    db = init_firebase()
    if db is None:
        return False
    try:
        db.collection(AUTOPOST_FIREBASE_COLLECTION).document(AUTOPOST_FIREBASE_DOCUMENT).set(autopost_data)
        return True
    except Exception:
        logging.exception("Firebase save failed")
        return False

def save_all():
    autopost_data["owner_sms_to_group"] = OWNER_SMS_TO_GROUP
    autopost_data["user_sms_to_group"] = USER_SMS_TO_GROUP
    autopost_data["user_registry"] = USER_REGISTRY
    save_local()
    firebase_save()

# ========================= REGISTRY ===========================

def register_user(user):
    if not user:
        return
    uid = str(user.id)
    username = f"@{user.username}" if user.username else ""
    name = " ".join(x for x in [user.first_name or "", user.last_name or ""] if x).strip()
    data = {
        "user_id": user.id,
        "username": username,
        "name": name,
        "updated_at": datetime.now(BD).isoformat(),
    }
    USER_REGISTRY[uid] = data
    if username:
        USER_REGISTRY[username.lower()] = data
    autopost_data["user_registry"] = USER_REGISTRY

# ========================= GEMINI =============================

def init_gemini():
    global gemini_client
    if gemini_client is not None:
        return gemini_client
    if not GEMINI_API_KEY:
        return None
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        return gemini_client
    except Exception:
        logging.exception("Gemini initialization failed")
        return None

async def ask_gemini(prompt, system_prompt=SYSTEM_PROMPT):
    client = init_gemini()
    if client is None:
        return "দুঃখিত, বস। 😔 Gemini API সংযুক্ত নেই। Render-এর GEMINI_API_KEY পরীক্ষা করুন।"
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
            text = getattr(response, "text", None)
            if text:
                return text.strip()
        except Exception as e:
            last_error = e
            logging.warning("Gemini model failed %s: %s", model_name, e)
    logging.warning("All Gemini models failed: %s", last_error)
    return "দুঃখিত 😔 এই মুহূর্তে AI সার্ভারে সমস্যা হচ্ছে। কিছুক্ষণ পরে আবার চেষ্টা করুন।"

async def create_ai_post(text):
    return await ask_gemini(text, POST_SYSTEM_PROMPT)

# ========================= HELPERS ============================

def parse_time(value):
    value = value.strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            pass
    return None

def next_post_id():
    ids = []
    for p in autopost_data.get("posts", []):
        try:
            ids.append(int(p.get("id", 0)))
        except Exception:
            pass
    return max(ids, default=0) + 1

def renumber_posts():
    for i, post in enumerate(autopost_data.get("posts", []), 1):
        post["id"] = i

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
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip()
    return None

# ========================= GROUPS =============================

async def add_current_group(update, context):
    if not await require_owner(update):
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text(error_box("বস, `/addgroup` Group-এর ভিতর থেকে ব্যবহার করুন।"))
        return
    gid = str(chat.id)
    autopost_data.setdefault("groups", {})[gid] = {
        "id": chat.id,
        "title": chat.title or "Unnamed Group",
        "type": chat.type,
        "added_at": datetime.now(BD).isoformat(),
        "active": True,
    }
    save_all()
    await update.effective_message.reply_text(success_box(
        f"📌 Group connected!\n\n🏷️ {chat.title or 'Unnamed'}\n🆔 {chat.id}\n\n"
        "✅ Auto Post Ready\n✅ Broadcast Ready\n✅ AI Post Ready"
    ))

async def groups_command(update, context):
    if not await require_owner(update):
        return
    groups = autopost_data.get("groups", {})
    if not groups:
        await update.effective_message.reply_text(info_box("কোনো Group যুক্ত নেই। Group-এর ভিতর `/addgroup` দিন।"))
        return
    lines = [vip_header("GROUP PANEL"), ""]
    for i, (gid, data) in enumerate(groups.items(), 1):
        lines.append(
            f"💎 {i}. {data.get('title','Unknown')}\n"
            f"🆔 {gid}\n"
            f"📡 Active: {'YES' if data.get('active', True) else 'NO'}"
        )
    await update.effective_message.reply_text("\n\n".join(lines) + vip_footer())

async def delgroup_command(update, context):
    if not await require_owner(update):
        return
    gid = context.args[0] if context.args else str(update.effective_chat.id)
    groups = autopost_data.get("groups", {})
    if gid not in groups:
        await update.effective_message.reply_text(error_box("এই Group তালিকায় নেই।"))
        return
    name = groups[gid].get("title", "Group")
    del groups[gid]
    save_all()
    await update.effective_message.reply_text(success_box(f"🗑️ Group removed.\n\n🏷️ {name}\n🆔 {gid}"))

# ========================= SEND ===============================

async def send_to_groups(context, text, exclude_chat_id=None):
    sent = failed = 0
    for gid, data in list(autopost_data.get("groups", {}).items()):
        if not data.get("active", True):
            continue
        try:
            cid = int(gid)
            if exclude_chat_id is not None and cid == exclude_chat_id:
                continue
            await context.bot.send_message(chat_id=cid, text=text)
            sent += 1
        except Exception as e:
            failed += 1
            logging.warning("Group send failed %s: %s", gid, e)
    return sent, failed

async def send_photo_to_groups(context, photo_file_id, caption=""):
    sent = failed = 0
    for gid, data in list(autopost_data.get("groups", {}).items()):
        if not data.get("active", True):
            continue
        try:
            await context.bot.send_photo(chat_id=int(gid), photo=photo_file_id, caption=caption[:1024])
            sent += 1
        except Exception as e:
            failed += 1
            logging.warning("Photo send failed %s: %s", gid, e)
    return sent, failed

# ========================= SMS CONTROL ========================

async def smson_command(update, context):
    global OWNER_SMS_TO_GROUP
    if not await require_owner(update):
        return
    OWNER_SMS_TO_GROUP = True
    save_all()
    await update.effective_message.reply_text(owner_reply(
        "🟢 Owner SMS → Group এখন ON।\n\n"
        "এখন আপনি সাধারণ SMS/text পাঠালে AI সুন্দর caption তৈরি করে সক্রিয় Group-গুলোতে পাঠাবে।"
    ))

async def smsoff_command(update, context):
    global OWNER_SMS_TO_GROUP
    if not await require_owner(update):
        return
    OWNER_SMS_TO_GROUP = False
    save_all()
    await update.effective_message.reply_text(owner_reply(
        "🔴 Owner SMS → Group এখন OFF।\n\n"
        "এখন আপনি সাধারণ প্রশ্ন/SMS পাঠালে Bot শুধু Gemini AI-এর উত্তর দেবে।"
    ))

async def smsstatus_command(update, context):
    if not await require_owner(update):
        return
    lines = [
        vip_header("SMS CONTROL"),
        "",
        "👑 Owner SMS → Group: " + ("🟢 ON" if OWNER_SMS_TO_GROUP else "🔴 OFF"),
    ]
    if USER_SMS_TO_GROUP:
        lines += [""] + [
            f"👤 {uid} → {'🟢 ON' if enabled else '🔴 OFF'}"
            for uid, enabled in USER_SMS_TO_GROUP.items()
        ]
    else:
        lines.append("ℹ️ কোনো User SMS control নেই।")
    await update.effective_message.reply_text("\n".join(lines) + vip_footer())

# ========================= NATURAL OWNER CONTROL ==============

async def owner_text_control(update, context, text):
    global OWNER_SMS_TO_GROUP, USER_SMS_TO_GROUP
    raw, low = text.strip(), text.strip().lower()

    explicit = extract_group_post(raw)
    if explicit:
        ai_post = await create_ai_post(explicit)
        sent, failed = await send_to_groups(context, ai_post)
        await update.effective_message.reply_text(owner_reply(f"📢 Group Post সম্পন্ন।\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))
        return True

    on_phrases = {"owner sms to group on", "sms to group on", "sms group on", "owner group sms on",
                  "ওনার sms to group on", "ওনার এসএমএস টু গ্রুপ অন"}
    off_phrases = {"owner sms to group off", "sms to group off", "sms group off", "owner group sms off",
                   "ওনার sms to group off", "ওনার এসএমএস টু গ্রুপ অফ"}

    if low in on_phrases:
        OWNER_SMS_TO_GROUP = True
        save_all()
        await update.effective_message.reply_text(owner_reply("🟢 Owner SMS → Group এখন ON।"))
        return True
    if low in off_phrases:
        OWNER_SMS_TO_GROUP = False
        save_all()
        await update.effective_message.reply_text(owner_reply("🔴 Owner SMS → Group এখন OFF। এখন সাধারণ SMS-এর AI উত্তর পাবেন।"))
        return True

    if low in {"owner sms status", "sms to group status", "sms status", "ওনার এসএমএস স্ট্যাটাস"}:
        await smsstatus_command(update, context)
        return True

    m = re.match(r"^(-?\d+)\s+sms\s+(on|off)$", low)
    if m:
        uid, action = m.group(1), m.group(2)
        if int(uid) <= 0:
            await update.effective_message.reply_text(owner_reply("❌ Positive personal User ID দিন।"))
            return True
        USER_SMS_TO_GROUP[uid] = action == "on"
        save_all()
        await update.effective_message.reply_text(owner_reply(
            f"👤 User ID: {uid}\n📢 SMS → Group: {'🟢 ON' if action == 'on' else '🔴 OFF'}"
        ))
        return True

    m = re.match(r"^(-?\d+)\s+sms\s+status$", low)
    if m:
        uid = m.group(1)
        enabled = USER_SMS_TO_GROUP.get(uid, False)
        await update.effective_message.reply_text(owner_reply(
            f"👤 User ID: {uid}\n📢 SMS → Group: {'🟢 ON' if enabled else '🔴 OFF'}"
        ))
        return True

    if low in {"auto post on", "autopost on", "অটো পোস্ট অন", "অটোপোস্ট অন"}:
        autopost_data["enabled"] = True
        save_all()
        await update.effective_message.reply_text(owner_reply("🟢 Auto Post চালু হয়েছে।"))
        return True

    if low in {"auto post off", "autopost off", "অটো পোস্ট অফ", "অটোপোস্ট অফ"}:
        autopost_data["enabled"] = False
        save_all()
        await update.effective_message.reply_text(owner_reply("🔴 Auto Post বন্ধ হয়েছে।"))
        return True

    if low in {"group add", "add group", "গ্রুপ যোগ করো", "গ্রুপ অ্যাড করো"}:
        await add_current_group(update, context)
        return True

    m = re.match(
        r"^(?:schedule|add\s*post|পোস্ট\s*যোগ)\s+([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)\s*(?:\||-)\s*(.+)$",
        raw, re.I
    )
    if m:
        t = parse_time(m.group(1))
        if not t:
            await update.effective_message.reply_text(owner_reply("⏰ সময় সঠিক নয়।"))
            return True
        post = {"id": next_post_id(), "post_time": t, "text": m.group(2).strip(),
                "photo_file_id": "", "enabled": True, "last_run_date": ""}
        autopost_data.setdefault("posts", []).append(post)
        save_all()
        await update.effective_message.reply_text(owner_reply(
            f"⏰ Scheduled Post যুক্ত হয়েছে।\n\n🆔 ID: {post['id']}\n🕐 Time: {t}\n🟢 Status: ON"
        ))
        return True

    return False

# ========================= AUTO POST =========================

async def on_command(update, context):
    if not await require_owner(update): return
    autopost_data["enabled"] = True
    save_all()
    await update.effective_message.reply_text(owner_reply("🟢 Auto Post চালু হয়েছে।"))

async def off_command(update, context):
    if not await require_owner(update): return
    autopost_data["enabled"] = False
    save_all()
    await update.effective_message.reply_text(owner_reply("🔴 Auto Post বন্ধ হয়েছে।"))

async def status_command(update, context):
    if not await require_owner(update): return
    await update.effective_message.reply_text(owner_reply(
        "📊 PREMIUM STATUS\n\n"
        f"📡 Groups: {len(autopost_data.get('groups', {}))}\n"
        f"📝 Posts: {len(autopost_data.get('posts', []))}\n"
        f"⏰ Auto Post: {'🟢 ON' if autopost_data.get('enabled') else '🔴 OFF'}\n"
        f"📢 Owner SMS → Group: {'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n"
        f"👤 Controlled Users: {len(USER_SMS_TO_GROUP)}"
    ))

async def addpost_command(update, context):
    if not await require_owner(update): return
    raw = update.effective_message.text or ""
    parts = raw.split(" ", 1)
    if len(parts) < 2:
        await update.effective_message.reply_text(owner_reply(
            "ব্যবহার:\n`/addpost 08:00 | আপনার বার্তা`\n`/addpost 08:30 PM | Good Night`"
        ))
        return
    m = re.match(r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)\s*\|\s*(.+)$", parts[1].strip(), re.I)
    if not m:
        await update.effective_message.reply_text(error_box("Format ভুল। `/addpost 08:00 | আপনার বার্তা`"))
        return
    t = parse_time(m.group(1))
    if not t:
        await update.effective_message.reply_text(error_box("সময় সঠিক নয়।"))
        return
    post = {"id": next_post_id(), "post_time": t, "text": m.group(2).strip(),
            "photo_file_id": "", "enabled": True, "last_run_date": ""}
    autopost_data.setdefault("posts", []).append(post)
    save_all()
    await update.effective_message.reply_text(owner_reply(
        f"⏰ Scheduled Post Added!\n\n🆔 ID: {post['id']}\n🕐 Time: {t}\n📝 Text: {post['text']}"
    ))

async def list_command(update, context):
    if not await require_owner(update): return
    posts = autopost_data.get("posts", [])
    if not posts:
        await update.effective_message.reply_text(info_box("কোনো Scheduled Post নেই।"))
        return
    lines = [vip_header("AUTO POST LIST"), ""]
    for p in posts:
        lines.append(
            f"🆔 ID: {p.get('id')}\n🕐 Time: {p.get('post_time')}\n"
            f"📦 Type: {'📸 PHOTO' if p.get('photo_file_id') else '📝 TEXT'}\n"
            f"📡 Status: {'🟢 ON' if p.get('enabled', True) else '🔴 OFF'}\n"
            f"💬 {p.get('text','')[:300]}\n━━━━━━━━━━━━━━━━━━━━"
        )
    await update.effective_message.reply_text("\n".join(lines))

async def delete_command(update, context):
    if not await require_owner(update): return
    if not context.args:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: `/delete POST_ID`"))
        return
    try:
        pid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(error_box("Post ID সঠিক নয়।"))
        return
    posts = autopost_data.get("posts", [])
    new_posts = [p for p in posts if int(p.get("id", 0)) != pid]
    if len(new_posts) == len(posts):
        await update.effective_message.reply_text(error_box(f"Post ID {pid} পাওয়া যায়নি।"))
        return
    autopost_data["posts"] = new_posts
    renumber_posts()  # IDs stay 1,2,3... after delete
    save_all()
    await update.effective_message.reply_text(owner_reply(f"🗑️ Post ID {pid} Delete হয়েছে। বাকি Post ID নতুন করে 1,2,3... করা হয়েছে।"))

async def clear_command(update, context):
    if not await require_owner(update): return
    autopost_data["posts"] = []
    save_all()
    await update.effective_message.reply_text(owner_reply("🧹 সব Scheduled Post Clear করা হয়েছে।"))

async def post_command(update, context):
    if not await require_owner(update): return
    raw = (update.effective_message.text or "").split(" ", 1)
    if len(raw) < 2:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: `/post আপনার বার্তা`"))
        return
    ai_post = await create_ai_post(raw[1].strip())
    sent, failed = await send_to_groups(context, ai_post)
    await update.effective_message.reply_text(owner_reply(f"📢 Group Post Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))

async def broadcast_command(update, context):
    if not await require_owner(update): return
    raw = (update.effective_message.text or "").split(" ", 1)
    if len(raw) < 2:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: `/broadcast আপনার বার্তা`"))
        return
    sent, failed = await send_to_groups(context, raw[1].strip())
    await update.effective_message.reply_text(owner_reply(f"📣 Broadcast Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))

async def test_command(update, context):
    if not await require_owner(update): return
    text = "╔════════════════════════════╗\n       👑 RJ TEAM TEST\n╚════════════════════════════╝\n\n💎 Group connection successful.\n📡 Premium AI Bot is active.\n🇧🇩 Bangladesh Time System Active."
    sent, failed = await send_to_groups(context, text)
    await update.effective_message.reply_text(owner_reply(f"🧪 Test Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))

async def autopost_worker(application):
    logging.info("Auto-post worker started.")
    while True:
        try:
            if autopost_data.get("enabled", True):
                now = datetime.now(BD)
                current_time, today = now.strftime("%H:%M"), now.strftime("%Y-%m-%d")
                changed = False
                for post in autopost_data.get("posts", []):
                    if not post.get("enabled", True): continue
                    if post.get("post_time") != current_time: continue
                    if post.get("last_run_date", "") == today: continue
                    photo_id, post_text = post.get("photo_file_id", ""), post.get("text", "")
                    if photo_id:
                        await send_photo_to_groups(application, photo_id, post_text)
                    else:
                        await send_to_groups(application, post_text)
                    post["last_run_date"] = today
                    changed = True
                if changed: save_all()
        except Exception:
            logging.exception("Auto worker error")
        await asyncio.sleep(20)

# ========================= PHOTO ==============================

async def photo_handler(update, context):
    message, user = update.effective_message, update.effective_user
    if not message or not user: return
    register_user(user)
    save_all()
    caption = (message.caption or "").strip()
    photo_id = message.photo[-1].file_id

    if is_owner(user):
        m = re.match(r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)\s*\|\s*(.*)$", caption, re.I)
        if m:
            t = parse_time(m.group(1))
            if t:
                post = {"id": next_post_id(), "post_time": t, "text": m.group(2).strip(),
                        "photo_file_id": photo_id, "enabled": True, "last_run_date": ""}
                autopost_data.setdefault("posts", []).append(post)
                save_all()
                await message.reply_text(owner_reply(f"📸 Photo Scheduled Post Added!\n\n🆔 ID: {post['id']}\n🕐 Time: {t}\n🟢 Status: ON"))
                return

        explicit = extract_group_post(caption)
        if explicit:
            ai_caption = await create_ai_post(explicit)
            sent, failed = await send_photo_to_groups(context, photo_id, ai_caption)
            await message.reply_text(owner_reply(f"📸 Photo Group Post Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))
            return

        if OWNER_SMS_TO_GROUP:
            base = caption or "এই ছবিটি RJ TEAM BANGLADESH-এর পক্ষ থেকে।"
            ai_caption = await create_ai_post(base)
            sent, failed = await send_photo_to_groups(context, photo_id, ai_caption)
            await message.reply_text(owner_reply(f"📸 Photo Group Post Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))
            return

        await message.reply_text(owner_reply("📸 Photo পেয়েছি, বস। SMS → Group OFF থাকায় এটি Group-এ পাঠানো হয়নি।"))
        return

    uid = str(user.id)
    if USER_SMS_TO_GROUP.get(uid, False):
        ai_caption = await create_ai_post(caption or "একটি নতুন Photo Post")
        sent, failed = await send_photo_to_groups(context, photo_id, ai_caption)
        await message.reply_text(f"📸 Premium Photo Post তৈরি হয়েছে।\n\n📢 Group Sent: {sent}")
    else:
        await message.reply_text("📸 Photo received successfully.")

# ========================= USER SEND ==========================

async def sendmsg_command(update, context):
    if not await require_owner(update): return
    parts = (update.effective_message.text or "").split(" ", 2)
    if len(parts) < 3:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: `/sendmsg USER_ID আপনার বার্তা`"))
        return
    target, send_text = parts[1].strip(), parts[2].strip()
    data = USER_REGISTRY.get(target.lower() if target.startswith("@") else target)
    if not data:
        await update.effective_message.reply_text(owner_reply("❌ User আগে Bot-এ `/start` দেয়নি বা Registry-তে নেই।"))
        return
    try:
        await context.bot.send_message(chat_id=int(data["user_id"]), text=send_text)
        await update.effective_message.reply_text(owner_reply(f"✅ Message পাঠানো হয়েছে।\n\n👤 User ID: {data['user_id']}"))
    except Exception:
        logging.exception("sendmsg failed")
        await update.effective_message.reply_text(error_box("Message পাঠানো যায়নি। User Bot block করেছে কিনা পরীক্ষা করুন।"))

# ========================= TRANSLATION ========================

async def translate_command(update, context):
    parts = (update.effective_message.text or "").split(" ", 2)
    if len(parts) < 3:
        await update.effective_message.reply_text(info_box("ব্যবহার: `/translate bn Hello brother`"))
        return
    result = await ask_gemini(f"Translate the following text into {parts[1]}. Return only the translation.\n\n{parts[2]}")
    user_last_ai_reply[update.effective_user.id] = result
    await update.effective_message.reply_text("🌐 TRANSLATION\n\n" + result)

async def translate_last_command(update, context):
    if not context.args:
        await update.effective_message.reply_text(info_box("ব্যবহার: `/translate_last bn`"))
        return
    last = user_last_ai_reply.get(update.effective_user.id)
    if not last:
        await update.effective_message.reply_text(error_box("আপনার কোনো আগের AI Reply পাওয়া যায়নি।"))
        return
    result = await ask_gemini(f"Translate this into {context.args[0]}. Return only the translation:\n\n{last}")
    await update.effective_message.reply_text("🔁 TRANSLATED LAST REPLY\n\n" + result)

# ========================= START / HELP / ABOUT ===============

async def start_command(update, context):
    register_user(update.effective_user)
    save_all()
    if is_owner(update.effective_user):
        text = "👑 বস, Welcome Back!\n\n💎 RJ TEAM BANGLADESH Premium AI Bot\n🤖 Gemini AI: Ready\n📡 Group System: Ready\n\n🛡️ Premium Control সক্রিয়। `/help` লিখুন।"
    else:
        text = vip_header("WELCOME") + "\n\n🤖 RJ TEAM Premium AI Bot-এ স্বাগতম।\n\n💬 আপনার প্রশ্ন লিখুন।\n/about — About\n/help — Help" + vip_footer()
    await update.effective_message.reply_text(text)

async def about_command(update, context):
    await update.effective_message.reply_text(
        vip_header("ABOUT RJ TEAM") + "\n\n👑 RJ TEAM BANGLADESH\n💎 Premium AI Bot\n🤖 Gemini AI Powered\n🇧🇩 Bangladesh Timezone\n📡 Multi Group System\n🔥 Firebase Backup" + vip_footer()
    )

async def help_command(update, context):
    if is_owner(update.effective_user):
        text = (
            vip_header("OWNER CONTROL") + "\n\n"
            "📌 GROUP\n/addgroup — Current Group Add\n/groups — Group List\n/delgroup — Group Remove\n/test — Group Test\n\n"
            "📌 SMS CONTROL\n/smson — Owner SMS → Group ON\n/smsoff — Owner SMS → Group OFF\n/smsstatus — SMS Status\n\n"
            "📌 POST\n/post — AI Group Post\n/broadcast — Broadcast\n/addpost — Scheduled Post\n/list — Post List\n/delete ID — Delete Post\n/clear — Clear Posts\n\n"
            "📌 AUTO POST\n/on — Auto Post ON\n/off — Auto Post OFF\n/autopost — Status\n/status — Full Status\n\n"
            "📌 USER\n/sendmsg USER_ID message\n123456789 sms on\n123456789 sms off\n123456789 sms status\n\n"
            "📌 AI\n/translate bn text\n/translate_last bn\n\n"
            "💎 SMS → Group OFF থাকলে আপনার সাধারণ প্রশ্নের AI উত্তর আসবে।\n"
            "🟢 SMS → Group ON থাকলে আপনার সাধারণ text AI caption হয়ে সক্রিয় Group-এ যাবে।"
        )
    else:
        text = vip_header("PREMIUM AI HELP") + "\n\n🤖 যেকোনো প্রশ্ন লিখুন।\n🌐 `/translate bn Hello`\nℹ️ `/about`"
    await update.effective_message.reply_text(text)

async def cancel_command(update, context):
    if await require_owner(update):
        await update.effective_message.reply_text(owner_reply("❌ কোনো pending operation ছিল না।"))

# ========================= NORMAL TEXT ========================

async def normal_message(update, context):
    message, user = update.effective_message, update.effective_user
    if not message or not user: return
    text = (message.text or "").strip()
    if not text: return
    register_user(user)
    save_all()

    if is_owner(user):
        if await owner_text_control(update, context, text):
            return

        # IMPORTANT: OFF = normal AI reply; ON = AI caption -> groups.
        if OWNER_SMS_TO_GROUP:
            ai_post = await create_ai_post(text)
            sent, failed = await send_to_groups(context, ai_post)
            await message.reply_text(owner_reply(
                "📢 আপনার SMS থেকে সুন্দর Premium Caption তৈরি করে Group-এ পাঠানো হয়েছে।\n\n"
                f"✅ Sent: {sent}\n❌ Failed: {failed}"
            ))
        else:
            answer = await ask_gemini("Owner @RJteam1 বলেছেন:\n\n" + text)
            user_last_ai_reply[user.id] = answer
            await message.reply_text(owner_reply(answer))
        return

    uid = str(user.id)
    if USER_SMS_TO_GROUP.get(uid, False):
        ai_post = await create_ai_post(text)
        sent, failed = await send_to_groups(context, ai_post)
        await message.reply_text(f"💎 Premium Post তৈরি হয়েছে।\n\n📢 Group Sent: {sent}")
        return

    answer = await ask_gemini(text)
    user_last_ai_reply[user.id] = answer
    await message.reply_text(answer)

# ========================= HEALTH =============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"RJ TEAM BANGLADESH PREMIUM AI BOT is running.")
    def log_message(self, format, *args):
        return

def start_health_server():
    global health_thread
    try:
        server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
        health_thread = Thread(target=server.serve_forever, daemon=True)
        health_thread.start()
        logging.info("Health server started on port %s", PORT)
    except Exception:
        logging.exception("Health server failed")

# ========================= INIT ===============================

async def post_init(application):
    global scheduler_task
    init_firebase()
    firebase_load()
    # Local file is a fallback if Firebase did not provide useful data.
    if not autopost_data.get("groups") and os.path.exists(AUTOPOST_FILE):
        load_local()

    if TARGET_CHAT_ID:
        for raw_id in TARGET_CHAT_ID.split(","):
            raw_id = raw_id.strip()
            if not raw_id: continue
            try:
                cid = int(raw_id)
                if cid >= 0: continue
                autopost_data.setdefault("groups", {}).setdefault(str(cid), {
                    "id": cid, "title": "Configured Group", "type": "group",
                    "added_at": datetime.now(BD).isoformat(), "active": True
                })
            except Exception:
                logging.warning("Invalid TARGET_CHAT_ID: %s", raw_id)

    save_all()

    # FIX: worker receives Application, which has .bot.
    if scheduler_task is None:
        scheduler_task = asyncio.create_task(autopost_worker(application))
    logging.info("RJ TEAM BANGLADESH bot initialized.")

async def callback_handler(update, context):
    if update.callback_query:
        await update.callback_query.answer()

async def error_handler(update, context):
    logging.error("Telegram update error: %s", context.error, exc_info=context.error)

# ========================= MAIN ===============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO
    )

    load_local()
    init_firebase()
    init_gemini()
    start_health_server()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    commands = {
        "start": start_command, "help": help_command, "about": about_command,
        "addgroup": add_current_group, "groups": groups_command, "delgroup": delgroup_command,
        "on": on_command, "off": off_command, "status": status_command, "autopost": status_command,
        "smson": smson_command, "smsoff": smsoff_command, "smsstatus": smsstatus_command,
        "post": post_command, "broadcast": broadcast_command, "addpost": addpost_command,
        "list": list_command, "delete": delete_command, "clear": clear_command, "test": test_command,
        "sendmsg": sendmsg_command, "translate": translate_command, "translate_last": translate_last_command,
        "cancel": cancel_command,
    }
    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, normal_message))
    app.add_error_handler(error_handler)

    logging.info("👑 RJ TEAM BANGLADESH PREMIUM AI BOT | Owner: @%s", ADMIN_USERNAME)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
