import os
import asyncio
import logging
import random
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

# =========================================================
# CONFIG
# =========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "RJteam1").strip().lstrip("@")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "").strip()
AUTOPOST_FILE = os.getenv("AUTOPOST_FILE", "autoposts.json")
BD_TZ = ZoneInfo("Asia/Dhaka")
AUTOPOST_ENABLED = os.getenv("AUTOPOST_ENABLED", "true").strip().lower() == "true"

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
FIREBASE_COLLECTION = os.getenv("AUTOPOST_FIREBASE_COLLECTION", "rj_bot_config").strip()
FIREBASE_DOCUMENT = os.getenv("AUTOPOST_FIREBASE_DOCUMENT", "autopost").strip()

# =========================================================
# FIREBASE
# =========================================================
def init_firebase():
    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON is not set. Using local storage.")
        return None
    try:
        if not firebase_admin._apps:
            service_account = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
            firebase_admin.initialize_app(credentials.Certificate(service_account))
        return firestore.client()
    except Exception as e:
        logger.error("Firebase initialization failed: %s", e, exc_info=True)
        return None

FIRESTORE_DB = init_firebase()

# =========================================================
# AUTOPOST STORAGE
# =========================================================
def _local_load_autopost_data():
    default = {"posts": [], "next_id": 1, "enabled": AUTOPOST_ENABLED, "groups": []}
    try:
        if not os.path.exists(AUTOPOST_FILE):
            return default
        with open(AUTOPOST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in default.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        logger.error("Could not load local autopost data: %s", e)
        return default

def load_autopost_data():
    local = _local_load_autopost_data()
    if FIRESTORE_DB is None:
        return local
    try:
        ref = FIRESTORE_DB.collection(FIREBASE_COLLECTION).document(FIREBASE_DOCUMENT)
        snap = ref.get()
        if snap.exists:
            data = snap.to_dict() or {}
            data.setdefault("posts", [])
            data.setdefault("next_id", 1)
            data.setdefault("enabled", AUTOPOST_ENABLED)
            data.setdefault("groups", [])
            return data
        ref.set(local)
        return local
    except Exception as e:
        logger.error("Could not load Firebase data: %s", e, exc_info=True)
        return local

AUTOPOST_DATA = load_autopost_data()

def save_autopost_data():
    data = {
        "posts": AUTOPOST_DATA.get("posts", []) or [],
        "next_id": int(AUTOPOST_DATA.get("next_id", 1)),
        "enabled": bool(AUTOPOST_DATA.get("enabled", True)),
        "groups": AUTOPOST_DATA.get("groups", []) or [],
    }
    try:
        tmp = AUTOPOST_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, AUTOPOST_FILE)
    except Exception as e:
        logger.error("Could not save local backup: %s", e)
    if FIRESTORE_DB is not None:
        try:
            FIRESTORE_DB.collection(FIREBASE_COLLECTION).document(FIREBASE_DOCUMENT).set(data)
        except Exception as e:
            logger.error("Could not save Firebase data: %s", e, exc_info=True)

def normalize_autopost_ids(save=True):
    posts = AUTOPOST_DATA.get("posts", []) or []
    changed = False
    for i, post in enumerate(posts, 1):
        if post.get("id") != i:
            post["id"] = i
            changed = True
    expected = len(posts) + 1
    if AUTOPOST_DATA.get("next_id") != expected:
        AUTOPOST_DATA["next_id"] = expected
        changed = True
    if changed and save:
        save_autopost_data()

normalize_autopost_ids(save=False)

def get_saved_groups():
    cleaned, seen = [], set()
    for g in AUTOPOST_DATA.get("groups", []) or []:
        try:
            cid = int(g.get("chat_id"))
        except Exception:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        cleaned.append({
            "chat_id": cid,
            "title": str(g.get("title") or f"Group {cid}").strip(),
            "username": str(g.get("username") or "").strip().lstrip("@"),
            "active": bool(g.get("active", True)),
        })
    AUTOPOST_DATA["groups"] = cleaned
    return cleaned

def save_group(chat_id, title="", username=""):
    try:
        chat_id = int(chat_id)
    except Exception:
        return False
    groups = get_saved_groups()
    for g in groups:
        if g["chat_id"] == chat_id:
            if title: g["title"] = title
            if username: g["username"] = username.lstrip("@")
            g["active"] = True
            save_autopost_data()
            return False
    groups.append({"chat_id": chat_id, "title": title or f"Group {chat_id}", "username": username.lstrip("@"), "active": True})
    AUTOPOST_DATA["groups"] = groups
    save_autopost_data()
    return True

def delete_group(chat_id):
    try: target = int(chat_id)
    except Exception: return False
    old = get_saved_groups()
    new = [g for g in old if g["chat_id"] != target]
    if len(new) == len(old): return False
    AUTOPOST_DATA["groups"] = new
    save_autopost_data()
    return True

def active_group_ids():
    return [g["chat_id"] for g in get_saved_groups() if g.get("active", True)]

def group_id_from_index(value):
    groups = get_saved_groups()
    try:
        i = int(value) - 1
        return groups[i]["chat_id"] if 0 <= i < len(groups) else None
    except Exception:
        return None

def target_chat_id():
    if not TARGET_CHAT_ID: return None
    try: return int(TARGET_CHAT_ID)
    except ValueError: return TARGET_CHAT_ID

def group_list_text():
    groups = get_saved_groups()
    if not groups:
        return "👥 ACTIVE GROUPS\n\n📦 Total: 0\n\nগ্রুপে /addgroup লিখে আগে গ্রুপটি যোগ করুন।"
    active = sum(1 for g in groups if g.get("active", True))
    lines = ["👥 GROUPS", "", f"📦 Total: {len(groups)}", f"🟢 Active: {active}", ""]
    for i, g in enumerate(groups, 1):
        status = "🟢 Active" if g.get("active", True) else "⏸️ Paused"
        uname = f"\n🔗 @{g['username']}" if g.get("username") else ""
        lines.append(f"{i}️⃣ {g['title']}\n🆔 {g['chat_id']}{uname}\n{status}")
        lines.append("")
    return "\n".join(lines).strip()

def parse_ampm_time(value):
    value = value.strip().upper().replace(".", "")
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try: return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError: pass
    return None

def display_time(hhmm):
    try: return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except Exception: return hhmm

def add_autopost(time_hhmm, post_type, text="", photo_file_id=None, target_groups=None):
    normalize_autopost_ids(save=False)
    posts = AUTOPOST_DATA.setdefault("posts", [])
    post_id = len(posts) + 1
    posts.append({
        "id": post_id, "time": time_hhmm, "type": post_type, "text": text or "",
        "photo_file_id": photo_file_id, "last_sent_by_group": {},
        "target_groups": target_groups or [],
    })
    AUTOPOST_DATA["next_id"] = len(posts) + 1
    save_autopost_data()
    return post_id

def delete_autopost(post_id):
    normalize_autopost_ids(save=False)
    try: target = int(post_id)
    except Exception: return False
    posts = [p for p in AUTOPOST_DATA.get("posts", []) if int(p.get("id", -1)) != target]
    if len(posts) == len(AUTOPOST_DATA.get("posts", [])): return False
    for i, p in enumerate(posts, 1): p["id"] = i
    AUTOPOST_DATA["posts"] = posts
    AUTOPOST_DATA["next_id"] = len(posts) + 1
    save_autopost_data()
    return True

def find_autopost(post_id):
    for p in AUTOPOST_DATA.get("posts", []):
        try:
            if int(p.get("id", -1)) == int(post_id): return p
        except Exception: pass
    return None

def autopost_detail_text(post):
    ptype = "📷 Photo Post" if post.get("type") == "photo" else "📝 Text Post"
    status = "🟢 ON" if AUTOPOST_DATA.get("enabled", True) else "🔴 OFF"
    return (f"📋 Saved Auto Post\n\n🆔 ID: {post.get('id')}\n"
            f"⏰ Time: {display_time(post.get('time',''))}\n📌 Type: {ptype}\n"
            f"⚙️ Auto Post: {status}\n\n📝 Caption:\n{post.get('text') or '(কোনো caption নেই)'}")

def autopost_detail_keyboard(pid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit", callback_data=f"autopost_edit:{pid}"),
         InlineKeyboardButton("🗑️ Delete", callback_data=f"autopost_delete:{pid}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"autopost_refresh:{pid}")],
    ])

# =========================================================
# ADMIN / OWNER
# =========================================================
def is_admin(update: Update):
    user = update.effective_user
    if not user: return False
    if ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID: return True
    return bool(user.username) and user.username.lstrip("@").lower() == ADMIN_USERNAME.lower()

async def admin_only(update):
    if is_admin(update): return True
    if update.message: await update.message.reply_text("⛔ এই command শুধু Owner/Admin ব্যবহার করতে পারবে।")
    return False

# =========================================================
# GEMINI
# =========================================================
client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]
GEMINI_SEMAPHORE = asyncio.Semaphore(3)

SYSTEM_PROMPT = """
তুমি একটি বন্ধুসুলভ Telegram AI Assistant। ব্যবহারকারী যে ভাষাতেই লিখুক, সাধারণ উত্তর বাংলায় দাও।
প্রশ্নের সরাসরি উত্তর দাও, Banglish হলে বাংলা অক্ষরে উত্তর দেওয়ার চেষ্টা করো। মজার SMS হলে হালকা মজার,
দুঃখের হলে সহানুভূতিশীল, romantic হলে কোমল, গুরুতর বিষয়ে মজা নয়। উত্তর Telegram-এর জন্য সংক্ষিপ্ত ও natural রাখো।
"""

def is_transient_error(s):
    s = s.lower()
    return any(x in s for x in ["429","500","502","503","504","resource_exhausted","unavailable","timeout","rate limit","too many requests"])

async def generate_gemini(prompt, system_instruction=None):
    async with GEMINI_SEMAPHORE:
        for model in GEMINI_MODELS:
            for attempt in range(2):
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        max_output_tokens=500,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    )
                    response = await client.aio.models.generate_content(model=model, contents=prompt, config=config)
                    answer = (response.text or "").strip()
                    if answer: return answer
                    break
                except Exception as e:
                    logger.error("Gemini error model=%s attempt=%s: %s", model, attempt + 1, e)
                    if is_transient_error(str(e)) and attempt == 0:
                        await asyncio.sleep(1.5 + random.random())
                    else:
                        break
    return None

async def ai_reply(text):
    answer = await generate_gemini(text, SYSTEM_PROMPT)
    return answer or "😅 এই মুহূর্তে AI সার্ভার ব্যস্ত আছে। একটু পরে আবার চেষ্টা করো। ❤️"

async def translate_text(text):
    prompt = f"""Translate the following text naturally. Detect the source language. If no target language is specified, translate into Bangla. Return only the translation.\n\nText:\n{text}"""
    return await generate_gemini(prompt, "You are a professional translation assistant. Return only the requested translation.") or "❌ Translation সার্ভার এই মুহূর্তে ব্যস্ত।"

# =========================================================
# OWNER NATURAL COMMANDS
# =========================================================
async def owner_natural_command(update, context, text):
    """@RJteam1-এর সাধারণ বাংলা/Banglish control message-কে নিরাপদ bot actions-এ map করে।"""
    if not is_admin(update): return False
    t = text.strip().lower()
    if not t: return False

    # status/list/groups
    if re.search(r"\b(status|স্ট্যাটাস|অবস্থা)\b", t):
        posts = AUTOPOST_DATA.get("posts", []) or []
        await update.message.reply_text(
            f"📊 RJ BOT STATUS\n\n🤖 Auto Post: {'🟢 ON' if AUTOPOST_DATA.get('enabled',True) else '🔴 OFF'}\n"
            f"👥 Groups: {len(get_saved_groups())}\n📋 Saved Posts: {len(posts)}"
        ); return True
    if re.search(r"\b(groups?|গ্রুপ|group list|গ্রুপ লিস্ট)\b", t) and not re.search(r"add|যোগ", t):
        await update.message.reply_text(group_list_text()); return True
    if re.search(r"\b(list|লিস্ট|saved posts?|সব পোস্ট|পোস্টগুলো)\b", t):
        normalize_autopost_ids(save=True)
        posts = AUTOPOST_DATA.get("posts", []) or []
        if not posts:
            await update.message.reply_text("📋 Saved Auto Posts\n\n📦 Total: 0"); return True
        lines = [f"📋 SAVED POSTS — {len(posts)}টি", ""]
        for p in posts:
            lines.append(f"🆔 ID {p['id']} | ⏰ {display_time(p.get('time',''))}\n📝 {p.get('text') or '(খালি)'}")
        await update.message.reply_text("\n\n".join(lines)[:4096]); return True

    # on/off
    if re.search(r"(auto\s*post|অটো\s*পোস্ট).*(off|বন্ধ|বন্ধ কর|disable|stop)", t):
        AUTOPOST_DATA["enabled"] = False; save_autopost_data()
        await update.message.reply_text("⛔ Auto Post OFF করা হয়েছে।"); return True
    if re.search(r"(auto\s*post|অটো\s*পোস্ট).*(on|চালু|চালু কর|enable|start)", t):
        AUTOPOST_DATA["enabled"] = True; save_autopost_data()
        await update.message.reply_text("✅ Auto Post ON করা হয়েছে।"); return True

    # delete post
    m = re.search(r"(?:delete|ডিলিট|মুছ|মুছে).*?(?:id|আইডি)?\s*(\d+)", t)
    if m:
        pid = int(m.group(1))
        ok = delete_autopost(pid)
        await update.message.reply_text(f"{'🗑️ ID '+str(pid)+' delete হয়েছে।' if ok else '❌ ID '+str(pid)+' পাওয়া যায়নি।'}")
        return True

    # add text: "auto post 8:30 pm caption ..."
    m = re.search(r"(?:auto\s*post|অটো\s*পোস্ট).*?(\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2}).*?(?:দাও|যোগ কর|add)?\s*(.*)$", text, re.I)
    if m and not re.search(r"off|বন্ধ|on|চালু|delete|ডিলিট|list|লিস্ট", t):
        hhmm = parse_ampm_time(m.group(1))
        caption = m.group(2).strip(" :-")
        if hhmm and caption:
            pid = add_autopost(hhmm, "text", caption)
            await update.message.reply_text(f"✅ Auto Post যোগ হয়েছে।\n🆔 ID: {pid}\n⏰ {display_time(hhmm)}")
            return True

    # broadcast
    if re.search(r"^(broadcast|ব্রডকাস্ট|সব গ্রুপে পাঠাও|সব গ্রুপে দাও)", t):
        msg = re.sub(r"^(broadcast|ব্রডকাস্ট|সব গ্রুপে পাঠাও|সব গ্রুপে দাও)\s*[:\-]?\s*", "", text, flags=re.I).strip()
        if msg:
            ok = fail = 0
            for cid in active_group_ids():
                try:
                    await context.bot.send_message(cid, msg[:4096], disable_web_page_preview=True); ok += 1
                except Exception: fail += 1
            await update.message.reply_text(f"📢 Broadcast complete\n\n✅ Sent: {ok}\n❌ Failed: {fail}")
            return True

    # Explicitly reject unsupported owner commands instead of pretending they worked.
    if re.search(r"(admin|owner|বস|bot|অটো|পোস্ট|গ্রুপ|broadcast|ব্রডকাস্ট)", t):
        await update.message.reply_text("ℹ️ এই কথাটি বুঝেছি, কিন্তু এর জন্য নির্দিষ্ট safe action নেই। /help লিখে available command দেখুন।")
        return True
    return False

# =========================================================
# COMMANDS
# =========================================================
async def start(update, context):
    if not update.message: return
    kb = [[InlineKeyboardButton("ℹ️ About", callback_data="about"), InlineKeyboardButton("🌐 Translate", callback_data="translate_help")],
          [InlineKeyboardButton("📢 Channel", url="https://t.me/RJteam123890"), InlineKeyboardButton("👑 Owner", url="https://t.me/RJteam1")]]
    await update.message.reply_text("👋 হ্যালো বন্ধু! ❤️\n\nআমি তোমার AI Assistant। 🤖\n\n💬 যেকোনো SMS পাঠাও।\n🌐 Translation-ও করা যাবে।\n\nনিচের Button ব্যবহার করতে পারো 👇", reply_markup=InlineKeyboardMarkup(kb))

async def help_command(update, context):
    if not update.message: return
    await update.message.reply_text(
        "🤖 RJ Team Bot Help\n\n💬 যেকোনো SMS পাঠাও।\n🌐 /translate Hello\nℹ️ /about\n\n"
        "👑 OWNER NATURAL CONTROL\nAuto Post on/off, list, delete ID, status, groups, broadcast—@RJteam1 সাধারণ ভাষায় বললেও bot action বুঝবে।\n\n"
        "👥 ADMIN\n/addgroup\n/groups\n/delgroup 1\n/pausegroup 1\n/renamegroup 1 নতুন নাম\n/broadcast মেসেজ\n/status\n\n"
        "📅 AUTO POST\n/autopost on/off/list\n/autopost add 8:30 PM পোস্ট\n/autopost addphoto 8:30 PM Caption (photo reply)\n/autopost delete 1\n/list\n/delete 1\n/clear\n/on\n/off\n/test"
    )

async def about_command(update, context):
    kb = [[InlineKeyboardButton("👑 Owner", url="https://t.me/RJteam1"), InlineKeyboardButton("📢 Channel", url="https://t.me/RJteam123890")]]
    await update.message.reply_text("🤖 About AI Assistant\n\nআমি RJ Team Bangladesh-এর AI Assistant। ❤️\n\n👑 Owner: @RJteam1\n📢 Channel: @RJteam123890", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

async def translate_command(update, context):
    if not context.args:
        await update.message.reply_text("🌐 /translate Hello, how are you?"); return
    await update.message.chat.send_action("typing")
    await update.message.reply_text("🌐 Translation:\n\n" + await translate_text(" ".join(context.args)), disable_web_page_preview=True)

async def addgroup_command(update, context):
    if not await admin_only(update): return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Group-এর ভিতর থেকে /addgroup দিন।"); return
    save_group(chat.id, chat.title or "Unnamed Group", getattr(chat, "username", "") or "")
    await update.message.reply_text("✅ Group active list-এ আছে।\n\n" + group_list_text())

async def groups_command(update, context):
    if await admin_only(update): await update.message.reply_text(group_list_text())

async def delgroup_command(update, context):
    if not await admin_only(update): return
    if not context.args: await update.message.reply_text("ব্যবহার: /delgroup 1"); return
    raw = context.args[0]; cid = group_id_from_index(raw) if raw.isdigit() and not raw.startswith("-") else None
    if cid is None:
        try: cid = int(raw)
        except Exception: cid = None
    await update.message.reply_text("🗑️ Group delete হয়েছে।\n\n" + group_list_text() if cid and delete_group(cid) else "❌ Group পাওয়া যায়নি।")

async def status_command(update, context):
    if not await admin_only(update): return
    await update.message.reply_text(f"📊 RJ BOT STATUS\n\n🤖 Auto Post: {'🟢 ON' if AUTOPOST_DATA.get('enabled',True) else '🔴 OFF'}\n👥 Groups: {len(get_saved_groups())}\n📋 Posts: {len(AUTOPOST_DATA.get('posts',[]) or [])}\n💾 Storage: Firebase + local backup")

async def pausegroup_command(update, context):
    if not await admin_only(update): return
    if not context.args: await update.message.reply_text("ব্যবহার: /pausegroup 1"); return
    raw=context.args[0]; cid=group_id_from_index(raw) if raw.isdigit() and not raw.startswith("-") else None
    if cid is None:
        try: cid=int(raw)
        except Exception: cid=None
    for g in get_saved_groups():
        if g["chat_id"] == cid:
            g["active"] = not g.get("active",True); save_autopost_data()
            await update.message.reply_text(f"✅ {g['title']} এখন {'🟢 Active' if g['active'] else '⏸️ Paused'}।"); return
    await update.message.reply_text("❌ Group পাওয়া যায়নি।")

async def renamegroup_command(update, context):
    if not await admin_only(update): return
    if len(context.args)<2: await update.message.reply_text("ব্যবহার: /renamegroup 1 নতুন নাম"); return
    raw=context.args[0]; cid=group_id_from_index(raw) if raw.isdigit() and not raw.startswith("-") else None
    if cid is None:
        try: cid=int(raw)
        except Exception: cid=None
    for g in get_saved_groups():
        if g["chat_id"]==cid:
            g["title"]=" ".join(context.args[1:]); save_autopost_data(); await update.message.reply_text("✅ নাম update হয়েছে।"); return
    await update.message.reply_text("❌ Group পাওয়া যায়নি।")

async def broadcast_command(update, context):
    if not await admin_only(update): return
    text=" ".join(context.args).strip()
    if not text and update.message.reply_to_message:
        text=update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    if not text: await update.message.reply_text("ব্যবহার: /broadcast আপনার মেসেজ"); return
    ok=fail=0
    for cid in active_group_ids():
        try: await context.bot.send_message(cid,text[:4096],disable_web_page_preview=True); ok+=1
        except Exception: fail+=1
    await update.message.reply_text(f"📢 Broadcast complete\n\n✅ Sent: {ok}\n❌ Failed: {fail}")

async def autopost_command(update, context):
    if not await admin_only(update): return
    args=context.args
    if not args:
        await update.message.reply_text("/autopost on | off | list | add 8:30 PM পোস্ট | addphoto 8:30 PM Caption | delete 1"); return
    action=args[0].lower()
    if action in ("on","off"):
        AUTOPOST_DATA["enabled"] = action=="on"; save_autopost_data(); await update.message.reply_text(f"{'✅ Auto Post ON' if action=='on' else '⛔ Auto Post OFF'}"); return
    if action=="list": await autopost_list_command(update,context); return
    if action=="delete" and len(args)>1:
        pid=int(args[1]) if args[1].isdigit() else -1; await update.message.reply_text("🗑️ Deleted" if delete_autopost(pid) else "❌ ID পাওয়া যায়নি।"); return
    if action=="add" and len(args)>=3:
        tc=3 if len(args)>2 and args[2].upper() in ("AM","PM") else 2
        hh=parse_ampm_time(" ".join(args[1:tc])); text=" ".join(args[tc:]).strip()
        if hh and text:
            pid=add_autopost(hh,"text",text); await update.message.reply_text(f"✅ Auto Post যোগ হয়েছে।\n🆔 ID: {pid}\n⏰ {display_time(hh)}"); return
    if action=="addphoto" and len(args)>=2:
        tc=3 if len(args)>2 and args[2].upper() in ("AM","PM") else 2
        hh=parse_ampm_time(" ".join(args[1:tc])); r=update.message.reply_to_message
        if hh and r and r.photo:
            caption=" ".join(args[tc:]).strip() or r.caption or ""
            pid=add_autopost(hh,"photo",caption,r.photo[-1].file_id); await update.message.reply_text(f"✅ Photo Auto Post যোগ হয়েছে।\n🆔 ID: {pid}\n⏰ {display_time(hh)}"); return
    await update.message.reply_text("❌ Format ভুল। /help দেখুন।")

async def autopost_list_command(update, context):
    if not await admin_only(update): return
    normalize_autopost_ids(save=True); posts=AUTOPOST_DATA.get("posts",[]) or []
    if not posts: await update.message.reply_text("📋 ALL SAVED AUTO POSTS\n\n📦 Total: 0"); return
    for p in posts:
        await update.message.reply_text(autopost_detail_text(p), reply_markup=autopost_detail_keyboard(p["id"]), disable_web_page_preview=True)

async def delete_command(update, context):
    if await admin_only(update):
        if context.args and context.args[0].isdigit(): await update.message.reply_text("🗑️ Deleted" if delete_autopost(int(context.args[0])) else "❌ ID পাওয়া যায়নি।")
        else: await update.message.reply_text("ব্যবহার: /delete ID")

async def clear_command(update, context):
    if await admin_only(update):
        AUTOPOST_DATA["posts"]=[]; AUTOPOST_DATA["next_id"]=1; save_autopost_data(); await update.message.reply_text("🗑️ সব Auto Post delete হয়েছে।")

async def on_command(update, context):
    if await admin_only(update): AUTOPOST_DATA["enabled"]=True; save_autopost_data(); await update.message.reply_text("✅ Auto Post ON 🟢")
async def off_command(update, context):
    if await admin_only(update): AUTOPOST_DATA["enabled"]=False; save_autopost_data(); await update.message.reply_text("⛔ Auto Post OFF 🔴")
async def test_command(update, context):
    if not await admin_only(update): return
    cid=(active_group_ids() or [target_chat_id()])[0]
    if not cid: await update.message.reply_text("❌ কোনো active group নেই।"); return
    try: await context.bot.send_message(cid,"🧪 RJ Team Auto Post Test সফল হয়েছে।"); await update.message.reply_text("✅ Test sent.")
    except Exception as e: await update.message.reply_text(f"❌ Test failed: {e}")
async def cancel_command(update, context):
    context.user_data.pop("autopost_edit_id",None); await update.message.reply_text("❌ Edit বাতিল করা হয়েছে।")

# =========================================================
# CALLBACKS
# =========================================================
async def autopost_callback_handler(update, context):
    q=update.callback_query
    if not q: return
    if not is_admin(update): await q.answer("⛔ শুধু Owner/Admin",show_alert=True); return
    data=q.data or ""; await q.answer()
    if data=="autopost_list":
        await q.edit_message_text("📋 ALL SAVED AUTO POSTS\n\n" + "\n\n".join(autopost_detail_text(p) for p in AUTOPOST_DATA.get("posts",[]))[:4096]); return
    try: action,pid=data.split(":",1); pid=int(pid)
    except Exception: return
    p=find_autopost(pid)
    if action=="autopost_open":
        if p: await q.message.reply_text(autopost_detail_text(p),reply_markup=autopost_detail_keyboard(pid))
        return
    if action=="autopost_refresh":
        if p: await q.edit_message_text(autopost_detail_text(p),reply_markup=autopost_detail_keyboard(pid))
        return
    if action=="autopost_edit":
        if p:
            context.user_data["autopost_edit_id"]=pid
            await q.message.reply_text(f"✏️ ID {pid} Edit Mode\n\nনতুন format: 10:30 PM|নতুন caption\n/cancel দিয়ে বাতিল করুন।")
        return
    if action=="autopost_delete":
        await q.edit_message_text(f"⚠️ ID {pid} delete করবেন?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes",callback_data=f"autopost_delete_yes:{pid}"),InlineKeyboardButton("❌ No",callback_data=f"autopost_delete_no:{pid}")]])); return
    if action=="autopost_delete_yes":
        await q.edit_message_text("🗑️ Deleted" if delete_autopost(pid) else "❌ ID পাওয়া যায়নি।"); return
    if action=="autopost_delete_no":
        if p: await q.edit_message_text(autopost_detail_text(p),reply_markup=autopost_detail_keyboard(pid))

async def button_handler(update, context):
    q=update.callback_query
    await q.answer()
    if q.data=="about": await about_command(update,context)
    elif q.data=="translate_help": await q.message.reply_text("🌐 /translate Hello, how are you?\n\nডিফল্টভাবে বাংলা translation দেওয়া হবে। ❤️")
    elif q.data=="translate_last":
        text=context.user_data.get("last_ai_reply")
        if text: await q.message.reply_text("🌐 Translation:\n\n"+await translate_text(text))
        else: await q.message.reply_text("❌ আগের reply পাওয়া যাচ্ছে না।")

# =========================================================
# MESSAGE HANDLER
# =========================================================
async def edit_mode_message(update, context):
    pid=context.user_data.get("autopost_edit_id")
    raw=update.message.text.strip()
    if raw.lower()=="/cancel": context.user_data.pop("autopost_edit_id",None); await update.message.reply_text("❌ Edit বাতিল।"); return True
    if "|" not in raw: await update.message.reply_text("Format: 10:30 PM|নতুন caption"); return True
    ts,caption=raw.split("|",1); hh=parse_ampm_time(ts)
    p=find_autopost(pid)
    if not hh or not caption.strip() or not p: await update.message.reply_text("❌ Format/time/ID ঠিক নয়।"); return True
    p["time"]=hh; p["text"]=caption.strip(); p["last_sent_by_group"]={}; save_autopost_data(); context.user_data.pop("autopost_edit_id",None)
    await update.message.reply_text(f"✅ ID {pid} update হয়েছে।\n⏰ {display_time(hh)}\n📝 {caption.strip()}"); return True

async def handle_message(update, context):
    if not update.message or not update.message.text: return
    text=update.message.text.strip()
    if not text: return
    if is_admin(update) and context.user_data.get("autopost_edit_id") is not None:
        if await edit_mode_message(update,context): return
    # Owner's natural language controls are checked before AI.
    if is_admin(update) and await owner_natural_command(update,context,text): return
    await update.message.chat.send_action("typing")
    answer=await ai_reply(text)
    context.user_data["last_ai_reply"]=answer
    await update.message.reply_text(answer,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Translate",callback_data="translate_last")]]),disable_web_page_preview=True)

# =========================================================
# AUTO POST WORKER
# =========================================================
async def auto_post_worker(application):
    logger.info("Automatic multi-group post system started.")
    while True:
        try:
            if AUTOPOST_DATA.get("enabled",True):
                now=datetime.now(BD_TZ); hh=now.strftime("%H:%M"); today=now.strftime("%Y-%m-%d")
                groups=active_group_ids()
                if not groups and TARGET_CHAT_ID:
                    cid=target_chat_id()
                    if cid: save_group(cid,"Legacy Target Group"); groups=active_group_ids()
                changed=False
                for p in AUTOPOST_DATA.get("posts",[]):
                    if p.get("time")!=hh: continue
                    targets=p.get("target_groups") or groups
                    sent=p.setdefault("last_sent_by_group",{})
                    for cid in targets:
                        key=str(cid)
                        if sent.get(key)==today: continue
                        try:
                            if p.get("type")=="photo" and p.get("photo_file_id"):
                                await application.bot.send_photo(cid,p["photo_file_id"],caption=(p.get("text") or "")[:1024] or None)
                            else:
                                await application.bot.send_message(cid,(p.get("text") or "")[:4096],disable_web_page_preview=True)
                            sent[key]=today; changed=True
                        except Exception as e: logger.error("Auto post failed id=%s group=%s: %s",p.get("id"),cid,e)
                if changed: save_autopost_data()
            await asyncio.sleep(20)
        except asyncio.CancelledError: raise
        except Exception as e: logger.error("Auto worker error: %s",e,exc_info=True); await asyncio.sleep(20)

async def post_init(application): application.bot_data["autopost_task"]=asyncio.create_task(auto_post_worker(application))
async def post_shutdown(application):
    task=application.bot_data.get("autopost_task")
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

async def error_handler(update, context): logger.error("Telegram error: %s",context.error,exc_info=True)

# =========================================================
# MAIN
# =========================================================
def main():
    app=(Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build())
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("help",help_command)); app.add_handler(CommandHandler("about",about_command)); app.add_handler(CommandHandler("translate",translate_command))
    app.add_handler(CommandHandler("autopost",autopost_command)); app.add_handler(CommandHandler("addgroup",addgroup_command)); app.add_handler(CommandHandler("groups",groups_command)); app.add_handler(CommandHandler("delgroup",delgroup_command)); app.add_handler(CommandHandler("status",status_command)); app.add_handler(CommandHandler("pausegroup",pausegroup_command)); app.add_handler(CommandHandler("renamegroup",renamegroup_command)); app.add_handler(CommandHandler("broadcast",broadcast_command))
    app.add_handler(CommandHandler("list",autopost_list_command)); app.add_handler(CommandHandler("delete",delete_command)); app.add_handler(CommandHandler("clear",clear_command)); app.add_handler(CommandHandler("on",on_command)); app.add_handler(CommandHandler("off",off_command)); app.add_handler(CommandHandler("test",test_command)); app.add_handler(CommandHandler("cancel",cancel_command))
    app.add_handler(CallbackQueryHandler(autopost_callback_handler,pattern=r"^(autopost_list|autopost_open:\d+|autopost_(edit|delete|refresh|delete_yes|delete_no):\d+)$"))
    app.add_handler(CallbackQueryHandler(button_handler,pattern=r"^(about|translate_help|translate_last)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_message))
    app.add_error_handler(error_handler)
    port=int(os.getenv("PORT","10000")); render_url=os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        app.run_webhook(listen="0.0.0.0",port=port,url_path="telegram/"+BOT_TOKEN,webhook_url=render_url.rstrip("/")+"/telegram/"+BOT_TOKEN,drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)
    else:
        app.run_polling(drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
