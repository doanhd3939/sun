from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests, re, asyncio, threading, time
import os
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
    {"label": "Bypass VN88", "type": "vn88"},
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

@app.route('/bypass', methods=['POST'])
def k():
    json = request.get_json()
    if not json:
        return jsonify({'error': 'get the fuck out bitch'}), 400
    type = json.get('type')
    if not type:
        return jsonify({'error': 'get the fuck out bitch'}), 400
    
    bypass_urls = {
        'm88': ('taodeptrai', 'https://bet88ec.com/cach-danh-bai-sam-loc', 'https://bet88ec.com/'),
        'fb88': ('taodeptrai', 'https://fb88mg.com/ty-le-cuoc-hong-kong-la-gi', 'https://fb88mg.com/'),
        '188bet': ('taodeptrailamnhe', 'https://88betag.com/cach-choi-game-bai-pok-deng', 'https://88betag.com/'),
        'w88': ('taodeptrai', 'https://188.166.185.213/tim-hieu-khai-niem-3-bet-trong-poker-la-gi', 'https://188.166.185.213/'),
        'v9bet': [
            "https://traffic-user.net/GET_MA.php?codexn=taodeptrai&url=https://v9betdi.com/cuoc-thang-ap-dao-la-gi&loai_traffic=https://v9betdi.com/&clk=1000",
            "https://traffic-user.net/GET_MA.php?codexn=taodeptrai&url=https://v9betho.com/ca-cuoc-bong-ro-ao&loai_traffic=https://v9betho.com/&clk=1000",
            "https://traffic-user.net/GET_MA.php?codexn=taodeptrai&url=https://v9betxa.com/cach-choi-craps&loai_traffic=https://v9betxa.com/&clk=1000",
        ],
        'bk8': ('taodeptrai', 'https://bk8xo.com/lo-ba-cang-la-gi', 'https://bk8xo.com/'),
        'vn88': ('deobiet', 'https://vn88ie.com/cach-choi-mega-6-45', 'https://vn88ie.com/'),
    }

    if type in bypass_urls:
        urls = bypass_urls[type]
        if isinstance(urls, list):
            results = []
            for url in urls:
                response = requests.post(url, timeout=15)
                html = response.text
                match = re.search(r'<span id="layma_me_vuatraffic"[^>]*>\s*(\d+)\s*</span>', html)
                if match:
                    results.append(match.group(1))
            if results:
                return jsonify({'codes': results}), 200
            else:
                return jsonify({'error': 'cannot get code'}), 400
        else:
            code_key, url, ref = urls
            response = requests.post(
                f'https://traffic-user.net/GET_MA.php?codexn={code_key}&url={url}&loai_traffic={ref}&clk=1000',
                timeout=15
            )
            html = response.text
            match = re.search(r'<span id="layma_me_vuatraffic"[^>]*>\s*(\d+)\s*</span>', html)
            if match:
                code = match.group(1)
                return jsonify({'code': code}), 200
            else:
                return jsonify({'error': 'cannot get code'}), 400
    else:
        return jsonify({'error': 'Invalid type'}), 400

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
    if data == HELP_BUTTON["callback"]:
        help_text = (
            "<b>📖 HƯỚNG DẪN SỬ DỤNG BOT BYPASS & HỖ TRỢ</b>\n"
            "• Bypass traffic (lấy mã) cho các loại: <b>M88, FB88, 188BET, W88, V9BET, BK8, VN88</b>.\n"
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
            [InlineKeyboardButton("💬 Liên hệ Admin & Nhóm", callback_data="help")]
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
            "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>70 giây</b>...</i>\n"
            "<b>⏱️wed bypass bóng x http://103.157.205.154:5000/</b>",
            parse_mode="HTML"
        )
        async def delay_and_reply():
            start_time = time.time()
            try:
                resp = requests.post("http://localhost:5000/bypass", json={"type": type, "user_id": user_id, "message": f"/ym {type}"})
                data = resp.json()
                if "code" in data or "codes" in data:
                    if "codes" in data:
                        result = f'✅ <b>{type.upper()}</b> | <b style="color:#32e1b7;">Mã</b>: <code>{", ".join(data["codes"])}</code>'
                    else:
                        result = f'✅ <b>{type.upper()}</b> | <b style="color:#32e1b7;">Mã</b>: <code>{data["code"]}</code>'
                else:
                    result = f'❌ <b>Lỗi:</b> {data.get("error", "Không lấy được mã")}'
            except Exception as e:
                result = f"❌ <b>Lỗi hệ thống:</b> <code>{e}</code>"
            elapsed = time.time() - start_time
            if elapsed < 70:
                await asyncio.sleep(70 - elapsed)
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
            "📌 <b>Hướng dẫn sử dụng:</b>\n<b>/ym &lt;loại&gt;</b>\nVí dụ: <code>/ym m88</code>\n<b>Các loại hợp lệ:</b> <i>m88, fb88, 188bet, w88, v9bet, bk8, vn88</i>"
        )
        return
    type = context.args[0].lower()
    user = update.effective_user.first_name or "User"
    sent = await update.message.reply_html(
        "⏳ <b>Đã nhận lệnh!</b>\n"
        "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>70 giây</b>...</i>\n"
        "<b>⏱️wed bypass bóng x http://103.157.205.154:5000/</b>"
    )
    async def delay_and_reply():
        start_time = time.time()
        try:
            resp = requests.post("http://localhost:5000/bypass", json={"type": type, "user_id": user_id, "message": f"/ym {type}"})
            data = resp.json()
            if "code" in data or "codes" in data:
                if "codes" in data:
                    result = f'✅ <b>{type.upper()}</b> | <b style="color:#32e1b7;">Mã</b>: <code>{", ".join(data["codes"])}</code>'
                else:
                    result = f'✅ <b>{type.upper()}</b> | <b style="color:#32e1b7;">Mã</b>: <code>{data["code"]}</code>'
            else:
                result = f'❌ <b>Lỗi:</b> {data.get("error", "Không lấy được mã")}'
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

# SỬ DỤNG GIAO DIỆN code.html ĐƯỢC TÍCH HỢP DƯỚI ĐÂY
BYPASS_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BYPASS TRAFFIC | YM5 Tool</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {background: linear-gradient(180deg, #483D8B, #6A5ACD, #7B68EE); min-height: 100vh; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 1rem; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: white;}
    .container {max-width: 400px; margin: 2rem auto; background: rgba(98, 84, 158, 0.5); border-radius: 1rem; box-shadow:0 4px 15px rgba(72, 61, 139, 0.6), inset 0 0 15px rgba(255 255 255 / 0.1); padding: 1.5rem 1.75rem 2.5rem 1.75rem; backdrop-filter: blur(10px); border: 1px solid rgba(255 255 255 / 0.2);}
    .icon-rocket {width: 60px; margin: 0 auto 0.75rem auto; display: block; filter: drop-shadow(0 0 6px #69B9FFAA); fill: #5CC1E0; animation: floatRocket 3s ease-in-out infinite;}
    @keyframes floatRocket {0%, 100% {transform: translateY(0);}50% {transform: translateY(-8px);}}
    .rainbow-text {font-weight: 800; font-size: 1.35rem; text-align: center; letter-spacing: 0.12em; user-select: none; background: linear-gradient(90deg,#ff003c,#ff6000,#82e58f,#00cc91,#0086ff,#6d47ff); -webkit-background-clip: text; color: transparent; text-shadow: 0 0 5px rgba(255 255 255 / 0.2); margin-bottom: 1rem;}
    .info-box {background: rgba(255 255 255 / 0.1); border-radius: 0.75rem; padding: 1rem 1rem 1.25rem; margin-bottom: 1rem; box-shadow: inset 0 0 15px rgba(255 255 255 / 0.12); text-align: center; line-height: 1.4; font-weight: 600;}
    .info-box p:first-child {font-size: 1.125rem; color: white;}
    .info-box p:nth-child(2) {font-size: 1rem; margin-top: 0.5rem; font-weight: 700; background: linear-gradient(90deg,#f97316,#ef4444,#22c55e,#14b8a6,#2563eb,#e879f9); -webkit-background-clip: text; color: transparent; user-select: none;}
    select {width: 100%; padding: 0.75rem 1rem; font-weight: 700; font-size: 1.1rem; border-radius: 0.75rem; background: rgba(255 255 255 / 0.1); border: 1px solid rgba(255 255 255 / 0.2); color: white; outline-offset: 3px; transition: border-color 0.3s ease; cursor: pointer; appearance: none;}
    select:hover, select:focus {border-color: #f97316; background: rgba(255 255 255 / 0.18);}
    .btn-primary {display: block; width: 100%; margin-top: 1rem; background-color: #3b3f71; font-weight: 700; font-size: 1.25rem; color: white; border-radius: 0.75rem; padding: 0.85rem 0; border: 2px solid rgba(255 255 255 / 0.4); text-align: center; cursor: pointer; transition: all 0.3s ease; box-shadow:0 0 10px #00cc91aa, inset 0 0 8px #14b8a6aa; user-select: none;}
    .btn-primary:hover {background-color: #2563eb; border-color: #00e3b199; box-shadow:0 0 15px #22c55eee, inset 0 0 15px #14b8a6ee;}
    .loader-ring {position: relative; width: 24px; height: 24px; margin-right: 0.7rem; flex-shrink: 0;}
    .loader-ring svg circle {fill: transparent; stroke: #e0e0e0; stroke-width: 3; stroke-linecap: round;}
    .loader-ring svg circle.progress {stroke: #22c55e; stroke-dasharray: 75; stroke-dashoffset: 75; animation: progressAnim 2s linear infinite; transform-origin: center;}
    @keyframes progressAnim {0% {stroke-dashoffset: 75; transform: rotate(0deg);}50% {stroke-dashoffset: 18.75; transform: rotate(180deg);}100% {stroke-dashoffset: 75; transform: rotate(360deg);}}
    .wait-message {margin-top: 1.5rem; background: rgba(255 255 255 / 0.1); border-radius: 0.75rem; padding: 1rem 1rem; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 1.125rem; color: #fbbf24; font-family: monospace; letter-spacing: 0.05em; user-select: none;}
    #result-message {margin-top: 1.5rem; background: rgba(255 255 255 / 0.1); border-radius: 0.75rem; padding: 1rem 1rem; text-align: center; font-weight: 700; font-size: 1.16rem;}
    #result-message code {background: #1113; color: #31ff8a; padding: 0.3rem 0.6rem; border-radius: 6px;}
    #result-message.error {color: #ff6969;}
    #result-message.success {color: #31ff8a;}
    footer {margin-top: 2rem; text-align: center; color: #d1d5db; font-weight: 600; font-size: 0.9rem; user-select: none;}
    footer b {color: #64748b; font-weight: 700;}
  </style>
</head>
<body>
  <main class="container" role="main" aria-label="BYPASS TRAFFIC YM5 Tool Interface">
    <svg class="icon-rocket" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M13 2a1 1 0 0 0-1.32.948L8.836 9.11 3.024 10.66a.75.75 0 0 0-.112 1.444L6.914 13.3l1.2 3.408a1 1 0 0 0 1.32.62l6.63-2.452a1 1 0 0 0 .62-1.32L13 2z"/>
      <path d="M12 21a4 4 0 1 1 4-4 4 4 0 0 1-4 4z" />
    </svg>
    <div class="rainbow-text" aria-label="Bypass Yeumony Bóng X title">BYPASS YEUMONY BÓNG X</div>
    <section class="info-box" aria-live="polite">
      <p>Bypass Tự Động Chuyên Tính Chính Xác Cao.</p>
      <p>Siêu đơn giản, không cần tài khoản!</p>
    </section>
    <form id="bypass-form" aria-label="Chọn nhà cái và lấy mã bóng X" autocomplete="off">
      <label for="select-provider" class="sr-only">Chọn nhà cái</label>
      <select id="select-provider" required aria-required="true" aria-describedby="select-desc" title="Chọn nhà cái để lấy mã bóng X">
        <option value="m88">M88</option>
        <option value="fb88">FB88</option>
        <option value="188bet">188BET</option>
        <option value="w88">W88</option>
        <option value="v9bet">V9BET</option>
        <option value="bk8">BK8</option>
        <option value="vn88">VN88</option>
      </select>
      <button type="submit" class="btn-primary" aria-label="Lấy mã bóng X">LẤY MÃ BÓNG X</button>
    </form>
    <div id="loading" class="wait-message" aria-live="assertive" aria-atomic="true" hidden>
      <div class="loader-ring" aria-hidden="true">
        <svg height="24" width="24" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="12" opacity="0.2"></circle>
          <circle class="progress" cx="12" cy="12" r="12"></circle>
        </svg>
      </div>
      <div id="loading-text">Vui lòng chờ 75 giây...</div>
    </div>
    <div id="result-message"></div>
  </main>
  <footer>
    YM5 Tool © 2025 – Design by <b>Bóng X Telegram</b>
  </footer>
  <script>
    (function () {
      const form = document.getElementById('bypass-form');
      const loading = document.getElementById('loading');
      const loadingText = document.getElementById('loading-text');
      const resultDiv = document.getElementById('result-message');
      let countdownInterval = null;
      form.addEventListener('submit', event => {
        event.preventDefault();
        resultDiv.textContent = '';
        if (countdownInterval) clearInterval(countdownInterval);
        const type = document.getElementById('select-provider').value;
        loading.hidden = false;
        let remaining = 75;
        loadingText.textContent = `Vui lòng chờ ${remaining} giây...`;
        countdownInterval = setInterval(() => {
          remaining--;
          loadingText.textContent = `Vui lòng chờ ${remaining} giây...`;
          if (remaining <= 0) {
            clearInterval(countdownInterval);
            loading.hidden = true;
          }
        }, 1000);
        fetch('/bypass', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type: type, user_id: 0, message: "/ym " + type})
        })
        .then(res => res.json())
        .then(data => {
            setTimeout(() => {
                loading.hidden = true;
                if (data.code || data.codes) {
                    if (data.codes) {
                        resultDiv.className = "success";
                        resultDiv.innerHTML = `✅ <b>Mã: </b><code>${data.codes.join(", ")}</code>`;
                    } else {
                        resultDiv.className = "success";
                        resultDiv.innerHTML = `✅ <b>Mã: </b><code>${data.code}</code>`;
                    }
                } else {
                    resultDiv.className = "error";
                    resultDiv.innerHTML = `<span>❌ Lỗi: ${data.error || 'Không lấy được mã'}</span>`;
                }
            }, 75000); // 75 giây
        })
        .catch(e => {
            loading.hidden = true;
            resultDiv.className = "error";
            resultDiv.innerHTML = "<span>Lỗi: Không thể kết nối máy chủ.</span>";
        });
      });
    })();
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