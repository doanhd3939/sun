from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests, re, asyncio, threading, time
import os

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8029254946:AAE8Upy5LoYIYsmcm8Y117Esm_-_MF0-ChA')
app = Flask(__name__)

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
USER_LOCKS = threading.Lock()
USER_BUTTON_LOCK = {}

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
            line.append(InlineKeyboardButton(task["label"], callback_data=f"bypass:{task['type']}:{chat_id}"))
        keyboard.append(line)
    keyboard.append([InlineKeyboardButton(HELP_BUTTON["label"], callback_data=f"{HELP_BUTTON['callback']}:{chat_id}")])
    if user is not None and is_admin(user):
        keyboard.append([InlineKeyboardButton("👑 Hướng dẫn Admin", callback_data=f"adminguide:{chat_id}")])
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
    chat_id = query.message.chat_id

    if ":" in data:
        parts = data.split(":")
        action = parts[0]
        action_type = parts[1] if len(parts) > 1 else None
        action_chat_id = int(parts[-1]) if parts[-1].isdigit() else None
    else:
        action = data
        action_type = None
        action_chat_id = None

    if action_chat_id is not None and user_id != action_chat_id:
        await query.edit_message_text(
            "⛔ <b>Nút này chỉ dành cho bạn!</b>",
            parse_mode="HTML"
        )
        return

    with USER_LOCKS:
        if USER_BUTTON_LOCK.get(user_id, False):
            await query.edit_message_text(
                "⛔ <b>Bạn vừa thao tác, vui lòng chờ kết quả!</b>",
                parse_mode="HTML"
            )
            return
        USER_BUTTON_LOCK[user_id] = True

    if action == "mainmenu":
        await send_main_menu(chat_id, context)
        USER_BUTTON_LOCK[user_id] = False
        return
    if action == "adminguide":
        await query.edit_message_text(
            ADMIN_GUIDE, parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Quay lại Menu", callback_data=f"mainmenu:{chat_id}")]
            ])
        )
        USER_BUTTON_LOCK[user_id] = False
        return
    if action == HELP_BUTTON["callback"]:
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
            [InlineKeyboardButton("🏠 Quay lại Menu", callback_data=f"mainmenu:{chat_id}")],
            [InlineKeyboardButton("💬 Liên hệ Admin & Nhóm", callback_data=f"help:{chat_id}")]
        ])
        await query.edit_message_text(
            help_text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=help_keyboard
        )
        USER_BUTTON_LOCK[user_id] = False
        return

    if action == "bypass":
        type = action_type
        check = pre_check(user_id)
        if check["status"] != "ok":
            await query.edit_message_text(
                f"❌ <b>Lỗi:</b> {check.get('msg', 'Bạn bị giới hạn.')}",
                parse_mode="HTML"
            )
            USER_BUTTON_LOCK[user_id] = False
            return

        # Gửi trạng thái lần đầu
        msg = (
            "⏳ <b>Đã nhận nhiệm vụ!</b>\n"
            "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>75 giây</b>...</i>\n"
            "<b>⏱️ Đang lấy mã, xin đừng gửi lệnh mới...</b>\n"
            "<b>Còn lại: <code>75</code> giây...</b>"
        )
        sent = await query.edit_message_text(msg, parse_mode="HTML")

        async def delay_and_reply():
            start_time = time.time()
            result = None
            # Lấy mã song song
            def get_code():
                nonlocal result
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
            t = threading.Thread(target=get_code)
            t.start()

            # Đếm ngược mượt mà (chỉ update mỗi 5 giây)
            for remain in range(70, 0, -5):
                await asyncio.sleep(5)
                try:
                    await sent.edit_text(
                        "⏳ <b>Đã nhận nhiệm vụ!</b>\n"
                        "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>75 giây</b>...</i>\n"
                        "<b>⏱️ Đang lấy mã, xin đừng gửi lệnh mới...</b>\n"
                        f"<b>Còn lại: <code>{remain}</code> giây...</b>",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            # Đợi đủ 75 giây hoặc mã đã xong
            t.join()
            await asyncio.sleep(max(0, 75 - (time.time() - start_time)))
            await sent.edit_text(
                "<b>🎉 KẾT QUẢ BYPASS</b>\n<b>─────────────────────────────</b>\n"
                + (result if result else "<b>Không lấy được kết quả</b>") +
                "\n<b>─────────────────────────────</b>",
                parse_mode="HTML"
            )
            await send_main_menu(chat_id, context)
            USER_BUTTON_LOCK[user_id] = False
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
    sent = await update.message.reply_html(
        "⏳ <b>Đã nhận lệnh!</b>\n"
        "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>75 giây</b>...</i>\n"
        "<b>⏱️ Đang lấy mã, xin đừng gửi lệnh mới...</b>\n"
        "<b>Còn lại: <code>75</code> giây...</b>"
    )
    async def delay_and_reply():
        start_time = time.time()
        result = None
        def get_code():
            nonlocal result
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
        t = threading.Thread(target=get_code)
        t.start()
        for remain in range(70, 0, -5):
            await asyncio.sleep(5)
            try:
                await sent.edit_text(
                    "⏳ <b>Đã nhận lệnh!</b>\n"
                    "🤖 <i>Bot đang xử lý yêu cầu của bạn, vui lòng chờ <b>75 giây</b>...</i>\n"
                    "<b>⏱️ Đang lấy mã, xin đừng gửi lệnh mới...</b>\n"
                    f"<b>Còn lại: <code>{remain}</code> giây...</b>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        t.join()
        await asyncio.sleep(max(0, 75 - (time.time() - start_time)))
        await sent.edit_text(
            "<b>🎉 KẾT QUẢ BYPASS</b>\n<b>─────────────────────────────</b>\n" + (result if result else "<b>Không lấy được kết quả</b>") + "\n<b>─────────────────────────────</b>",
            parse_mode="HTML"
        )
        await send_main_menu(update.effective_chat.id, context)
    asyncio.create_task(delay_and_reply())

# BYPASS_TEMPLATE giữ nguyên như bản trước

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", lambda update, ctx: send_main_menu(update.effective_chat.id, ctx)))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("ym", ym_command))
    application.add_handler(CommandHandler(["ban", "unban", "addadmin", "deladmin", "adminguide"], ym_command))
    application.run_polling()