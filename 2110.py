from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests, re, asyncio, threading, time
import os
import json
from concurrent.futures import ThreadPoolExecutor

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8029254946:AAE8Upy5LoYIYsmcm8Y117Esm_-_MF0-ChA')
app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=20)  # Đủ lớn để phục vụ nhiều yêu cầu đồng thời

TASKS = [
    {"label": "Bypass M88", "type": "m88"},
    {"label": "Bypass FB88", "type": "fb88"},
    {"label": "Bypass 188BET", "type": "188bet"},
    {"label": "Bypass W88", "type": "w88"},
    {"label": "Bypass V9BET", "type": "v9bet"},
    {"label": "Bypass BK8", "type": "bk8"},
]
HELP_BUTTON = {"label": "📖 Hướng dẫn / Hỗ trợ", "callback": "help"}

ADMINS = set([7509896689])
ADMINS_LOCK = threading.Lock()
SPAM_COUNTER = {}
BAN_LIST = {}

def admin_notify(msg: str) -> str:
    return (
        "<b>👑 QUẢN TRỊ VIÊN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{msg}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

ADMIN_GUIDE = (
    "<b>👑 HƯỚNG DẪN QUẢN TRỊ VIÊN</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>CÁC LỆNH QUẢN TRỊ:</b>\n"
    "<code>/ban &lt;user_id&gt; &lt;phút&gt;</code> – Ban user X phút\n"
    "<code>/unban &lt;user_id&gt;</code> – Gỡ ban user\n"
    "<code>/addadmin &lt;user_id&gt;</code> – Thêm admin mới\n"
    "<code>/deladmin &lt;user_id&gt;</code> – Xoá quyền admin\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>LƯU Ý:</b>\n"
    "- Không thể xoá chính mình nếu là admin cuối cùng.\n"
    "- Ban thủ công sẽ ghi đè ban tự động.\n"
    "- /unban sẽ gỡ mọi loại ban.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>Ví dụ:</b>\n"
    "<code>/ban 123456789 10</code> – Ban user 123456789 trong 10 phút\n"
    "<code>/unban 123456789</code> – Gỡ ban user\n"
)

def is_admin(user_id):
    with ADMINS_LOCK:
        return user_id in ADMINS

def auto_unban_loop():
    while True:
        now = time.time()
        to_del = []
        for user_id, ban in list(BAN_LIST.items()):
            if ban['until'] <= now:
                to_del.append(user_id)
        for user_id in to_del:
            del BAN_LIST[user_id]
        time.sleep(5)
threading.Thread(target=auto_unban_loop, daemon=True).start()

def pre_check(user_id):
    if is_admin(user_id):
        return {"status": "ok"}
    ban = BAN_LIST.get(user_id)
    if ban and ban['until'] > time.time():
        return {"status": "banned", "msg": "Bạn đang bị cấm."}
    now = time.time()
    cnts = SPAM_COUNTER.setdefault(user_id, [])
    cnts = [t for t in cnts if now - t < 60]
    cnts.append(now)
    SPAM_COUNTER[user_id] = cnts
    if len(cnts) > 3:
        BAN_LIST[user_id] = {'until': now + 300, 'manual': False}
        return {"status": "spam", "msg": "Bạn đã bị tự động ban 5 phút do spam."}
    return {"status": "ok"}

def handle_admin_command(current_user_id, cmd, args):
    if not is_admin(current_user_id):
        return {"status": "error", "msg": admin_notify("❌ <b>Bạn không có quyền quản trị viên!</b>")}
    if cmd == "/ban":
        if len(args) < 2:
            return {"status": "error", "msg": admin_notify("❌ <b>Cú pháp đúng:</b> <code>/ban &lt;user_id&gt; &lt;số_phút&gt;</code>")}
        target = int(args[0])
        mins = int(args[1])
        now = time.time()
        was_banned = BAN_LIST.get(target)
        BAN_LIST[target] = {'until': now + mins * 60, 'manual': True}
        if was_banned:
            return {"status": "ok", "msg": admin_notify(f"🔁 <b>Đã cập nhật lại thời gian ban <code>{target}</code> thành <b>{mins} phút</b>.</b>")}
        else:
            return {"status": "ok", "msg": admin_notify(f"🔒 <b>Đã ban <code>{target}</code> trong <b>{mins} phút</b>.</b>")}
    elif cmd == "/unban":
        if len(args) < 1:
            return {"status": "error", "msg": admin_notify("❌ <b>Cú pháp đúng:</b> <code>/unban &lt;user_id&gt;</code>")}
        target = int(args[0])
        if target in BAN_LIST:
            del BAN_LIST[target]
            return {"status": "ok", "msg": admin_notify(f"🔓 <b>Đã gỡ ban <code>{target}</code>.</b>")}
        return {"status": "ok", "msg": admin_notify(f"ℹ️ <b>User <code>{target}</code> không bị cấm.</b>")}
    elif cmd == "/addadmin":
        if len(args) < 1:
            return {"status": "error", "msg": admin_notify("❌ <b>Cú pháp đúng:</b> <code>/addadmin &lt;user_id&gt;</code>")}
        target = int(args[0])
        with ADMINS_LOCK:
            ADMINS.add(target)
        return {"status": "ok", "msg": admin_notify(f"✨ <b>Đã thêm admin <code>{target}</code>.</b>")}
    elif cmd == "/deladmin":
        if len(args) < 1:
            return {"status": "error", "msg": admin_notify("❌ <b>Cú pháp đúng:</b> <code>/deladmin &lt;user_id&gt;</code>")}
        target = int(args[0])
        with ADMINS_LOCK:
            if target == current_user_id and len(ADMINS) == 1:
                return {"status": "error", "msg": admin_notify("⚠️ <b>Không thể xoá admin cuối cùng!</b>")}
            ADMINS.discard(target)
        return {"status": "ok", "msg": admin_notify(f"🗑️ <b>Đã xoá quyền admin <code>{target}</code>.</b>")}
    elif cmd == "/adminguide":
        return {"status": "ok", "msg": ADMIN_GUIDE}
    else:
        return {"status": "error", "msg": admin_notify("❌ <b>Lệnh quản trị không hợp lệ!</b>")}

def process_request(user_id, message, bypass_func):
    if message.startswith(('/ban', '/unban', '/addadmin', '/deladmin','/adminguide')):
        parts = message.split()
        return handle_admin_command(user_id, parts[0], parts[1:])
    check = pre_check(user_id)
    if check["status"] != "ok":
        return check
    result = bypass_func(message)
    return {"status": "ok", "msg": result}

def bypass(type):
    config = {
        'm88':   ('M88', 'https://bet88ec.com/cach-danh-bai-sam-loc', 'https://bet88ec.com/', 'taodeptrai'),
        'fb88':  ('FB88', 'https://fb88mg.com/ty-le-cuoc-hong-kong-la-gi', 'https://fb88mg.com/', 'taodeptrai'),
        '188bet':('188BET', 'https://88betag.com/cach-choi-game-bai-pok-deng', 'https://88betag.com/', 'taodeptrailamnhe'),
        'w88':   ('W88', 'https://188.166.185.213/tim-hieu-khai-niem-3-bet-trong-poker-la-gi', 'https://188.166.185.213/', 'taodeptrai'),
        'v9bet': ('V9BET', 'https://v9betse.com/ca-cuoc-dua-cho', 'https://v9betse.com/', 'taodeptrai'),
        'bk8':   ('BK8', 'https://bk8ze.com/cach-choi-bai-catte', 'https://bk8ze.com/', 'taodeptrai')
    }
    if type not in config:
        return f'❌ Sai loại: <code>{type}</code>'
    name, url, ref, code_key = config[type]
    try:
        res = requests.post(f'https://traffic-user.net/GET_MA.php?codexn={code_key}&url={url}&loai_traffic={ref}&clk=1000', timeout=15)
        match = re.search(r'<span id="layma_me_vuatraffic"[^>]*>\s*(\d+)\s*</span>', res.text)
        if match:
            return f'✅ <b>{name}</b> | <b style="color:#32e1b7;">Mã</b>: <code>{match.group(1)}</code>'
        else:
            return f'⚠️ <b>{name}</b> | <span style="color:#ffd166;">Không tìm thấy mã</span>'
    except Exception as e:
        return f'❌ <b>Lỗi khi lấy mã:</b> <code>{e}</code>'

def bypass_with_delay(type):
    start_time = time.time()
    try:
        result = bypass(type)
    except Exception as e:
        result = f"❌ <b>Lỗi hệ thống:</b> <code>{e}</code>"
    elapsed = time.time() - start_time
    if elapsed < 75:
        time.sleep(75 - elapsed)
    return result

@app.route('/bypass', methods=['POST'])
def handle_api():
    json_data = request.get_json()
    user_id = int(json_data.get('user_id', 0))
    message = json_data.get('message', '')
    type = json_data.get('type')
    future = executor.submit(bypass_with_delay, type)
    result = future.result()
    return jsonify({"status": "ok", "msg": result})

@app.route('/', methods=['GET'])
def index():
    return render_template_string(BYPASS_TEMPLATE)

def start_flask():
    app.run(host="0.0.0.0", port=5000, threaded=True)

async def send_main_menu(chat_id, context):
    try:
        user = (await context.bot.get_chat(chat_id)).id
    except Exception:
        user = None
    keyboard = []
    for i in range(0, len(TASKS), 2):
        line = []
        for task in TASKS[i:i+2]:
            line.append(InlineKeyboardButton(task["label"], callback_data=f"bypass:{task['type']}"))
        keyboard.append(line)
    keyboard.append([InlineKeyboardButton(HELP_BUTTON["label"], callback_data=HELP_BUTTON["callback"])])
    if user is not None and is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Hướng dẫn Admin", callback_data="adminguide")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="<b>🔰 CHỌN NHIỆM VỤ BYPASS-BÓNG X:</b>\nBạn có thể tiếp tục chọn nhiệm vụ khác hoặc xem hướng dẫn 👇",
        parse_mode="HTML", reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "mainmenu":
        await send_main_menu(query.message.chat_id, context)
        return
    if data == "adminguide":
        await query.edit_message_text(
            ADMIN_GUIDE, parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Quay lại Menu", callback_data="mainmenu")]
            ])
        )
        return
    if data == "contact_admin":
        await query.edit_message_text(
            "<b>💬 Liên hệ hỗ trợ:</b>\nBạn có thể nhắn trực tiếp cho <b>@doanhvip12</b> qua Telegram:\n<a href='https://t.me/doanhvip1'>@doanhvip1</a>\n\nHoặc tham gia nhóm <b>@doanhvip1</b>",
            parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Quay lại hướng dẫn", callback_data="help")],
                [InlineKeyboardButton("🏠 Quay lại Menu", callback_data="mainmenu")]
            ])
        )
        return
    if data == HELP_BUTTON["callback"]:
        help_text = (
            "<b>📖 HƯỚNG DẪN SỬ DỤNG BOT BYPASS & HỖ TRỢ</b>\n"
            "• Bypass traffic (lấy mã) cho các loại: <b>M88, FB88, 188BET, W88, V9BET, BK8</b>.\n"
            "• Giao diện Telegram cực dễ dùng, thao tác nhanh chóng.\n"
            "━━━━━━━━━━━━━\n"
            "<b>2. CÁCH SỬ DỤNG:</b>\n"
            "– Dùng các NÚT NHIỆM VỤ hoặc lệnh <code>/ym &lt;loại&gt;</code>\n"
            "Ví dụ: <code>/ym m88</code> hoặc <code>/ym bk8</code>\n"
            "━━━━━━━━━━━━━\n"
            "<b>5. HỖ TRỢ & LIÊN HỆ:</b>\n"
            "• Admin: <a href='https://t.me/doanhvip1'>@doanhvip12</a> | Nhóm: <a href='https://t.me/doanhvip1'>https://t.me/doanhvip1</a>\n"
            "<i>Chúc bạn thành công! 🚀</i>"
        )
        help_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Quay lại Menu", callback_data="mainmenu")],
            [InlineKeyboardButton("💬 Liên hệ Admin & Nhóm", callback_data="contact_admin")]
        ])
        await query.edit_message_text(
            help_text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=help_keyboard
        )
        return

    if data.startswith("bypass:"):
        type = data.split(":", 1)[1]
        user = query.from_user.first_name or "User"
        check = pre_check(user_id)
        if check["status"] != "ok":
            await query.edit_message_text(
                f"❌ <b>Lỗi:</b> {check.get('msg', 'Bạn bị giới hạn.')}",
                parse_mode="HTML"
            )
            return
        sent = await query.edit_message_text(
            "⏳ <b>Đã nhận nhiệm vụ!</b>\n"
            "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>75 giây</b>...</i>\n"
            "<b>⏱️ Đang lấy mã, xin đừng gửi lệnh mới...</b>",
            parse_mode="HTML"
        )
        async def delay_and_reply():
            start_time = time.time()
            try:
                result = bypass(type)
            except Exception as e:
                result = f"❌ <b>Lỗi hệ thống:</b> <code>{e}</code>"
            elapsed = time.time() - start_time
            if elapsed < 75:
                await asyncio.sleep(75 - elapsed)
            await sent.edit_text(
                "<b>🎉 KẾT QUẢ BYPASS</b>\n<b>─────────────────────────────</b>\n"
                + result +
                "\n<b>─────────────────────────────</b>",
                parse_mode="HTML"
            )
            await send_main_menu(query.message.chat_id, context)
        asyncio.create_task(delay_and_reply())

async def ym_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message.text
    if message.startswith(('/ban', '/unban', '/addadmin', '/deladmin','/adminguide')):
        parts = message.split()
        result = handle_admin_command(user_id, parts[0], parts[1:])
        await update.message.reply_html(result["msg"])
        return
    check = pre_check(user_id)
    if check["status"] != "ok":
        await update.message.reply_html(
            f"❌ <b>Lỗi:</b> {check.get('msg', '')}"
        )
        return
    if not context.args:
        await update.message.reply_html(
            "📌 <b>Hướng dẫn sử dụng:</b>\n<b>/ym &lt;loại&gt;</b>\nVí dụ: <code>/ym m88</code>\n<b>Các loại hợp lệ:</b> <i>m88, fb88, 188bet, w88, v9bet, bk8</i>"
        )
        return
    type = context.args[0].lower()
    user = update.effective_user.first_name or "User"
    sent = await update.message.reply_html(
        "⏳ <b>Đã nhận lệnh!</b>\n"
        "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>75 giây</b>...</i>\n"
        "<b>⏱️ Đang lấy mã, xin đừng gửi lệnh mới...</b>"
    )
    async def delay_and_reply():
        start_time = time.time()
        try:
            result = bypass(type)
        except Exception as e:
            result = f"❌ <b>Lỗi hệ thống:</b> <code>{e}</code>"
        elapsed = time.time() - start_time
        if elapsed < 75:
            await asyncio.sleep(75 - elapsed)
        await sent.edit_text(
            "<b>🎉 KẾT QUẢ BYPASS</b>\n<b>─────────────────────────────</b>\n" + result + "\n<b>─────────────────────────────</b>",
            parse_mode="HTML"
        )
        await send_main_menu(update.effective_chat.id, context)
    asyncio.create_task(delay_and_reply())

BYPASS_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>BYPASS TRAFFIC | YM5 Tool</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;500&display=swap" rel="stylesheet">
    <style>
        body, html {
            height: 100%; margin: 0; padding: 0;
            font-family: 'Montserrat', 'Segoe UI', sans-serif;
            overflow-x: hidden;
        }
        body {
            min-height: 100vh;
            background: url('https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1400&q=80') no-repeat center center fixed;
            background-size: cover;
            position: relative;
        }
        .overlay {
            position: fixed; left:0; top:0; right:0; bottom:0; z-index:0;
            background: linear-gradient(120deg, #000a 50%, #1a162cbb 100%);
            pointer-events: none;
        }
        .glass {
            background: rgba(255, 255, 255, 0.19);
            margin: 60px 0 0 0;
            border-radius: 28px;
            box-shadow: 0 12px 48px #000a, 0 2px 10px #8efcff22;
            max-width: 430px; width: 95vw;
            padding: 42px 32px 30px 32px;
            position: relative;
            z-index: 2;
            backdrop-filter: blur(10px);
            border: 2.5px solid rgba(255,255,255,0.23);
            animation: fadeInUp 1.2s cubic-bezier(.29,1.29,.77,1.03);
        }
        @keyframes fadeInUp {
            0% { transform: translateY(80px); opacity: 0;}
            100% { transform: translateY(0); opacity: 1;}
        }
        .brand { text-align: center; margin-bottom: 17px;}
        .brand img {
            width: 84px; height: 84px;
            border-radius: 18px;
            box-shadow: 0 2px 32px #6ff6ffcc;
            animation: logoPop 1.2s cubic-bezier(.22,1.11,.77,1.01);
        }
        @keyframes logoPop {
            0% { transform: scale(.2) rotate(-13deg);}
            70% { transform: scale(1.15) rotate(7deg);}
            100% { transform: scale(1) rotate(0);}
        }
        .brand h1 {
            font-size: 2.2rem;
            margin: 14px 0 0 0;
            color: #fff;
            font-weight: 800;
            text-shadow: 0 2px 24px #29e5ff33, 0 2px 3px #1a162c4a;
            letter-spacing: 3px;
            text-transform: uppercase;
            background: linear-gradient(90deg,#ff8a00,#e52e71,#43cea2,#185a9d,#f158ff,#00f2fe);
            background-size: 200% 200%;
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            animation: gradtxt 4s linear infinite alternate;
        }
        @keyframes gradtxt {
            0% {background-position:0 0;}
            100% {background-position:100% 100%;}
        }
        .desc {
            color: #fff;
            font-size: 1.13rem;
            text-align: center;
            margin-bottom: 20px;
            font-weight: 600;
            line-height: 1.6;
            letter-spacing: 0.01em;
            text-shadow: 0 2px 14px #0006;
        }
        select, button {
            width: 100%; padding: 15px;
            margin-top: 21px; border: none; border-radius: 13px;
            font-size: 1.18rem; font-family: inherit;
            transition: background .19s, box-shadow .23s;
            outline: none;
        }
        select {
            background: #ffffff33; color: #31344b;
            box-shadow: 0 2px 12px #3fafff1c;
            font-weight: 600;
        }
        button {
            background: linear-gradient(90deg,#ff8a00,#e52e71,#43cea2,#185a9d,#f158ff,#00f2fe);
            background-size: 300% 300%;
            color: #fff; font-weight: bold; cursor: pointer;
            margin-bottom: 12px; letter-spacing: 2.1px;
            box-shadow: 0 3px 18px #ffb34736;
            border: 2.5px solid #fff9;
            position: relative; overflow: hidden;
            animation: btnGlow 2.2s infinite alternate;
        }
        @keyframes btnGlow {
            0% { box-shadow: 0 0 18px #ff8a0092;}
            100% { box-shadow: 0 0 32px #43cea2e0;}
        }
        button:disabled {
            background: #283c53bb;
            color: #eee;
            cursor: not-allowed;
            box-shadow: none;
        }
        #result {
            margin-top: 22px;
            padding: 22px 6px;
            border-radius: 13px;
            background: rgba(255,255,255, 0.16);
            font-size: 1.22rem;
            min-height: 36px;
            text-align: center;
            font-family: 'Montserrat', monospace, sans-serif;
            font-weight: 700;
            word-break: break-word;
            animation: fadeInResult 0.85s;
        }
        @keyframes fadeInResult {
            0% { opacity:0; transform: scale(0.9);}
            100% { opacity:1; transform: scale(1);}
        }
        .spinner {
            border: 4px solid #eee;
            border-top: 4px solid #00eaff;
            border-radius: 50%;
            width: 38px; height: 38px;
            animation: spin 0.8s linear infinite;
            display: inline-block;
            margin-bottom: -9px;
            margin-right: 6px;
            vertical-align: middle;
            box-shadow: 0 2px 16px #44f6ff44;
        }
        @keyframes spin {
            0% { transform: rotate(0);}
            100% { transform: rotate(360deg);}
        }
        .footer {
            margin-top: 40px; color: #fafffc;
            font-size: 1rem;
            text-align: center; padding-bottom: 20px;
            z-index: 2; position: relative;
            text-shadow: 0 2px 10px #0006;
        }
        .footer a {
            color: #ffd9fa; text-decoration: none; font-weight: 700;
            transition: color .18s;
        }
        .footer a:hover { color: #00e4ff; text-decoration: underline;}
        .timer {
            font-size: 1.11rem; color: #ffd97e;
            font-weight: 700; letter-spacing: 1px;
        }
        .pulse { animation: pulse 1s infinite; }
        @keyframes pulse {
            0% { color: #ffd97e;}
            50% { color: #fff0a8;}
            100% { color: #ffd97e;}
        }
        .click-effect {
            position: absolute; pointer-events: none;
            border-radius: 50%;
            background: rgba(255,120,255,0.23);
            animation: clickpop 0.6s linear forwards;
            z-index: 4;
        }
        @keyframes clickpop {
            0% { opacity:1; transform: scale(0);}
            80% { opacity:0.8; }
            100% { opacity:0; transform: scale(2.9);}
        }
        @media (max-width: 540px) {
            .glass { padding: 16px 2vw 16px 2vw; }
            .brand h1 { font-size: 1.07rem; }
            .footer { font-size: 0.91rem;}
        }
    </style>
</head>
<body>
    <div class="overlay"></div>
    <div class="glass">
        <div class="brand">
            <img src="https://i.imgur.com/9q7g6pK.png" alt="Anime" />
            <h1>BYPASS YEUMONY BÓNG X</h1>
        </div>
        <div class="desc">
            Bypass Tự Động Chuyên Tính Chính Xác Cao.<br>
            <span style="background:linear-gradient(90deg,#ff8a00,#e52e71,#43cea2,#185a9d,#f158ff,#00f2fe);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1.09em;">Siêu đơn giản, hiệu quả - bảo mật tuyệt đối!</span>
        </div>
        <select id="type">
            <option value="m88">M88</option>
            <option value="fb88">FB88</option>
            <option value="188bet">188BET</option>
            <option value="w88">W88</option>
            <option value="v9bet">V9BET</option>
            <option value="bk8">BK8</option>
        </select>
        <button id="getBtn" onclick="submitForm(event)">LẤY MÃ BÓNG X</button>
        <div id="result"></div>
    </div>
    <div class="footer">
        YM5 Tool &copy; 2025 &ndash; Design by <a href="https://t.me/doanh444" target="_blank">Bóng X Telegram</a>
    </div>
<script>
function submitForm(e) {
    var type = document.getElementById('type').value;
    var resultDiv = document.getElementById('result');
    var btn = document.getElementById('getBtn');
    btn.disabled = true;
    btn.innerText = "ĐANG XỬ LÝ...";
    resultDiv.innerHTML = '<div class="spinner"></div> <span class="timer pulse" id="timer">⏳ Đang lấy mã, vui lòng chờ 75 giây...</span>';
    fetch('/bypass', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type: type, user_id: 0, message: "/ym " + type})
    })
    .then(res => res.json())
    .then(data => {
        btn.disabled = false;
        btn.innerText = "LẤY MÃ BÓNG X";
        resultDiv.innerHTML = formatResult(data.msg);
    })
    .catch(e => {
        btn.disabled = false;
        btn.innerText = "LẤY MÃ BÓNG X";
        resultDiv.innerHTML = "<span style='color:#ff6f6f;'>Lỗi: Không thể kết nối máy chủ.</span>";
    });
}
function formatResult(msg) {
    if(msg.includes('✅')) {
        return `<span style="color:#31ff8a;font-weight:bold;font-size:1.24rem;">${msg}</span>`;
    } else if(msg.includes('⚠️')) {
        return `<span style="color:#ffd166;">${msg}</span>`;
    } else if(msg.includes('❌')) {
        return `<span style="color:#ff6f6f;">${msg}</span>`;
    } else {
        return msg;
    }
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", lambda update, ctx: send_main_menu(update.effective_chat.id, ctx)))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("ym", ym_command))
    application.add_handler(CommandHandler(["ban", "unban", "addadmin", "deladmin", "adminguide"], ym_command))
    application.run_polling()