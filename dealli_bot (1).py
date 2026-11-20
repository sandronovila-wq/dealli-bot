import os, sqlite3
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

TOKEN=os.getenv('BOT_TOKEN'); ADMIN_ID=int(os.getenv('ADMIN_ID','0'))
BASE=os.getenv('RENDER_EXTERNAL_URL','').rstrip('/'); SECRET=os.getenv('WEBHOOK_SECRET','dealli-secret-change-this')
DB='dealli.db'; PATH='/telegram-webhook'
if not TOKEN or not ADMIN_ID or not BASE: raise RuntimeError('Set BOT_TOKEN, ADMIN_ID and deploy on Render Web Service')
bot=Bot(TOKEN); dp=Dispatcher()
def conn(): return sqlite3.connect(DB)
def init_db():
 with conn() as c:
  c.execute('CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, joined_at TEXT, notifications INTEGER DEFAULT 1)')
  c.execute('CREATE TABLE IF NOT EXISTS deals(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,price TEXT,old_price TEXT,url TEXT,category TEXT,description TEXT,created_at TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,query TEXT,created_at TEXT)')
def menu():
 k=InlineKeyboardBuilder(); k.button(text='🔥 Предложения',callback_data='deals'); k.button(text='🔎 Найти товар',callback_data='search'); k.button(text='🔔 Уведомления',callback_data='notifications'); k.button(text='ℹ️ О боте',callback_data='about'); k.adjust(1); return k.as_markup()
def cats():
 k=InlineKeyboardBuilder()
 for label,cat in [('Все','all'),('Техника','tech'),('Игры','gaming'),('Одежда','clothes')]: k.button(text=label,callback_data='cat:'+cat)
 k.button(text='🏠 Меню',callback_data='home'); k.adjust(1); return k.as_markup()
@dp.message(Command('start'))
async def start(m:Message):
 with conn() as c: c.execute('INSERT OR IGNORE INTO users(user_id,joined_at) VALUES(?,?)',(m.from_user.id,datetime.now().isoformat()))
 await m.answer('Привет! DEALLI помогает находить интересные предложения. Выбирай раздел:',reply_markup=menu())
@dp.callback_query(F.data=='home')
async def home(q:CallbackQuery): await q.message.edit_text('Главное меню:',reply_markup=menu()); await q.answer()
@dp.callback_query(F.data=='deals')
async def deals(q:CallbackQuery): await q.message.edit_text('Выбери категорию:',reply_markup=cats()); await q.answer()
@dp.callback_query(F.data.startswith('cat:'))
async def category(q:CallbackQuery):
 cat=q.data.split(':')[1]
 with conn() as c:
  rows=c.execute('SELECT title,price,old_price,url,description FROM deals'+('' if cat=='all' else ' WHERE category=?')+' ORDER BY id DESC LIMIT 10',() if cat=='all' else (cat,)).fetchall()
 text='Пока предложений нет. Скоро добавим первые находки.' if not rows else ''
 for title,price,old,url,desc in rows:
  text+=f'\n\n🛍 <b>{title}</b>\n💰 {price}'+(f' (было {old})' if old else '')+(f'\n{desc}' if desc else '')+(f'\n<a href="{url}">Открыть</a>' if url else '')
 k=InlineKeyboardBuilder(); k.button(text='⬅️ Категории',callback_data='deals'); k.button(text='🏠 Меню',callback_data='home'); k.adjust(1)
 await q.message.edit_text(text,reply_markup=k.as_markup(),parse_mode='HTML',disable_web_page_preview=True); await q.answer()
@dp.callback_query(F.data=='search')
async def search(q:CallbackQuery): await q.message.answer('Напиши товар и бюджет, например: наушники до 30€'); await q.answer()
@dp.message(F.text & ~F.text.startswith('/'))
async def request(m:Message):
 with conn() as c: c.execute('INSERT INTO requests(user_id,query,created_at) VALUES(?,?,?)',(m.from_user.id,m.text,datetime.now().isoformat()))
 await m.answer('Запрос записан!');
 try: await bot.send_message(ADMIN_ID,f'Запрос от {m.from_user.id}: {m.text}')
 except: pass
@dp.callback_query(F.data=='notifications')
async def notify(q:CallbackQuery):
 with conn() as c:
  row=c.execute('SELECT notifications FROM users WHERE user_id=?',(q.from_user.id,)).fetchone(); v=0 if row and row[0] else 1
  c.execute('INSERT OR IGNORE INTO users(user_id,joined_at) VALUES(?,?)',(q.from_user.id,datetime.now().isoformat())); c.execute('UPDATE users SET notifications=? WHERE user_id=?',(v,q.from_user.id))
 k=InlineKeyboardBuilder(); k.button(text='Переключить',callback_data='notifications'); k.button(text='Меню',callback_data='home'); k.adjust(1)
 await q.message.edit_text('Уведомления '+('включены' if v else 'выключены'),reply_markup=k.as_markup()); await q.answer()
@dp.callback_query(F.data=='about')
async def about(q:CallbackQuery):
 k=InlineKeyboardBuilder(); k.button(text='Назад',callback_data='home'); await q.message.edit_text('DEALLI — подборка выгодных покупок. Проверяй цену и наличие у продавца.',reply_markup=k.as_markup()); await q.answer()
@dp.message(Command('deal'))
async def add_deal(m:Message):
 if m.from_user.id!=ADMIN_ID: return
 parts=m.text.split('|',5)
 if len(parts)<6: await m.answer('/deal tech | Название | Цена | Старая цена | URL | Описание'); return
 category=parts[0].split(maxsplit=1)[1].strip(); title,price,old,url,desc=[x.strip() for x in parts[1:6]]
 with conn() as c:
  c.execute('INSERT INTO deals(title,price,old_price,url,category,description,created_at) VALUES(?,?,?,?,?,?,?)',(title,price,old,url,category,desc,datetime.now().isoformat())); users=c.execute('SELECT user_id FROM users WHERE notifications=1').fetchall()
 await m.answer('Добавлено: '+title)
 for (uid,) in users:
  try: await bot.send_message(uid,f'🔥 {title}\nЦена: {price}'+(f' Было: {old}' if old else '')+(f'\n{desc}' if desc else '')+(f'\n{url}' if url else ''))
  except: pass
@dp.message(Command('stats'))
async def stats(m:Message):
 if m.from_user.id!=ADMIN_ID:return
 with conn() as c: u=c.execute('select count(*) from users').fetchone()[0]; d=c.execute('select count(*) from deals').fetchone()[0]; r=c.execute('select count(*) from requests').fetchone()[0]
 await m.answer(f'Пользователи: {u}\nПредложения: {d}\nЗапросы: {r}')
async def startup(app):
 init_db(); await bot.set_webhook(BASE+PATH,secret_token=SECRET,drop_pending_updates=True)
async def shutdown(app): await bot.delete_webhook(); await bot.session.close()
def app():
 a=web.Application(); h=SimpleRequestHandler(dp,bot,secret_token=SECRET); h.register(a,path=PATH); setup_application(a,dp,bot=bot); a.on_startup.append(startup); a.on_shutdown.append(shutdown); a.router.add_get('/',lambda r:web.Response(text='DEALLI is alive')); return a
if __name__=='__main__': web.run_app(app(),host='0.0.0.0',port=int(os.getenv('PORT','10000')))
