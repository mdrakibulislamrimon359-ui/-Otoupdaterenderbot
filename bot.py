# ============================================================
# RJ TEAM BANGLADESH - PREMIUM AI BOT
# Full bot.py: AI, Auto Post, Groups, Inbox SMS ON/OFF, Firebase
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

# ========================= CONFIG ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "RJteam1").strip().lstrip("@")
ADMIN_USER_ID_RAW = os.getenv("ADMIN_USER_ID", "").strip()
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "").strip()
AUTOPOST_FILE = os.getenv("AUTOPOST_FILE", "autopost.json").strip() or "autopost.json"
AUTOPOST_ENABLED = os.getenv("AUTOPOST_ENABLED", "true").lower() in ("1", "true", "yes", "on")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
AUTOPOST_FIREBASE_COLLECTION = os.getenv("AUTOPOST_FIREBASE_COLLECTION", "rj_bot_config").strip()
AUTOPOST_FIREBASE_DOCUMENT = os.getenv("AUTOPOST_FIREBASE_DOCUMENT", "autopost").strip()
PORT = int(os.getenv("PORT", "10000"))

# Override GEMINI_MODEL in Render if needed. Retired gemini-2.0-flash is intentionally excluded.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
GEMINI_MODELS = list(dict.fromkeys([
    GEMINI_MODEL,
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]))

BD = ZoneInfo("Asia/Dhaka")
try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_RAW) if ADMIN_USER_ID_RAW else None
except ValueError:
    ADMIN_USER_ID = None

SYSTEM_PROMPT = """
তুমি RJ TEAM BANGLADESH-এর Premium AI Assistant।
স্বাভাবিক, ভদ্র ও বন্ধুসুলভভাবে উত্তর দেবে।
বাংলা প্রশ্নে বাংলায় উত্তর দেবে। Banglish হলে সহজ বাংলা/Banglish-এ উত্তর দিতে পারো।
প্রযুক্তি/কোডিং প্রশ্নে পরিষ্কারভাবে সাহায্য করবে। ভুল তথ্য বানিয়ে বলবে না।
Owner @RJteam1-এর সাথে কথা বলার সময় তাকে "বস" বলে সম্বোধন করবে।
"""
POST_SYSTEM_PROMPT = """
তুমি RJ TEAM BANGLADESH-এর Premium Telegram Post Writer।
ব্যবহারকারীর দেওয়া কথার মূল অর্থ ঠিক রেখে সুন্দর, সংক্ষিপ্ত ও আকর্ষণীয় বাংলা Telegram/group caption তৈরি করবে।
প্রয়োজনে heading, spacing ও Unicode emoji ব্যবহার করবে।
নিজে থেকে নতুন তথ্য, link, phone number বা দাবি বানাবে না।
শুধু প্রস্তুত পোস্টটি দেবে; ব্যাখ্যা যোগ করবে না।
"""

# ========================= GLOBAL ============================
gemini_client = None
firebase_db = None
scheduler_task = None
health_thread = None
OWNER_SMS_TO_GROUP = False
USER_SMS_TO_GROUP = {}
USER_REGISTRY = {}
user_last_ai_reply = {}
autopost_data = {
    "enabled": AUTOPOST_ENABLED, "groups": {}, "posts": [],
    "owner_sms_to_group": False, "user_sms_to_group": {}, "user_registry": {},
}

# ========================= UI ================================
def vip_header(title="RJ TEAM BANGLADESH"):
    return f"╔════════════════════════════╗\n        👑 {title}\n╚════════════════════════════╝"

def vip_footer():
    return "\n\n━━━━━━━━━━━━━━━━━━━━\n💎 RJ TEAM BANGLADESH\n👑 PREMIUM AI EXPERIENCE\n━━━━━━━━━━━━━━━━━━━━"

def success_box(message):
    return vip_header("SUCCESS") + "\n\n" + message + vip_footer()

def error_box(message):
    return vip_header("ERROR") + "\n\n" + message + vip_footer()

def info_box(message):
    return vip_header("INFORMATION") + "\n\n" + message + vip_footer()

def owner_reply(message):
    return "👑 বস,\n\n" + message + vip_footer()

def inbox_sms_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Inbox SMS ON", callback_data="inbox_sms_on"),
         InlineKeyboardButton("🔴 Inbox SMS OFF", callback_data="inbox_sms_off")],
        [InlineKeyboardButton("📊 বর্তমান Status", callback_data="inbox_sms_status")],
    ])

def inbox_sms_panel_text():
    status = ("🟢 ON — আপনার সাধারণ মেসেজ পোস্ট হয়ে গ্রুপ/চ্যানেলে যাবে।"
              if OWNER_SMS_TO_GROUP else
              "🔴 OFF — আপনার সাধারণ মেসেজের AI উত্তর ইনবক্সে আসবে।")
    return owner_reply("📨 INBOX SMS CONTROL\n\nবর্তমান অবস্থা:\n" + status + "\n\nনিচের বাটন দিয়ে পরিবর্তন করুন।")

# ========================= OWNER =============================
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

# ========================= STORAGE ===========================
def normalize_storage():
    global autopost_data, USER_SMS_TO_GROUP, USER_REGISTRY, OWNER_SMS_TO_GROUP
    if not isinstance(autopost_data, dict):
        autopost_data = {}
    groups = autopost_data.get("groups", {})
    if isinstance(groups, list):
        autopost_data["groups"] = {
            str(x.get("id", x.get("chat_id"))): x for x in groups
            if isinstance(x, dict) and x.get("id", x.get("chat_id")) is not None
        }
    elif not isinstance(groups, dict):
        autopost_data["groups"] = {}
    if not isinstance(autopost_data.get("posts"), list):
        autopost_data["posts"] = []
    raw_sms = autopost_data.get("user_sms_to_group", {})
    if isinstance(raw_sms, list):
        raw_sms = {str(x): True for x in raw_sms}
    if not isinstance(raw_sms, dict):
        raw_sms = {}
    USER_SMS_TO_GROUP = {str(k): bool(v) for k, v in raw_sms.items()}
    raw_registry = autopost_data.get("user_registry", {})
    if not isinstance(raw_registry, dict):
        raw_registry = {}
    USER_REGISTRY = {str(k): v for k, v in raw_registry.items() if isinstance(v, dict)}
    OWNER_SMS_TO_GROUP = bool(autopost_data.get("owner_sms_to_group", False))
    autopost_data["user_sms_to_group"] = USER_SMS_TO_GROUP
    autopost_data["user_registry"] = USER_REGISTRY
    autopost_data.setdefault("enabled", AUTOPOST_ENABLED)
    autopost_data.setdefault("groups", {})
    autopost_data.setdefault("posts", [])

def init_firebase():
    global firebase_db
    if firebase_db is not None:
        return firebase_db
    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        return None
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)))
        firebase_db = firestore.client()
    except Exception:
        logging.exception("Firebase initialization failed")
    return firebase_db

def save_local():
    try:
        os.makedirs(os.path.dirname(os.path.abspath(AUTOPOST_FILE)), exist_ok=True)
        with open(AUTOPOST_FILE, "w", encoding="utf-8") as f:
            json.dump(autopost_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logging.exception("Local save failed")
        return False

def load_local():
    global autopost_data
    if os.path.exists(AUTOPOST_FILE):
        try:
            with open(AUTOPOST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                autopost_data.update(data)
            normalize_storage()
        except Exception:
            logging.exception("Local load failed")

def firebase_load():
    global autopost_data
    db = init_firebase()
    if db is None:
        return
    try:
        snap = db.collection(AUTOPOST_FIREBASE_COLLECTION).document(AUTOPOST_FIREBASE_DOCUMENT).get()
        if snap.exists and isinstance(snap.to_dict(), dict):
            autopost_data.update(snap.to_dict())
            normalize_storage()
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
    normalize_storage()
    autopost_data["owner_sms_to_group"] = OWNER_SMS_TO_GROUP
    autopost_data["user_sms_to_group"] = USER_SMS_TO_GROUP
    autopost_data["user_registry"] = USER_REGISTRY
    save_local()
    firebase_save()

def register_user(user):
    if not user:
        return
    uid = str(user.id)
    username = f"@{user.username}" if user.username else ""
    name = " ".join(x for x in [user.first_name or "", user.last_name or ""] if x).strip()
    data = {"user_id": user.id, "username": username, "name": name, "updated_at": datetime.now(BD).isoformat()}
    USER_REGISTRY[uid] = data
    if username:
        USER_REGISTRY[username.lower()] = data
    autopost_data["user_registry"] = USER_REGISTRY

# ========================= GEMINI ============================
def init_gemini():
    global gemini_client
    if gemini_client is not None:
        return gemini_client
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY is missing.")
        return None
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        logging.exception("Gemini initialization failed")
    return gemini_client

async def ask_gemini(prompt, system_prompt=SYSTEM_PROMPT):
    client = init_gemini()
    if client is None:
        return "দুঃখিত 😔\nGemini API সংযুক্ত নেই। Render-এর GEMINI_API_KEY পরীক্ষা করুন।"
    last_error = None
    # Do not force temperature: model APIs may not support every generation parameter.
    config = types.GenerateContentConfig(system_instruction=system_prompt)
    for model_name in GEMINI_MODELS:
        try:
            logging.info("Trying Gemini model: %s", model_name)
            response = await asyncio.to_thread(
                client.models.generate_content, model=model_name, contents=prompt, config=config
            )
            answer = getattr(response, "text", None)
            if answer and answer.strip():
                logging.info("Gemini success: %s", model_name)
                return answer.strip()
            last_error = f"{model_name}: empty response"
        except Exception as exc:
            last_error = exc
            logging.warning("Gemini model failed %s: %s", model_name, exc)
    logging.error("All Gemini models failed: %s", last_error)
    return ("দুঃখিত 😔\n\nAI সার্ভারে সমস্যা হচ্ছে। Render-এর GEMINI_API_KEY ও GEMINI_MODEL "
            "এবং Google AI Studio-তে API/model access পরীক্ষা করুন।")

async def create_ai_post(text):
    return await ask_gemini(text, POST_SYSTEM_PROMPT)

# ========================= HELPERS ===========================
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
    for pat in patterns:
        m = re.search(pat, text, re.I | re.S)
        if m:
            return m.group(1).strip()
    return None

def get_bot(obj):
    if obj is None:
        return None
    bot = getattr(obj, "bot", None) or getattr(getattr(obj, "application", None), "bot", None)
    return bot or (obj if hasattr(obj, "send_message") else None)

async def resolve_chat_reference(context, reference):
    reference = (reference or "").strip()
    if not reference:
        return None, "❌ Group/Channel username বা Chat ID দিন।"
    reference = re.sub(r"^https?://t\.me/", "", reference, flags=re.I).strip("/").split("?", 1)[0]
    bot = get_bot(context)
    if bot is None:
        return None, "❌ Telegram Bot পাওয়া যায়নি।"
    try:
        if re.fullmatch(r"-?\d+", reference):
            return await bot.get_chat(int(reference)), None
        username = reference.lstrip("@").strip()
        if not username:
            return None, "❌ Username সঠিক নয়।"
        return await bot.get_chat("@" + username), None
    except Exception:
        logging.exception("Could not resolve chat")
        return None, ("❌ Group/Channel resolve হয়নি। Bot-কে chat-এ যোগ করুন; Channel হলে Admin ও "
                      "Post Messages permission দিন; username/Chat ID পরীক্ষা করুন।")

async def check_chat_permissions(context, chat):
    bot = get_bot(context)
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=chat.id, user_id=me.id)
        if member.status in ("left", "kicked"):
            return False, "❌ Bot এই Group/Channel-এর member নয়।"
        if chat.type == "channel":
            if member.status != "administrator":
                return False, "❌ Channel-এ Bot Admin নয়।"
            if getattr(member, "can_post_messages", True) is False:
                return False, "❌ Bot-এর Post Messages permission নেই।"
        return True, None
    except Exception:
        logging.exception("Permission check failed")
        return False, "⚠️ Permission যাচাই হয়নি। Bot-কে chat-এ যোগ করে আবার চেষ্টা করুন।"

async def send_to_groups(context_or_bot, text, exclude_chat_id=None):
    bot = get_bot(context_or_bot)
    groups = autopost_data.get("groups", {})
    if bot is None:
        return 0, len(groups)
    sent = failed = 0
    for gid, data in list(groups.items()):
        if not data.get("active", True):
            continue
        try:
            cid = int(gid)
            if exclude_chat_id is not None and cid == exclude_chat_id:
                continue
            await bot.send_message(chat_id=cid, text=text)
            sent += 1
        except Exception:
            failed += 1
            logging.exception("Destination send failed: %s", gid)
    return sent, failed

async def send_photo_to_groups(context_or_bot, photo_file_id, caption=""):
    bot = get_bot(context_or_bot)
    groups = autopost_data.get("groups", {})
    if bot is None:
        return 0, len(groups)
    sent = failed = 0
    for gid, data in list(groups.items()):
        if not data.get("active", True):
            continue
        try:
            await bot.send_photo(chat_id=int(gid), photo=photo_file_id, caption=(caption or "")[:1024])
            sent += 1
        except Exception:
            failed += 1
            logging.exception("Photo send failed: %s", gid)
    return sent, failed

# ========================= GROUP MANAGEMENT ==================
async def add_chat_destination(update, context):
    if not await require_owner(update):
        return
    message = update.effective_message
    chat = None
    if context.args:
        chat, error = await resolve_chat_reference(context, context.args[0])
        if error:
            await message.reply_text(error_box(error)); return
    else:
        current = update.effective_chat
        if current and current.type in ("group", "supergroup", "channel"):
            chat = current
        else:
            await message.reply_text(error_box("ব্যবহার: /addgroup @username অথবা /addchannel @username")); return
    allowed, err = await check_chat_permissions(context, chat)
    if not allowed:
        await message.reply_text(error_box(err)); return
    gid = str(chat.id)
    username = getattr(chat, "username", None)
    autopost_data.setdefault("groups", {})[gid] = {
        "id": chat.id, "title": getattr(chat, "title", None) or getattr(chat, "full_name", None) or "Unnamed",
        "username": "@" + username if username else "", "type": chat.type,
        "added_at": datetime.now(BD).isoformat(), "active": True,
    }
    save_all()
    await message.reply_text(success_box(f"📡 Destination যুক্ত হয়েছে!\n🏷️ {autopost_data['groups'][gid]['title']}\n🆔 {gid}\n📂 {chat.type}"))

async def addgroup_command(update, context): await add_chat_destination(update, context)
async def addchannel_command(update, context): await add_chat_destination(update, context)
async def addchat_command(update, context): await add_chat_destination(update, context)

async def groups_command(update, context):
    if not await require_owner(update): return
    groups = autopost_data.get("groups", {})
    if not groups:
        await update.effective_message.reply_text(info_box("কোনো Group/Channel যুক্ত নেই।\n/addgroup @username")); return
    lines = [vip_header("PREMIUM DESTINATION PANEL"), ""]
    for i, (gid, d) in enumerate(groups.items(), 1):
        lines.append(f"{i}. {d.get('title', 'Unknown')}\n🆔 ID: {gid}\n📂 Type: {d.get('type', 'unknown')}\n🔗 {d.get('username') or 'No Username'}\n📡 Active: {'🟢 YES' if d.get('active', True) else '🔴 NO'}\n━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💎 Total Destinations: {len(groups)}")
    await update.effective_message.reply_text("\n".join(lines) + vip_footer())

async def remove_chat_destination(update, context):
    if not await require_owner(update): return
    groups = autopost_data.get("groups", {})
    if not groups:
        await update.effective_message.reply_text(info_box("কোনো Group/Channel তালিকায় নেই।")); return
    if not context.args:
        chat = update.effective_chat
        gid = str(chat.id) if chat else ""
    else:
        ref = context.args[0].lower()
        gid = next((sid for sid, d in groups.items()
                    if sid == ref or str(d.get("username", "")).lower() == ref
                    or str(d.get("username", "")).lower().lstrip("@") == ref.lstrip("@")), None)
        if gid is None:
            chat, error = await resolve_chat_reference(context, context.args[0])
            if error:
                await update.effective_message.reply_text(error_box(error)); return
            gid = str(chat.id)
    if gid not in groups:
        await update.effective_message.reply_text(error_box("❌ এই Group/Channel তালিকায় নেই।")); return
    name = groups[gid].get("title", "Unknown")
    del groups[gid]; save_all()
    await update.effective_message.reply_text(success_box(f"🗑️ Destination Removed!\n🏷️ {name}\n🆔 {gid}"))

async def delgroup_command(update, context): await remove_chat_destination(update, context)
async def delchannel_command(update, context): await remove_chat_destination(update, context)
async def removegroup_command(update, context): await remove_chat_destination(update, context)
async def removechannel_command(update, context): await remove_chat_destination(update, context)

# ========================= INBOX SMS CONTROL =================
async def inboxsms_command(update, context):
    if await require_owner(update):
        await update.effective_message.reply_text(inbox_sms_panel_text(), reply_markup=inbox_sms_keyboard())

async def set_owner_sms_mode(update, enabled):
    global OWNER_SMS_TO_GROUP
    OWNER_SMS_TO_GROUP = enabled
    save_all()
    state = "ON" if enabled else "OFF"
    desc = ("এখন আপনার সাধারণ Inbox text AI caption হয়ে active Group/Channel-এ যাবে।"
            if enabled else "এখন সাধারণ প্রশ্নের AI উত্তর Inbox-এ আসবে; সাধারণ text broadcast হবে না।")
    query = update.callback_query
    if query:
        await query.edit_message_text(owner_reply(f"📨 Inbox SMS {state}\n\n{desc}"), reply_markup=inbox_sms_keyboard())
    elif update.effective_message:
        await update.effective_message.reply_text(owner_reply(f"📨 Inbox SMS {state}\n\n{desc}"), reply_markup=inbox_sms_keyboard())

async def smson_command(update, context):
    if await require_owner(update): await set_owner_sms_mode(update, True)

async def smsoff_command(update, context):
    if await require_owner(update): await set_owner_sms_mode(update, False)

async def smsstatus_command(update, context):
    if not await require_owner(update): return
    lines = [vip_header("SMS CONTROL"), "", f"👑 Owner Inbox SMS → Group: {'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}"]
    lines += ([f"👤 {uid} → {'🟢 ON' if v else '🔴 OFF'}" for uid, v in USER_SMS_TO_GROUP.items()]
              if USER_SMS_TO_GROUP else ["ℹ️ কোনো User SMS control নেই।"])
    await update.effective_message.reply_text("\n".join(lines) + vip_footer(), reply_markup=inbox_sms_keyboard())

async def callback_handler(update, context):
    q = update.callback_query
    if not q: return
    action = q.data or ""
    if action not in {"inbox_sms_on", "inbox_sms_off", "inbox_sms_status"}:
        await q.answer(); return
    if not is_owner(q.from_user):
        await q.answer("⛔ এই Control শুধুমাত্র Owner-এর জন্য।", show_alert=True); return
    await q.answer()
    if action == "inbox_sms_on": await set_owner_sms_mode(update, True)
    elif action == "inbox_sms_off": await set_owner_sms_mode(update, False)
    else: await q.edit_message_text(inbox_sms_panel_text(), reply_markup=inbox_sms_keyboard())

# ========================= OWNER NATURAL CONTROL =============
async def owner_text_control(update, context, text):
    global USER_SMS_TO_GROUP
    raw, low = text.strip(), text.strip().lower()
    explicit = extract_group_post(raw)
    if explicit:
        post = await create_ai_post(explicit)
        sent, failed = await send_to_groups(context, post)
        await update.effective_message.reply_text(owner_reply(f"📢 Group/Channel Post সম্পন্ন।\n\n✅ Sent: {sent}\n❌ Failed: {failed}")); return True
    on_phrases = {"owner sms to group on", "sms to group on", "sms group on", "owner group sms on", "ওনার এসএমএস টু গ্রুপ অন"}
    off_phrases = {"owner sms to group off", "sms to group off", "sms group off", "owner group sms off", "ওনার এসএমএস টু গ্রুপ অফ"}
    if low in on_phrases: await set_owner_sms_mode(update, True); return True
    if low in off_phrases: await set_owner_sms_mode(update, False); return True
    if low in {"owner sms status", "sms to group status", "sms status", "ওনার এসএমএস স্ট্যাটাস"}:
        await smsstatus_command(update, context); return True
    m = re.match(r"^(-?\d+)\s+sms\s+(on|off)$", low)
    if m:
        uid, action = m.groups()
        if int(uid) <= 0:
            await update.effective_message.reply_text(owner_reply("❌ Positive personal User ID দিন।")); return True
        USER_SMS_TO_GROUP[uid] = action == "on"; save_all()
        await update.effective_message.reply_text(owner_reply(f"👤 User ID: {uid}\n📢 SMS → Group: {'🟢 ON' if action == 'on' else '🔴 OFF'}")); return True
    m = re.match(r"^(-?\d+)\s+sms\s+status$", low)
    if m:
        uid = m.group(1)
        await update.effective_message.reply_text(owner_reply(f"👤 User ID: {uid}\n📢 SMS → Group: {'🟢 ON' if USER_SMS_TO_GROUP.get(uid, False) else '🔴 OFF'}")); return True
    if low in {"auto post on", "autopost on", "অটো পোস্ট অন", "অটোপোস্ট অন"}:
        autopost_data["enabled"] = True; save_all()
        await update.effective_message.reply_text(owner_reply("🟢 Auto Post চালু হয়েছে।")); return True
    if low in {"auto post off", "autopost off", "অটো পোস্ট অফ", "অটোপোস্ট অফ"}:
        autopost_data["enabled"] = False; save_all()
        await update.effective_message.reply_text(owner_reply("🔴 Auto Post বন্ধ হয়েছে।")); return True
    if low in {"group add", "add group", "গ্রুপ যোগ করো", "গ্রুপ অ্যাড করো"}:
        await add_chat_destination(update, context); return True
    m = re.match(r"^(?:schedule|add\s*post|পোস্ট\s*যোগ)\s+([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)\s*(?:\||-)\s*(.+)$", raw, re.I | re.S)
    if m:
        t = parse_time(m.group(1))
        if not t:
            await update.effective_message.reply_text(owner_reply("⏰ সময় সঠিক নয়।")); return True
        p = {"id": next_post_id(), "post_time": t, "text": m.group(2).strip(), "photo_file_id": "", "enabled": True, "last_run_date": ""}
        autopost_data.setdefault("posts", []).append(p); save_all()
        await update.effective_message.reply_text(owner_reply(f"⏰ Scheduled Post যুক্ত হয়েছে।\n\n🆔 ID: {p['id']}\n🕐 Time: {t}\n🟢 Status: ON")); return True
    return False

# ========================= AUTO POST COMMANDS ================
async def on_command(update, context):
    if await require_owner(update):
        autopost_data["enabled"] = True; save_all()
        await update.effective_message.reply_text(owner_reply("🟢 Auto Post চালু হয়েছে।"))

async def off_command(update, context):
    if await require_owner(update):
        autopost_data["enabled"] = False; save_all()
        await update.effective_message.reply_text(owner_reply("🔴 Auto Post বন্ধ হয়েছে।"))

async def status_command(update, context):
    if not await require_owner(update): return
    groups = autopost_data.get("groups", {})
    gc = sum(1 for d in groups.values() if d.get("type") != "channel")
    cc = sum(1 for d in groups.values() if d.get("type") == "channel")
    await update.effective_message.reply_text(owner_reply(
        "📊 PREMIUM STATUS\n\n"
        f"📡 Total Destinations: {len(groups)}\n👥 Groups: {gc}\n📢 Channels: {cc}\n"
        f"📝 Posts: {len(autopost_data.get('posts', []))}\n"
        f"⏰ Auto Post: {'🟢 ON' if autopost_data.get('enabled', True) else '🔴 OFF'}\n"
        f"📨 Inbox SMS → Group: {'🟢 ON' if OWNER_SMS_TO_GROUP else '🔴 OFF'}\n"
        f"👤 Controlled Users: {len(USER_SMS_TO_GROUP)}"
    ))

async def addpost_command(update, context):
    if not await require_owner(update): return
    raw = (update.effective_message.text or "").split(" ", 1)
    if len(raw) < 2:
        await update.effective_message.reply_text(owner_reply("ব্যবহার:\n/addpost 08:00 | আপনার বার্তা\n/addpost 08:30 PM | Good Night")); return
    m = re.match(r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)\s*\|\s*(.+)$", raw[1].strip(), re.I | re.S)
    if not m:
        await update.effective_message.reply_text(error_box("Format ভুল। /addpost 08:00 | আপনার বার্তা")); return
    t = parse_time(m.group(1))
    if not t:
        await update.effective_message.reply_text(error_box("সময় সঠিক নয়।")); return
    p = {"id": next_post_id(), "post_time": t, "text": m.group(2).strip(), "photo_file_id": "", "enabled": True, "last_run_date": ""}
    autopost_data.setdefault("posts", []).append(p); save_all()
    await update.effective_message.reply_text(owner_reply(f"⏰ Scheduled Post Added!\n\n🆔 ID: {p['id']}\n🕐 Time: {t}\n📝 Text: {p['text']}"))

async def list_command(update, context):
    if not await require_owner(update): return
    posts = autopost_data.get("posts", [])
    if not posts:
        await update.effective_message.reply_text(info_box("কোনো Scheduled Post নেই।")); return
    lines = [vip_header("AUTO POST LIST"), ""]
    for p in posts:
        lines.append(f"🆔 ID: {p.get('id')}\n🕐 Time: {p.get('post_time')}\n📦 Type: {'📸 PHOTO' if p.get('photo_file_id') else '📝 TEXT'}\n📡 Status: {'🟢 ON' if p.get('enabled', True) else '🔴 OFF'}\n💬 {p.get('text', '')[:250]}\n━━━━━━━━━━━━━━━━━━━━")
    await update.effective_message.reply_text("\n".join(lines))

async def delete_command(update, context):
    if not await require_owner(update): return
    if not context.args:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: /delete POST_ID")); return
    try: pid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(error_box("Post ID সঠিক নয়।")); return
    posts = autopost_data.get("posts", [])
    new_posts = [p for p in posts if int(p.get("id", 0)) != pid]
    if len(new_posts) == len(posts):
        await update.effective_message.reply_text(error_box(f"Post ID {pid} পাওয়া যায়নি।")); return
    autopost_data["posts"] = new_posts; renumber_posts(); save_all()
    await update.effective_message.reply_text(owner_reply(f"🗑️ Post ID {pid} Delete হয়েছে।"))

async def clear_command(update, context):
    if await require_owner(update):
        autopost_data["posts"] = []; save_all()
        await update.effective_message.reply_text(owner_reply("🧹 সব Scheduled Post Clear করা হয়েছে।"))

async def post_command(update, context):
    if not await require_owner(update): return
    raw = (update.effective_message.text or "").split(" ", 1)
    if len(raw) < 2:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: /post আপনার বার্তা")); return
    ai_post = await create_ai_post(raw[1].strip())
    sent, failed = await send_to_groups(context, ai_post)
    await update.effective_message.reply_text(owner_reply(f"📢 Group/Channel Post Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))

async def broadcast_command(update, context):
    if not await require_owner(update): return
    raw = (update.effective_message.text or "").split(" ", 1)
    if len(raw) < 2:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: /broadcast আপনার বার্তা")); return
    sent, failed = await send_to_groups(context, raw[1].strip())
    await update.effective_message.reply_text(owner_reply(f"📣 Broadcast Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))

async def test_command(update, context):
    if not await require_owner(update): return
    text = ("╔════════════════════════════╗\n       👑 RJ TEAM TEST\n╚════════════════════════════╝\n\n"
            "💎 Destination connection successful.\n📡 Premium AI Bot is active.\n🇧🇩 Bangladesh Time System Active.")
    sent, failed = await send_to_groups(context, text)
    await update.effective_message.reply_text(owner_reply(f"🧪 Test Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))

# ========================= AUTO POST WORKER ==================
async def autopost_worker(application):
    logging.info("Auto-post worker started.")
    while True:
        try:
            if autopost_data.get("enabled", True):
                now = datetime.now(BD)
                current_time, today = now.strftime("%H:%M"), now.strftime("%Y-%m-%d")
                changed = False
                for p in autopost_data.get("posts", []):
                    if not p.get("enabled", True) or p.get("post_time") != current_time or p.get("last_run_date", "") == today:
                        continue
                    if p.get("photo_file_id"):
                        await send_photo_to_groups(application, p["photo_file_id"], p.get("text", ""))
                    else:
                        await send_to_groups(application, p.get("text", ""))
                    p["last_run_date"] = today; changed = True
                if changed: save_all()
        except Exception:
            logging.exception("Auto worker error")
        await asyncio.sleep(20)

# ========================= PHOTO HANDLER =====================
async def photo_handler(update, context):
    message, user = update.effective_message, update.effective_user
    if not message or not user or not message.photo: return
    register_user(user); save_all()
    caption, photo_id = (message.caption or "").strip(), message.photo[-1].file_id
    if is_owner(user):
        m = re.match(r"^([0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)\s*\|\s*(.*)$", caption, re.I | re.S)
        if m:
            t = parse_time(m.group(1))
            if t:
                p = {"id": next_post_id(), "post_time": t, "text": m.group(2).strip(), "photo_file_id": photo_id, "enabled": True, "last_run_date": ""}
                autopost_data.setdefault("posts", []).append(p); save_all()
                await message.reply_text(owner_reply(f"📸 Photo Scheduled Post Added!\n\n🆔 ID: {p['id']}\n🕐 Time: {t}\n🟢 Status: ON")); return
        explicit = extract_group_post(caption)
        if explicit:
            ai_caption = await create_ai_post(explicit)
            sent, failed = await send_photo_to_groups(context, photo_id, ai_caption)
            await message.reply_text(owner_reply(f"📸 Photo Group Post Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}")); return
        if OWNER_SMS_TO_GROUP:
            ai_caption = await create_ai_post(caption or "এই ছবিটি RJ TEAM BANGLADESH-এর পক্ষ থেকে।")
            sent, failed = await send_photo_to_groups(context, photo_id, ai_caption)
            await message.reply_text(owner_reply(f"📸 Photo Group Post Complete!\n\n✅ Sent: {sent}\n❌ Failed: {failed}"))
        else:
            await message.reply_text(owner_reply("📸 Photo পেয়েছি, বস।\nInbox SMS OFF থাকায় এটি Group/Channel-এ পাঠানো হয়নি।"))
        return
    if USER_SMS_TO_GROUP.get(str(user.id), False):
        ai_caption = await create_ai_post(caption or "একটি নতুন Photo Post")
        sent, failed = await send_photo_to_groups(context, photo_id, ai_caption)
        await message.reply_text(f"📸 Premium Photo Post তৈরি হয়েছে.\n\n📢 Group/Channel Sent: {sent}")
    else:
        await message.reply_text("📸 Photo received successfully.")

# ========================= USER MESSAGING ====================
async def sendmsg_command(update, context):
    if not await require_owner(update): return
    parts = (update.effective_message.text or "").split(" ", 2)
    if len(parts) < 3:
        await update.effective_message.reply_text(owner_reply("ব্যবহার: /sendmsg USER_ID আপনার বার্তা")); return
    target, send_text = parts[1].strip(), parts[2].strip()
    key = target.lower() if target.startswith("@") else target
    data = USER_REGISTRY.get(key)
    if not data:
        await update.effective_message.reply_text(owner_reply("❌ User আগে Bot-এ /start দেয়নি বা Registry-তে নেই।")); return
    try:
        await context.bot.send_message(chat_id=int(data["user_id"]), text=send_text)
        await update.effective_message.reply_text(owner_reply(f"✅ Message পাঠানো হয়েছে.\n\n👤 User ID: {data['user_id']}"))
    except Exception:
        logging.exception("sendmsg failed")
        await update.effective_message.reply_text(error_box("Message পাঠানো যায়নি। User Bot block করেছে কিনা পরীক্ষা করুন।"))

# ========================= TRANSLATION =======================
async def translate_command(update, context):
    parts = (update.effective_message.text or "").split(" ", 2)
    if len(parts) < 3:
        await update.effective_message.reply_text(info_box("ব্যবহার: /translate bn Hello brother")); return
    result = await ask_gemini("Translate the following text into " + parts[1] + ". Return only the translation.\n\n" + parts[2])
    user_last_ai_reply[update.effective_user.id] = result
    await update.effective_message.reply_text("🌐 TRANSLATION\n\n" + result)

async def translate_last_command(update, context):
    if not context.args:
        await update.effective_message.reply_text(info_box("ব্যবহার: /translate_last bn")); return
    last = user_last_ai_reply.get(update.effective_user.id)
    if not last:
        await update.effective_message.reply_text(error_box("আপনার কোনো আগের AI Reply পাওয়া যায়নি।")); return
    result = await ask_gemini("Translate this into " + context.args[0] + ". Return only the translation:\n\n" + last)
    await update.effective_message.reply_text("🔁 TRANSLATED LAST REPLY\n\n" + result)

# ========================= START / HELP ======================
async def start_command(update, context):
    register_user(update.effective_user); save_all()
    if is_owner(update.effective_user):
        await update.effective_message.reply_text(owner_reply(
            "Welcome Back!\n\n💎 RJ TEAM BANGLADESH Premium AI Bot\n🤖 Gemini AI: configured\n📡 Group/Channel System: Ready\n\n/inboxsms — Inbox SMS ON/OFF buttons\n/help — সব command"
        ), reply_markup=inbox_sms_keyboard())
    else:
        await update.effective_message.reply_text(vip_header("WELCOME") +
            "\n\n🤖 RJ TEAM Premium AI Bot-এ স্বাগতম।\n\n💬 আপনার প্রশ্ন লিখুন।\n/about — About\n/help — Help" + vip_footer())

async def about_command(update, context):
    await update.effective_message.reply_text(vip_header("ABOUT RJ TEAM") +
        "\n\n👑 RJ TEAM BANGLADESH\n💎 Premium AI Bot\n🤖 Gemini AI Powered\n🇧🇩 Bangladesh Timezone\n📡 Multi Group / Channel System\n🔥 Firebase Backup" + vip_footer())

async def help_command(update, context):
    if is_owner(update.effective_user):
        text = (
            vip_header("OWNER CONTROL") + "\n\n"
            "📌 GROUP / CHANNEL\n/addgroup @username\n/addchannel @username\n/addchat @username\n/groups\n/delgroup @username\n/delchannel @username\n/test\n\n"
            "📌 INBOX SMS CONTROL\n/inboxsms — ON/OFF buttons\n/smson — ON\n/smsoff — OFF\n/smsstatus — Status\n\n"
            "📌 POST\n/post আপনার বার্তা\n/broadcast আপনার বার্তা\n/addpost 08:00 | আপনার বার্তা\n/list\n/delete ID\n/clear\n\n"
            "📌 AUTO POST\n/on — Auto Post ON\n/off — Auto Post OFF\n/autopost — Status\n/status — Full Status\n\n"
            "📌 USER\n/sendmsg USER_ID message\n123456789 sms on\n123456789 sms off\n123456789 sms status\n\n"
            "📌 AI\n/translate bn text\n/translate_last bn\n\n"
            "🟢 Inbox SMS ON: সাধারণ text AI caption হয়ে active Group/Channel-এ যাবে।\n"
            "🔴 Inbox SMS OFF: সাধারণ প্রশ্নের AI উত্তর Inbox-এ আসবে।"
        )
        await update.effective_message.reply_text(text + vip_footer(), reply_markup=inbox_sms_keyboard())
    else:
        await update.effective_message.reply_text(vip_header("PREMIUM AI HELP") + "\n\n🤖 যেকোনো প্রশ্ন লিখুন।\n/translate bn Hello\n/about" + vip_footer())

async def cancel_command(update, context):
    if await require_owner(update):
        await update.effective_message.reply_text(owner_reply("❌ কোনো pending operation ছিল না।"))

# ========================= NORMAL TEXT =======================
async def normal_message(update, context):
    message, user = update.effective_message, update.effective_user
    if not message or not user: return
    text = (message.text or "").strip()
    if not text: return
    register_user(user); save_all()
    if is_owner(user):
        if await owner_text_control(update, context, text): return
        if OWNER_SMS_TO_GROUP:
            ai_post = await create_ai_post(text)
            sent, failed = await send_to_groups(context, ai_post)
            await message.reply_text(owner_reply(
                "📢 আপনার Inbox SMS থেকে সুন্দর Premium Caption তৈরি করে Group/Channel-এ পাঠানো হয়েছে।\n\n"
                f"✅ Sent: {sent}\n❌ Failed: {failed}"
            ))
        else:
            answer = await ask_gemini("Owner @RJteam1 বলেছেন:\n\n" + text)
            user_last_ai_reply[user.id] = answer
            await message.reply_text(owner_reply(answer))
        return
    if USER_SMS_TO_GROUP.get(str(user.id), False):
        ai_post = await create_ai_post(text)
        sent, failed = await send_to_groups(context, ai_post)
        await message.reply_text(f"💎 Premium Post তৈরি হয়েছে.\n\n📢 Group/Channel Sent: {sent}\n❌ Failed: {failed}")
        return
    answer = await ask_gemini(text)
    user_last_ai_reply[user.id] = answer
    await message.reply_text(answer)

# ========================= HEALTH SERVER =====================
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

# ========================= POST INIT =========================
async def post_init(application):
    global scheduler_task
    init_firebase()
    firebase_load()
    if not autopost_data.get("groups") and os.path.exists(AUTOPOST_FILE):
        load_local()
    normalize_storage()
    if TARGET_CHAT_ID:
        for raw_id in TARGET_CHAT_ID.split(","):
            raw_id = raw_id.strip()
            if not raw_id: continue
            try:
                cid = int(raw_id)
                autopost_data.setdefault("groups", {}).setdefault(str(cid), {
                    "id": cid, "title": "Configured Destination", "username": "",
                    "type": "group", "added_at": datetime.now(BD).isoformat(), "active": True,
                })
            except ValueError:
                logging.warning("Invalid TARGET_CHAT_ID: %s", raw_id)
    save_all()
    if scheduler_task is None:
        scheduler_task = asyncio.create_task(autopost_worker(application))
    logging.info("RJ TEAM BANGLADESH bot initialized.")

# ========================= ERROR HANDLER =====================
async def error_handler(update, context):
    logging.error("Telegram update error: %s", context.error, exc_info=context.error)

# ========================= MAIN ==============================
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
    )
    load_local()
    normalize_storage()
    init_firebase()
    init_gemini()
    start_health_server()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    commands = {
        "start": start_command, "help": help_command, "about": about_command,
        "addgroup": addgroup_command, "addchannel": addchannel_command, "addchat": addchat_command,
        "groups": groups_command, "delgroup": delgroup_command, "delchannel": delchannel_command,
        "removegroup": removegroup_command, "removechannel": removechannel_command,
        "on": on_command, "off": off_command, "status": status_command, "autopost": status_command,
        "smson": smson_command, "smsoff": smsoff_command, "smsstatus": smsstatus_command,
        "inboxsms": inboxsms_command, "post": post_command, "broadcast": broadcast_command,
        "addpost": addpost_command, "list": list_command, "delete": delete_command, "clear": clear_command,
        "test": test_command, "sendmsg": sendmsg_command, "translate": translate_command,
        "translate_last": translate_last_command, "cancel": cancel_command,
    }
    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, normal_message))
    app.add_error_handler(error_handler)
    logging.info("RJ TEAM BANGLADESH PREMIUM AI BOT | Owner: @%s", ADMIN_USERNAME)
    logging.info("Gemini models configured: %s", ", ".join(GEMINI_MODELS))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
