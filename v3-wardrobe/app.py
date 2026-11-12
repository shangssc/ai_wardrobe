# -*- coding: utf-8 -*-
"""
AI 智能衣橱（Python 网页版）· 第二档工程化版本
功能：注册登录 -> 身体数据 -> 上传衣服(分类/材质/版型/颜色) -> 衣橱 -> 豆包AI搭配
升级点：MySQL 可切换、上传图片自动压缩、数据库层抽象、豆包 API 容错重试
运行：python app.py  然后浏览器打开 http://127.0.0.1:5000
"""
import os
import io
import json
import hashlib
import secrets
import time
from datetime import datetime

import requests
from PIL import Image
from flask import Flask, request, session, redirect, url_for, render_template, flash

from db import DB, init_db, USE_MYSQL

# ================== 基础配置 ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 图片压缩上限：最长边 800px、质量 85 —— 兼顾清晰度和加载速度
IMG_MAX_SIDE = 800
IMG_QUALITY = 85

# 豆包（火山方舟）配置
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_MODEL = os.environ.get("ARK_MODEL", "doubao-1-5-pro-32k-250115")
ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
ARK_TIMEOUT = 30      # 单次请求超时（秒）
ARK_RETRIES = 2       # 失败重试次数

CATEGORIES = ["上装", "下装", "连衣裙", "外套", "鞋子", "配饰"]
MATERIALS = ["棉", "麻", "丝", "羊毛", "牛仔", "皮革", "聚酯纤维", "针织"]
FITS = ["紧身", "修身", "合身", "宽松", "oversize"]
COLORS = ["白", "黑", "灰", "米色", "蓝", "粉", "红", "绿", "棕", "其他"]
WEATHERS = ["晴", "多云", "阴", "小雨", "大雨", "雪", "大风"]
SCENES = ["通勤", "约会", "休闲", "运动", "设计感", "见家长"]

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)


# ================== 工具函数 ==================
def hash_password(pw: str) -> str:
    return hashlib.sha256(("wardrobe-salt:" + pw).encode()).hexdigest()


def compress_image(file_storage, save_path):
    """上传图片自动压缩：转 RGB、限制最长边、控制文件体积。
    返回 (原始字节大小, 压缩后字节大小)——用于性能统计。"""
    raw = file_storage.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    if max(w, h) > IMG_MAX_SIDE:
        scale = IMG_MAX_SIDE / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=IMG_QUALITY, optimize=True)
    size_before, size_after = len(raw), buf.tell()
    with open(save_path, "wb") as f:
        f.write(buf.getvalue())
    return size_before, size_after


# ================== 豆包 AI ==================
def call_doubao(prompt: str) -> str:
    """调用豆包大模型，带超时和重试容错"""
    last_err = None
    for attempt in range(ARK_RETRIES + 1):
        try:
            resp = requests.post(
                ARK_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ARK_API_KEY}",
                },
                json={
                    "model": ARK_MODEL,
                    "messages": [
                        {"role": "system",
                         "content": "你是一位懂面料、版型和场合穿搭的时尚顾问，回答简洁实用，用中文。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                },
                timeout=ARK_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            if attempt < ARK_RETRIES:
                time.sleep(1.5 * (attempt + 1))  # 退避重试
    raise RuntimeError(f"豆包调用失败（重试{ARK_RETRIES}次）：{last_err}")


def mock_outfit(wardrobe, temp, weather, scene, extra):
    """未配置豆包 Key 时的免费模拟推荐（规则版）"""
    def pick(cat_list, n=2):
        return [f"{i['color']}{i['material']}{i['category']}（{i['fit']}）" for i in cat_list[:n]]

    tops = [i for i in wardrobe if i["category"] in ("上装", "外套")]
    bottoms = [i for i in wardrobe if i["category"] in ("下装", "连衣裙")]
    shoes = [i for i in wardrobe if i["category"] == "鞋子"]
    accs = [i for i in wardrobe if i["category"] == "配饰"]

    lines = [f"场景：{scene} ｜ 温度：{temp}°C {weather}", ""]
    for label, arr in [("上装", tops), ("下装", bottoms), ("鞋子", shoes), ("配饰", accs)]:
        p = pick(arr)
        lines.append(f"【{label}】" + ("、".join(p) if p else "衣橱中暂无此类单品，建议补充"))

    if temp >= 28:
        lines.append("\n💡 天气较热，建议选透气面料、宽松版型。")
    elif temp >= 15:
        lines.append("\n💡 温度舒适，按推荐直接穿即可。")
    else:
        lines.append("\n💡 气温偏低，建议叠穿或加保暖外套。")
    lines.append("\n（未配置豆包 API Key，此为规则模拟推荐；配置后为 AI 个性化搭配）")
    return "\n".join(lines)


# ================== 页面路由 ==================
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("outfit"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("请填写用户名和密码")
        elif len(password) < 6:
            flash("密码至少 6 位")
        else:
            db = DB()
            try:
                if db.query_one("SELECT 1 FROM users WHERE username=?", (username,)):
                    flash("用户名已被注册")
                else:
                    db.execute("INSERT INTO users(username, password_hash) VALUES(?,?)",
                               (username, hash_password(password)))
            finally:
                db.close()
            if "user_id" not in session:
                flash("注册成功，请登录")
                return redirect(url_for("login"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        db = DB()
        try:
            user = db.query_one(
                "SELECT * FROM users WHERE username=? AND password_hash=?",
                (username, hash_password(request.form.get("password", ""))),
            )
        finally:
            db.close()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("outfit"))
        flash("用户名或密码错误")
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        fields = ["height", "weight", "shoulder", "bust", "waist", "hip", "sex"]
        values = []
        for f in fields:
            v = request.form.get(f, "").strip()
            if f == "sex":
                values.append(v)
            else:
                try:
                    values.append(float(v) if v else None)
                except ValueError:
                    values.append(None)
        db = DB()
        try:
            db.execute("UPDATE users SET height=?,weight=?,shoulder=?,bust=?,waist=?,hip=?,sex=? WHERE id=?",
                       (*values, session["user_id"]))
        finally:
            db.close()
        flash("身体数据已保存 ✅")
    db = DB()
    try:
        user = db.query_one("SELECT * FROM users WHERE id=?", (session["user_id"],))
    finally:
        db.close()
    return render_template("profile.html", user=user)


@app.route("/add", methods=["GET", "POST"])
def add():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        file = request.files.get("image")
        category = request.form.get("category", "")
        if not file or not file.filename:
            flash("请先拍照或上传衣服图片")
        elif not category:
            flash("请选择分类")
        else:
            # 压缩后统一存为 jpg（不再依赖原始扩展名，也更安全）
            filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}.jpg"
            save_path = os.path.join(UPLOAD_DIR, filename)
            size_before, size_after = compress_image(file, save_path)
            print(f"[图片压缩] {size_before/1024:.0f}KB -> {size_after/1024:.0f}KB "
                  f"(节省 {100 - size_after * 100 // max(size_before, 1)}%)")
            db = DB()
            try:
                db.execute(
                    "INSERT INTO clothes(user_id,image,category,material,fit,color,created_at) VALUES(?,?,?,?,?,?,?)",
                    (session["user_id"], filename, category,
                     request.form.get("material", "未知"), request.form.get("fit", "合身"),
                     request.form.get("color", "其他"), datetime.now().isoformat()),
                )
            finally:
                db.close()
            flash("已加入衣橱 ✅")
            return redirect(url_for("wardrobe"))
    return render_template("add.html", categories=CATEGORIES, materials=MATERIALS, fits=FITS, colors=COLORS)


@app.route("/wardrobe")
def wardrobe():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cat = request.args.get("cat", "全部")
    db = DB()
    try:
        if cat == "全部":
            rows = db.query("SELECT * FROM clothes WHERE user_id=? ORDER BY created_at DESC",
                            (session["user_id"],))
        else:
            rows = db.query("SELECT * FROM clothes WHERE user_id=? AND category=? ORDER BY created_at DESC",
                            (session["user_id"], cat))
    finally:
        db.close()
    return render_template("wardrobe.html", clothes=rows, current=cat, categories=CATEGORIES)


@app.route("/delete/<int:cid>")
def delete(cid):
    if "user_id" in session:
        db = DB()
        try:
            row = db.query_one("SELECT image FROM clothes WHERE id=? AND user_id=?",
                               (cid, session["user_id"]))
            if row:
                path = os.path.join(UPLOAD_DIR, row["image"])
                if os.path.exists(path):
                    os.remove(path)
                db.execute("DELETE FROM clothes WHERE id=?", (cid,))
        finally:
            db.close()
    return redirect(url_for("wardrobe"))


@app.route("/outfit", methods=["GET", "POST"])
def outfit():
    if "user_id" not in session:
        return redirect(url_for("login"))
    result, is_ai = "", False
    if request.method == "POST":
        temp = request.form.get("temperature", "")
        weather = request.form.get("weather", "晴")
        scene = request.form.get("scene", "")
        extra = request.form.get("extra", "无")
        if not temp or not scene:
            flash("请填写温度并选择穿衣要求")
        else:
            db = DB()
            try:
                user = db.query_one("SELECT * FROM users WHERE id=?", (session["user_id"],))
                rows = db.query("SELECT * FROM clothes WHERE user_id=?", (session["user_id"],))
            finally:
                db.close()
            # 只给 AI 需要的字段，并把 datetime 转成安全结构（兼容 MySQL）
            wardrobe = [
                {"category": i["category"], "material": i["material"],
                 "fit": i["fit"], "color": i["color"]}
                for i in rows
            ]
            if ARK_API_KEY:
                profile_desc = (
                    f"身高{user['height'] or '未知'}cm，体重{user['weight'] or '未知'}kg"
                    + (f"，胸围{user['bust']}cm" if user["bust"] else "")
                    + (f"，腰围{user['waist']}cm" if user["waist"] else "")
                    + (f"，臀围{user['hip']}cm" if user["hip"] else "")
                )
                prompt = (
                    "你是专业穿搭顾问。请根据以下信息，从用户现有衣橱中选出搭配并说明理由。\n"
                    f"用户身体数据：{profile_desc}。\n"
                    f"今日条件：温度{temp}°C，{weather}；穿衣要求：{scene}；补充：{extra}。\n"
                    f"衣橱单品（JSON）：{json.dumps(wardrobe, ensure_ascii=False)}\n"
                    "要求：1.只推荐衣橱中存在的单品；2.给出1套主推+1套备选；"
                    "3.每套说明上装/下装/鞋子/配饰及整体风格理由；4.不超过300字；"
                    "5.如衣橱单品不足以满足要求，指出需要补充什么。"
                )
                t0 = time.time()
                try:
                    result = call_doubao(prompt)
                    is_ai = True
                    print(f"[豆包] 耗时 {time.time() - t0:.1f}s")
                except Exception as e:
                    result = f"{e}\n\n已自动降级为规则推荐：\n\n" + mock_outfit(wardrobe, float(temp), weather, scene, extra)
            else:
                result = mock_outfit(wardrobe, float(temp), weather, scene, extra)
    return render_template("outfit.html", result=result, is_ai=is_ai, weathers=WEATHERS, scenes=SCENES)


# ================== 启动 ==================
init_db()


def get_lan_ip():
    """获取本机在局域网中的 IP（手机用这个地址访问）"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    lan_ip = get_lan_ip()
    print("=" * 60)
    print("  AI 智能衣橱已启动！")
    print()
    print("  电脑访问： http://127.0.0.1:5000")
    print(f"  手机访问： http://{lan_ip}:5000   ← 手机和电脑要连同一个 WiFi")
    print(f"  数据库：  {'MySQL (' + os.environ.get('MYSQL_HOST', '') + ')' if USE_MYSQL else 'SQLite（本地文件）'}")
    print(f"  豆包AI：  {'已配置' if ARK_API_KEY else '未配置（当前使用免费模拟推荐）'}")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
