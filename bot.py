import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ChatPermissions, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hlink

# --- KONFIGURATSIYA ---
TOKEN = "8623378940:AAFR_EcoSY64xCZAioWwzje6WnhOWF55cUU"
OWNER_ID = 5745296238

DB_FILE = "database.json"

def load_db():
    default = {
        "groups": {}, 
        "users": {},  
        "channels": [], 
        "extra_admins": [], 
        "global_words": ["kazino", "bonus", "stavka", "sex", "qizlar"],
        "punish_levels": {"4": 1, "5": 7, "6": 0} 
    }
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

db = load_db()

class AdminState(StatesGroup):
    waiting_for_word = State()
    waiting_for_del_word = State()
    waiting_for_broadcast = State()
    waiting_for_channel = State()
    waiting_for_admin_id = State()
    waiting_for_punish_step = State()
    waiting_for_punish_days = State()

bot = Bot(token=TOKEN)
dp = Dispatcher()

def is_admin(user_id):
    return user_id == OWNER_ID or user_id in db["extra_admins"]

def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ So'z qo'shish", callback_data="add_word"),
                InlineKeyboardButton(text="❌ So'z o'chirish", callback_data="del_word_start"))
    builder.row(InlineKeyboardButton(text="📜 So'zlar", callback_data="list_words"),
                InlineKeyboardButton(text="📊 Stat", callback_data="view_stat"))
    builder.row(InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="broadcast"),
                InlineKeyboardButton(text="👥 Guruhlar", callback_data="list_groups"))
    builder.row(InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_chan"),
                InlineKeyboardButton(text="⚖️ Jazo sozlash", callback_data="set_punish"))
    builder.row(InlineKeyboardButton(text="👤 Admin qo'shish", callback_data="add_admin_id"))
    return builder.as_markup()

# --- ADMIN HANDLERLAR ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if message.chat.type != "private": return
    
    if is_admin(message.from_user.id):
        await message.answer("💻 **Admin Panelga xush kelibsiz!**", reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    else:
        not_joined = []
        for channel in db["channels"]:
            try:
                member = await bot.get_chat_member(channel, message.from_user.id)
                if member.status in ["left", "kicked"]: not_joined.append(channel)
            except: pass
        
        if not_joined:
            kb = InlineKeyboardBuilder()
            for ch in not_joined:
                kb.row(InlineKeyboardButton(text=f"Obuna bo'lish", url=f"https://t.me/{ch.replace('@', '')}"))
            kb.row(InlineKeyboardButton(text="Tekshirish ✅", callback_data="check_subs"))
            return await message.answer("Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=kb.as_markup())

        bot_info = await bot.get_me()
        add_url = f"https://t.me/{bot_info.username}?startgroup=true"
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="➕ Guruhga qo'shish", url=add_url))
        await message.answer("Salom! Men guruhlarni reklamadan himoya qilaman.", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "check_subs")
async def check_subs(callback: types.CallbackQuery):
    await callback.answer("Tekshirilmoqda...")
    await start_handler(callback.message)

@dp.callback_query(F.data == "broadcast")
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Guruhlarga yuboriladigan xabarni yozing:")
    await state.set_state(AdminState.waiting_for_broadcast)

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    count = 0
    for gid in list(db["groups"].keys()):
        try:
            await bot.send_message(chat_id=int(gid), text=message.text)
            count += 1
            await asyncio.sleep(0.1)
        except: continue
    await message.answer(f"✅ Xabar {count} ta guruhga yuborildi."); await state.clear()

@dp.callback_query(F.data == "add_word")
async def add_word(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Taqiqlangan so'zni yuboring:"); await state.set_state(AdminState.waiting_for_word)

@dp.message(AdminState.waiting_for_word)
async def proc_word(message: types.Message, state: FSMContext):
    word = message.text.lower().strip()
    if word not in db["global_words"]: db["global_words"].append(word); save_db(db)
    await message.answer(f"✅ '{word}' qo'shildi."); await state.clear()

@dp.callback_query(F.data == "del_word_start")
async def del_word(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("O'chirmoqchi bo'lgan so'zni yozing:"); await state.set_state(AdminState.waiting_for_del_word)

@dp.message(AdminState.waiting_for_del_word)
async def proc_del(message: types.Message, state: FSMContext):
    word = message.text.lower().strip()
    if word in db["global_words"]: db["global_words"].remove(word); save_db(db)
    await message.answer(f"🗑 '{word}' o'chirildi."); await state.clear()

# --- JAZO SOZLASH TUGMALARI ---

@dp.callback_query(F.data == "set_punish")
async def punish_start(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for i in range(1, 11):
        builder.add(InlineKeyboardButton(text=str(i), callback_data=f"step_{i}"))
    builder.adjust(5)
    await callback.message.edit_text("Nechanchi ogohlantirish jazosini o'zgartiramiz?", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("step_"))
async def proc_p_step(callback: types.CallbackQuery, state: FSMContext):
    step = callback.data.split("_")[1]
    await state.update_data(step=step)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚫 Faqat ogohlantirish", callback_data="pday_-1"))
    builder.row(InlineKeyboardButton(text="⏳ 1 kun mute", callback_data="pday_1"))
    builder.row(InlineKeyboardButton(text="⏳ 3 kun mute", callback_data="pday_3"))
    builder.row(InlineKeyboardButton(text="⏳ 7 kun mute", callback_data="pday_7"))
    builder.row(InlineKeyboardButton(text="🚷 Abadiy blok", callback_data="pday_0"))
    await callback.message.edit_text(f"{step}-ogohlantirish uchun jazo turini tanlang:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("pday_"))
async def proc_p_days(callback: types.CallbackQuery, state: FSMContext):
    day_val = float(callback.data.split("_")[1])
    data = await state.get_data()
    db["punish_levels"][str(data['step'])] = day_val
    save_db(db)
    await callback.message.edit_text(f"✅ Saqlandi: {data['step']}-ogohlantirish uchun jazo yangilandi."); await state.clear()

@dp.callback_query(F.data == "view_stat")
async def view_stat(callback: types.CallbackQuery):
    total_g = len(db["groups"]); total_s = sum(g.get("stats", 0) for g in db["groups"].values())
    await callback.message.answer(f"📊 Statistika:\n- Guruhlar: {total_g}\n- O'chirilgan reklamalar: {total_s}")

@dp.callback_query(F.data == "list_groups")
async def list_groups(callback: types.CallbackQuery):
    text = "👥 Bot qo'shilgan guruhlar:\n\n"
    for gid in db["groups"]:
        try:
            chat = await bot.get_chat(gid)
            text += f"🔹 {chat.title} (ID: {gid})\n"
        except: text += f"🔹 Noma'lum guruh (ID: {gid})\n"
    await callback.message.answer(text)

@dp.callback_query(F.data == "add_chan")
async def add_chan_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Kanal userneymini yuboring (@ bilan):"); await state.set_state(AdminState.waiting_for_channel)

@dp.message(AdminState.waiting_for_channel)
async def proc_chan(message: types.Message, state: FSMContext):
    if message.text.startswith("@"): db["channels"].append(message.text); save_db(db); await message.answer("✅ Kanal qo'shildi.")
    await state.clear()

@dp.callback_query(F.data == "add_admin_id")
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Yangi admin ID sini yuboring:"); await state.set_state(AdminState.waiting_for_admin_id)

@dp.message(AdminState.waiting_for_admin_id)
async def proc_admin(message: types.Message, state: FSMContext):
    if message.text.isdigit(): db["extra_admins"].append(int(message.text)); save_db(db); await message.answer("✅ Admin qo'shildi.")
    await state.clear()

# --- MODERATSIYA MANTIQI ---

@dp.my_chat_member()
async def on_join(event: types.ChatMemberUpdated):
    if event.new_chat_member.status in ["administrator", "member"]:
        db["groups"][str(event.chat.id)] = {"stats": 0}; save_db(db)

@dp.message()
async def monitor(message: types.Message):
    if not message.chat.type in ["group", "supergroup"]: return
    try:
        m = await message.chat.get_member(message.from_user.id)
        if m.status in ["creator", "administrator"]: return
    except: return

    if message.new_chat_members or message.left_chat_member:
        try: await message.delete()
        except: pass
        return

    text = message.text or message.caption or ""
    is_spam = any(w in text.lower() for w in db["global_words"]) or re.search(r'(https?://|t\.me/|@[\w_]+)', text)

    if is_spam:
        uid, cid = str(message.from_user.id), str(message.chat.id)
        db["users"][uid] = db["users"].get(uid, {"warns": 0})
        db["users"][uid]["warns"] += 1
        db["groups"][cid]["stats"] = db["groups"].get(cid, {}).get("stats", 0) + 1
        save_db(db)

        user_link = f"@{message.from_user.username}" if message.from_user.username else hlink(message.from_user.full_name, f"tg://user?id={message.from_user.id}")
        warns = db["users"][uid]["warns"]
        
        await message.delete()
        days = db["punish_levels"].get(str(warns), -1)
        
        if days == -1:
            msg = await message.answer(f"⚠️ {user_link}, reklama bermang! ({warns}-ogohlantirish)", parse_mode="HTML")
            await asyncio.sleep(259200); await msg.delete()
        else:
            until = datetime.now() + timedelta(days=days) if days > 0 else None
            await message.chat.restrict(uid, permissions=ChatPermissions(can_send_messages=False), until_date=until)
            status = f"{days} kunga" if days > 0 else "abadiy"
            await message.answer(f"🔇 {user_link} {status} bloklandi (Ogohlantirish: {warns}).", parse_mode="HTML")

async def main():
    print("Bot 24/7 rejimda ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
