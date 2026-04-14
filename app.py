import hashlib, hmac, secrets
from flask import Flask, request, redirect, render_template, jsonify, session
import database as db
import os

flask_app = Flask(__name__)

SECRET_KEY     = os.getenv("SECRET_KEY", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

# 启动时强制校验关键配置（与 README 声明一致）
if not SECRET_KEY:
    raise RuntimeError("❌ .env 中未配置 SECRET_KEY，服务拒绝启动。"
                       "生成命令: python -c \"import secrets; print(secrets.token_hex(32))\"")
if not ADMIN_PASSWORD:
    raise RuntimeError("❌ .env 中未配置 ADMIN_PASSWORD，服务拒绝启动。")

flask_app.secret_key = SECRET_KEY


def _auth_token():
    """使用 HMAC-SHA256 签名，防止 Cookie 被伪造"""
    return hmac.new(SECRET_KEY.encode(), f"teletask:{ADMIN_PASSWORD}".encode(),
                    hashlib.sha256).hexdigest()


def _ct_eq(a: str, b: str) -> bool:
    """常量时间字符串比较，防止时序攻击"""
    return secrets.compare_digest((a or "").encode(), (b or "").encode())


def check_auth():
    return _ct_eq(request.cookies.get("auth", ""), _auth_token())


@flask_app.before_request
def require_login():
    open_paths = {"/login", "/do_login", "/do_files_login", "/do_stats_login",
                  "/stats", "/stats/logout", "/files", "/files/logout", "/import"}
    if request.path in open_paths:
        return
    if not check_auth():
        return redirect("/login")


@flask_app.route("/login")
def login():
    return render_template("login.html", err=request.args.get("err"))


@flask_app.route("/do_login", methods=["POST"])
def do_login():
    if _ct_eq(request.form.get("pwd", ""), ADMIN_PASSWORD):
        resp = redirect("/")
        resp.set_cookie("auth", _auth_token(), max_age=86400 * 7, httponly=True)
        return resp
    return redirect("/login?err=1")


@flask_app.route("/")
def index():
    return render_template(
        "index.html",
        keywords       = db.get_keywords(),
        schedules      = db.get_schedules(),
        stats          = db.get_stats(),
        ban_rules      = db.get_auto_ban_rules(),
        chats          = db.get_chats(),
        group_mute_rules = db.get_group_mute_rules(),
        group_muted_users = db.get_group_muted_users(),
    )


# ======== 关键词 CRUD ========
@flask_app.route("/kw/add", methods=["POST"])
def kw_add():
    pattern = request.form.get("pattern", "").strip()
    match   = request.form.get("match", "contains")
    mode    = request.form.get("mode", "random")
    replies = _parse_replies(request.form)
    das     = _parse_seconds(request.form, "kw_delete")
    eas     = _parse_seconds(request.form, "kw_expire")
    start_at = _parse_datetime_local(request.form.get("kw_start_at", ""))
    chat_ids = _parse_chat_ids_form(request.form)
    # Bug4修复：正则模式下校验表达式合法性
    if pattern and match == "regex":
        import re
        try:
            re.compile(pattern)
        except re.error as e:
            from urllib.parse import quote
            return redirect(f"/?kw_err={quote(f'正则表达式非法：{e}')}")
    if pattern and replies:
        db.add_keyword(pattern, match, mode, replies, das, eas,
                       start_at=start_at, chat_ids=chat_ids)
    return redirect("/")


@flask_app.route("/kw/edit/<int:kid>", methods=["POST"])
def kw_edit(kid):
    pattern = request.form.get("pattern", "").strip()
    match   = request.form.get("match", "contains")
    mode    = request.form.get("mode", "random")
    replies = _parse_replies(request.form)
    das     = _parse_seconds(request.form, "kw_delete")
    # Bug1修复：优先读 kw_expire_clear（hidden input，-1 表示清除）；
    # 普通到期字段被 disabled 后不提交，hidden 字段作为信号源。
    clear_flag = request.form.get("kw_expire_clear", "0").strip()
    if clear_flag == "-1":
        eas = -1
    else:
        eas = _parse_seconds(request.form, "kw_expire")
    start_at = _parse_datetime_local(request.form.get("kw_start_at", ""))
    chat_ids = _parse_chat_ids_form(request.form)
    # Bug4修复：正则模式下校验表达式合法性
    if pattern and match == "regex":
        import re
        try:
            re.compile(pattern)
        except re.error as e:
            from urllib.parse import quote
            return redirect(f"/?kw_err={quote(f'正则表达式非法：{e}')}")
    if pattern:
        db.update_keyword(kid, pattern, match, mode, replies, das, eas,
                          start_at=start_at, chat_ids=chat_ids)
    return redirect("/")


@flask_app.route("/kw/get/<int:kid>")
def kw_get(kid):
    row = db.get_keyword(kid)
    return jsonify(row if row else {})


@flask_app.route("/kw/delete/<int:kid>")
def kw_delete(kid):
    db.delete_keyword(kid)
    return redirect("/")


@flask_app.route("/kw/toggle/<int:kid>")
def kw_toggle(kid):
    db.toggle_keyword(kid)
    return redirect("/")


def _parse_replies(f):
    replies = []
    i = 0
    while True:
        rtype = f.get(f"reply_type_{i}")
        if rtype is None:
            break
        replies.append({
            "reply_type"   : rtype,
            "reply_text"   : f.get(f"reply_text_{i}",    "").strip() or None,
            "reply_file_id": f.get(f"reply_file_id_{i}", "").strip() or None,
            "reply_caption": f.get(f"reply_caption_{i}", "").strip() or None,
        })
        i += 1
    return replies


def _parse_seconds(f, prefix):
    """
    将「数量+单位」表单字段转换为秒数。
    特殊值：val == -1 → 返回 -1（表示"清除到期时间"信号）
    val == 0 或无效 → 返回 None（不设置）
    """
    try:
        val  = int(f.get(f"{prefix}_value", 0) or 0)
        unit = int(f.get(f"{prefix}_unit",  1) or 1)
        if val == -1:
            return -1          # ✅ 传递"清除"信号给 database.update_keyword
        return val * unit if val > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_datetime_local(s):
    """
    将 <input type="datetime-local"> 的值（YYYY-MM-DDTHH:MM）
    转换为数据库使用的 "YYYY-MM-DD HH:MM:SS" 字符串。空值 → None。
    """
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("T", " ")
    if len(s) == 16:      # 没有秒数
        s += ":00"
    return s


def _parse_chat_ids_form(f):
    """从表单中提取 chat_ids（多选复选框）。返回 int 列表，空列表表示"所有群组"。"""
    ids = []
    for v in f.getlist("chat_ids"):
        try:
            ids.append(int(v))
        except (ValueError, TypeError):
            pass
    return ids


# ======== 定时任务 CRUD ========
@flask_app.route("/sc/add", methods=["POST"])
def sc_add():
    try:
        params = _sc_form(request.form)
    except ValueError as e:
        from urllib.parse import quote
        return redirect(f"/?sc_err={quote(str(e))}")
    db.add_schedule(**params)
    _reload()
    return redirect("/")


@flask_app.route("/sc/edit/<int:sid>", methods=["POST"])
def sc_edit(sid):
    try:
        params = _sc_form(request.form)
    except ValueError as e:
        from urllib.parse import quote
        return redirect(f"/?sc_err={quote(str(e))}")
    db.update_schedule(sid, **params)
    _reload()
    return redirect("/")


@flask_app.route("/sc/get/<int:sid>")
def sc_get(sid):
    row = db.get_schedule(sid)
    return jsonify(row if row else {})


@flask_app.route("/sc/delete/<int:sid>")
def sc_delete(sid):
    db.delete_schedule(sid)
    _reload()
    return redirect("/")


@flask_app.route("/sc/toggle/<int:sid>")
def sc_toggle(sid):
    db.toggle_schedule(sid)
    _reload()
    return redirect("/")


def _sc_form(f):
    once = f.get("once", "0") == "1"
    if once:
        dt   = f.get("run_at", "").strip()
        # Bug3修复：一次性任务必须提供执行时间
        if not dt:
            raise ValueError("一次性任务必须填写执行时间")
        # BugA修复：校验 run_at 是否为合法日期时间，防止非法值写入数据库
        dt_full = (dt + ":00") if len(dt) == 16 else dt
        try:
            from datetime import datetime as _dt
            _dt.fromisoformat(dt_full)
        except ValueError:
            raise ValueError(f"执行时间格式非法：{dt}")
        cron = dt_full
    else:
        cron = f.get("cron", "").strip()
        # Bug8修复：校验 cron 表达式合法性
        if cron:
            try:
                from apscheduler.triggers.cron import CronTrigger
                parts = cron.split()
                if len(parts) != 5:
                    raise ValueError("Cron 需要5个字段")
                CronTrigger(minute=parts[0], hour=parts[1],
                            day=parts[2], month=parts[3], day_of_week=parts[4])
            except Exception as e:
                raise ValueError(f"Cron 表达式非法：{e}")
    das = _parse_seconds(f, "sc_delete")
    return dict(
        name                 = f.get("name",        "").strip(),
        chat_id              = f.get("chat_id",     "").strip(),
        cron                 = cron,
        msg_type             = f.get("msg_type",    "text"),
        msg_text             = f.get("msg_text",    "").strip() or None,
        msg_file_id          = f.get("msg_file_id", "").strip() or None,
        msg_caption          = f.get("msg_caption", "").strip() or None,
        once                 = once,
        delete_after_seconds = das,
        start_at             = None,   # 定时任务不再使用"开始生效时间"
    )


def _reload():
    try:
        import bot
        bot.reload_schedules()
    except Exception:
        pass


# ======== 统计页面 ========
@flask_app.route("/stats")
def stats_page():
    if not session.get("stats_auth"):
        return render_template("stats_login.html", err=False)
    return render_template(
        "stats.html",
        kw_logs = db.get_keyword_logs(limit=200),
        sc_logs = db.get_schedule_logs(limit=100),
        banned  = db.get_banned_users(),
        stats   = db.get_stats(),
    )


@flask_app.route("/do_stats_login", methods=["POST"])
def do_stats_login():
    if _ct_eq(request.form.get("pwd", ""), ADMIN_PASSWORD):
        session["stats_auth"] = True
        return redirect("/stats")
    return render_template("stats_login.html", err=True)


@flask_app.route("/stats/logout")
def stats_logout():
    session.pop("stats_auth", None)
    return redirect("/stats")


@flask_app.route("/stats/ban/<int:uid>", methods=["POST"])
def stats_ban(uid):
    if not session.get("stats_auth"):
        return redirect("/stats")
    db.ban_user(uid,
                request.form.get("username",   ""),
                request.form.get("first_name", ""),
                request.form.get("reason",     ""))
    return redirect("/stats")


@flask_app.route("/stats/unban/<int:uid>")
def stats_unban(uid):
    if not session.get("stats_auth"):
        return redirect("/stats")
    db.unban_user(uid)
    return redirect("/stats")


# ======== 自动Ban规则 ========
@flask_app.route("/ban_rules/add", methods=["POST"])
def ban_rules_add():
    try:
        tc      = int(request.form.get("trigger_count", 10) or 10)
        ws_val  = int(request.form.get("window_value",  5)  or 5)
        ws_unit = int(request.form.get("window_unit",   60) or 60)
        db.add_auto_ban_rule(tc, ws_val * ws_unit)
    except (ValueError, TypeError):
        pass
    return redirect("/")


@flask_app.route("/ban_rules/delete/<int:rid>")
def ban_rules_delete(rid):
    db.delete_auto_ban_rule(rid)
    return redirect("/")


@flask_app.route("/ban_rules/toggle/<int:rid>")
def ban_rules_toggle(rid):
    db.toggle_auto_ban_rule(rid)
    return redirect("/")


# ======== 群组内关键词屏蔽规则 ========
@flask_app.route("/group_mute_rules/add", methods=["POST"])
def group_mute_rules_add():
    try:
        chat_id       = int(request.form.get("chat_id", 0) or 0)
        trigger_count = int(request.form.get("trigger_count", 5) or 5)
        unmute_time   = request.form.get("unmute_time", "23:59").strip()
        h, m = (unmute_time.split(":") + ["0"])[:2]
        unmute_hour   = max(0, min(23, int(h)))
        unmute_minute = max(0, min(59, int(m)))
        if chat_id:
            db.add_group_mute_rule(chat_id, trigger_count, unmute_hour, unmute_minute)
    except (ValueError, TypeError):
        pass
    return redirect("/")


@flask_app.route("/group_mute_rules/delete/<int:rid>")
def group_mute_rules_delete(rid):
    db.delete_group_mute_rule(rid)
    return redirect("/")


@flask_app.route("/group_mute_rules/toggle/<int:rid>")
def group_mute_rules_toggle(rid):
    db.toggle_group_mute_rule(rid)
    return redirect("/")


@flask_app.route("/group_mute_rules/unmute", methods=["POST"])
def group_mute_rules_unmute():
    """手动提前解除某用户在某群的屏蔽"""
    try:
        user_id = int(request.form.get("user_id", 0) or 0)
        chat_id = int(request.form.get("chat_id", 0) or 0)
        if user_id and chat_id:
            db.unmute_user_in_group(user_id, chat_id)
            import bot_helpers as bh
            bh.reset_group_trigger(user_id, chat_id)
    except (ValueError, TypeError):
        pass
    return redirect("/")


# ======== 文件库 ========
@flask_app.route("/files")
def files_page():
    if not session.get("files_auth"):
        return render_template("files_login.html", err=False)
    return render_template("files.html", records=db.get_file_records())


@flask_app.route("/do_files_login", methods=["POST"])
def do_files_login():
    if _ct_eq(request.form.get("pwd", ""), ADMIN_PASSWORD):
        session["files_auth"] = True
        return redirect("/files")
    return render_template("files_login.html", err=True)


@flask_app.route("/files/logout")
def files_logout():
    session.pop("files_auth", None)
    return redirect("/files")


@flask_app.route("/files/rename/<int:fid>", methods=["POST"])
def files_rename(fid):
    if not session.get("files_auth"):
        return redirect("/files")
    new_name = request.form.get("file_name", "").strip()
    if new_name:
        db.update_file_name(fid, new_name)
    return redirect("/files")


@flask_app.route("/files/delete/<int:fid>")
def files_delete(fid):
    if not session.get("files_auth"):
        return redirect("/files")
    # Bug6修复：删前检查引用，有引用则拒绝
    records = db.get_file_records()
    target  = next((r for r in records if r["id"] == fid), None)
    if target:
        usages = db.get_file_ids_in_use(target["file_id"])
        if usages:
            names = "、".join(u["name"] for u in usages[:5])
            return render_template("files.html", records=records,
                                   err=f"⚠️ 文件被以下规则引用，无法删除：{names}"), 400
    db.soft_delete_file(fid)
    return redirect("/files")


@flask_app.route("/files/check_usages/<int:fid>")
def files_check_usages(fid):
    if not session.get("files_auth"):
        return jsonify({"error": "unauthorized"}), 403
    records = db.get_file_records()
    target  = next((r for r in records if r["id"] == fid), None)
    if not target:
        return jsonify({"usages": [], "file_name": ""})
    usages = db.get_file_ids_in_use(target["file_id"])
    return jsonify({"usages": usages, "file_name": target["file_name"] or ""})


@flask_app.route("/files/bulk_check_usages", methods=["POST"])
def files_bulk_check_usages():
    """批量检查多个文件是否有引用。"""
    if not session.get("files_auth"):
        return jsonify({"error": "unauthorized"}), 403
    ids = []
    for v in request.form.getlist("ids"):
        try:
            ids.append(int(v))
        except (ValueError, TypeError):
            pass
    if not ids:
        return jsonify({"items": []})
    records = db.get_file_records()
    by_id   = {r["id"]: r for r in records}
    items   = []
    for fid in ids:
        tgt = by_id.get(fid)
        if not tgt:
            continue
        usages = db.get_file_ids_in_use(tgt["file_id"])
        if usages:
            items.append({
                "id": fid,
                "file_name": tgt["file_name"] or "",
                "usages": usages,
            })
    return jsonify({"items": items})


@flask_app.route("/files/bulk_delete", methods=["POST"])
def files_bulk_delete():
    if not session.get("files_auth"):
        return redirect("/files")
    ids = []
    for v in request.form.getlist("ids"):
        try:
            ids.append(int(v))
        except (ValueError, TypeError):
            pass
    if not ids:
        return redirect("/files")
    # Bug6修复：批量删前检查引用，过滤掉被引用的文件，只删安全的
    records  = db.get_file_records()
    by_id    = {r["id"]: r for r in records}
    safe_ids = []
    blocked  = []
    for fid in ids:
        tgt = by_id.get(fid)
        if not tgt:
            continue
        usages = db.get_file_ids_in_use(tgt["file_id"])
        if usages:
            blocked.append(tgt["file_name"] or str(fid))
        else:
            safe_ids.append(fid)
    if safe_ids:
        db.bulk_soft_delete_files(safe_ids)
    if blocked:
        names = "、".join(blocked[:5])
        return render_template("files.html", records=db.get_file_records(),
                               err=f"⚠️ 以下文件因被规则引用未删除：{names}"), 400
    return redirect("/files")


# ======== 批量操作 ========
def _bulk_ids():
    """从表单取出 ids 列表（int），忽略非法值"""
    ids = []
    for v in request.form.getlist("ids"):
        try:
            ids.append(int(v))
        except (ValueError, TypeError):
            pass
    return ids


@flask_app.route("/kw/bulk", methods=["POST"])
def kw_bulk():
    action = request.form.get("action", "")
    ids    = _bulk_ids()
    if not ids:
        return redirect("/")
    if action == "delete":
        db.bulk_delete_keywords(ids)
    elif action == "enable":
        db.bulk_toggle_keywords(ids, 1)
    elif action == "disable":
        db.bulk_toggle_keywords(ids, 0)
    return redirect("/")


@flask_app.route("/sc/bulk", methods=["POST"])
def sc_bulk():
    action = request.form.get("action", "")
    ids    = _bulk_ids()
    if not ids:
        return redirect("/")
    if action == "delete":
        db.bulk_delete_schedules(ids)
    elif action == "enable":
        db.bulk_toggle_schedules(ids, 1)
    elif action == "disable":
        db.bulk_toggle_schedules(ids, 0)
    _reload()
    return redirect("/")


# ======== 群组管理 ========
@flask_app.route("/chats/add", methods=["POST"])
def chats_add():
    cid   = request.form.get("chat_id", "").strip()
    title = request.form.get("title", "").strip()
    if not cid:
        return redirect("/")
    try:
        db.add_chat_manual(int(cid), title or str(cid))
    except (ValueError, TypeError):
        pass
    return redirect("/")


# 注意：Telegram 群组/频道 chat_id 为负数（如 -1001234567890），
# Flask 默认的 <int:...> 转换器不匹配负数，会导致 404。
# 因此这里用 <cid> 字符串转换器，再手动 int()。
@flask_app.route("/chats/rename/<cid>", methods=["POST"])
def chats_rename(cid):
    try:
        cid_int = int(cid)
    except (ValueError, TypeError):
        return redirect("/")
    title = request.form.get("title", "").strip()
    if title:
        db.update_chat_title(cid_int, title)
    return redirect("/")


@flask_app.route("/chats/delete/<cid>")
def chats_delete(cid):
    try:
        cid_int = int(cid)
    except (ValueError, TypeError):
        return redirect("/")
    db.delete_chat(cid_int)
    return redirect("/")


# ======== 批量导入 ========
@flask_app.route("/import")
def import_page():
    return render_template("import.html", msg=request.args.get("msg"))


@flask_app.route("/import/kw", methods=["POST"])
def import_kw():
    import bulk_import
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect("/import?msg=" + _url_msg("未选择文件"))
    try:
        ok, fail, errors = bulk_import.import_keywords(f.filename, f.read())
    except Exception as e:
        return redirect("/import?msg=" + _url_msg(f"导入失败：{e}"))
    summary = f"关键词导入完成：成功 {ok} 条，失败 {fail} 条"
    if errors:
        summary += "\n\n错误详情：\n" + "\n".join(errors[:20])
        if len(errors) > 20:
            summary += f"\n...（共 {len(errors)} 条错误，仅显示前 20 条）"
    return render_template("import.html", msg=summary)


@flask_app.route("/import/sc", methods=["POST"])
def import_sc():
    import bulk_import
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect("/import?msg=" + _url_msg("未选择文件"))
    try:
        ok, fail, errors = bulk_import.import_schedules(f.filename, f.read())
    except Exception as e:
        return redirect("/import?msg=" + _url_msg(f"导入失败：{e}"))
    _reload()
    summary = f"定时任务导入完成：成功 {ok} 条，失败 {fail} 条"
    if errors:
        summary += "\n\n错误详情：\n" + "\n".join(errors[:20])
        if len(errors) > 20:
            summary += f"\n...（共 {len(errors)} 条错误，仅显示前 20 条）"
    return render_template("import.html", msg=summary)


@flask_app.route("/import/template/<kind>")
def import_template(kind):
    """下载模板。kind 形如 kw_csv / kw_json / sc_csv / sc_json"""
    import bulk_import
    from flask import Response
    mapping = {
        "kw_csv":  (bulk_import.build_keyword_template_csv,  "keywords_template.csv",  "text/csv; charset=utf-8"),
        "kw_json": (bulk_import.build_keyword_template_json, "keywords_template.json", "application/json; charset=utf-8"),
        "sc_csv":  (bulk_import.build_schedule_template_csv, "schedules_template.csv", "text/csv; charset=utf-8"),
        "sc_json": (bulk_import.build_schedule_template_json,"schedules_template.json","application/json; charset=utf-8"),
    }
    if kind not in mapping:
        return "unknown template", 404
    builder, fname, mime = mapping[kind]
    return Response(
        builder(),
        mimetype=mime,
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


def _url_msg(s):
    from urllib.parse import quote
    return quote(s)


@flask_app.route("/debug/routes")
def debug_routes():
    if not check_auth():
        return "unauthorized", 403
    routes = [f"{','.join(r.methods)} {r.rule}" for r in flask_app.url_map.iter_rules()]
    return "<pre>" + "\n".join(sorted(routes)) + "</pre>"
