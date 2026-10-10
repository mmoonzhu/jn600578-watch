#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京能电力 (600578.SH) 定向融资 / 定增 公告监控 -> 邮件推送

用法:
    python3 watch.py            正常检查，有新公告就发邮件
    python3 watch.py --init     首次运行：只记录当前公告基线，不发邮件
    python3 watch.py --test     发一封测试邮件，验证邮箱配置是否正确
    python3 watch.py --dry      只在终端打印将要发送的内容，不实际发送、不写状态
    python3 watch.py --all      忽略关键词过滤，检查全部公告

凭据（推荐放 GitHub Secrets，不要写进文件）：
    EMAIL_USER   发件邮箱完整地址
    EMAIL_PASS   SMTP 授权码（不是邮箱登录密码）
    EMAIL_TO     收件地址，留空则发给自己；多个用逗号分隔
    EMAIL_HOST   默认 smtp.qq.com（163: smtp.163.com / Gmail: smtp.gmail.com）
    EMAIL_PORT   默认 465（SSL）；填 587 自动改用 STARTTLS

仅依赖 Python 标准库，无需 pip 安装任何包。
"""

import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
LOG_PATH = os.path.join(BASE_DIR, "watch.log")

STOCK_CODE = "600578"
STOCK_NAME = "京能电力"
CNINFO_ORGID = "gssh0600578"      # 巨潮资讯网机构代码
LOOKBACK_DAYS = 30                # 每次检查回看的天数
FETCH_PAGES = 2                   # 每个数据源抓取页数

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# 关键词：命中任一即推送。想加减范围，直接改这个列表即可。
# ---------------------------------------------------------------------------
KEYWORDS = [
    # 发行本体
    "向特定对象发行", "向特定对象发行股票", "定向增发", "定增", "非公开发行",
    "发行A股", "发行股票", "发行股份", "证券发行", "发行注册",
    # 审核 / 注册流程
    "审核问询", "问询函", "审核中心", "上市委", "审核通过", "审核结果",
    "同意注册", "注册批复", "予以注册", "注册生效", "批文",
    # 方案文件
    "预案", "论证分析", "可行性分析", "募集说明书", "发行方案",
    "摊薄即期回报", "填补措施", "前次募集资金",
    # 审议程序（只盯"临时"股东会——年度股东会是例行事项，已排除）
    "临时股东会", "临时股东大会", "董事会决议", "监事会决议",
    # 发行实施
    "附条件生效", "股份认购", "认购协议", "资产购买协议",
    "发行结果", "发行情况报告书", "发行价格", "发行对象", "认购邀请书",
    "验资", "募集资金", "募集资金到位", "新增股份", "股份变动", "上市公告书",
    # 配套
    "关联交易暨", "豁免要约", "权益变动",
]

# 噪音排除：命中这些词说明跟定增无关，直接丢弃
EXCLUDE = [
    # 与定增无关的日常事项，命中即丢弃
    "委托贷款", "日常关联交易", "担保额度", "风险评估报告",
    "发电量完成情况", "业绩说明会", "投资者关系活动记录",
    "利润分配预案", "权益分派", "分红", "股东回报规划",
    "年度股东会", "年度股东大会", "年度报告", "季度报告", "半年度报告",
    "独立董事辞职", "独立董事津贴", "独立董事述职", "独立董事候选人",
    "会计师事务所", "审计机构", "续聘", "薪酬", "考核", "责任书",
]

# ---------------------------------------------------------------------------
# 里程碑识别：把公告归类到定增流程的具体阶段，推送时一眼看懂进度
# ---------------------------------------------------------------------------
STAGES = [
    ("⑦ 新增股份上市", ["上市公告书", "新增股份", "股份变动", "上市流通"]),
    ("⑥ 发行实施", ["发行结果", "发行情况报告书", "认购邀请书", "缴款", "验资",
                    "募集资金到位", "发行价格"]),
    ("⑤ 证监会同意注册", ["同意注册", "注册批复", "予以注册", "注册生效", "批文"]),
    ("④ 上交所审核通过", ["上市委", "审核通过", "审核结果", "审核中心意见"]),
    ("③ 上交所审核中", ["审核问询", "问询函", "问询回复", "审核问询回复", "回复"]),
    ("② 股东会审议", ["股东大会", "股东会", "临时股东会"]),
    ("① 董事会/预案", ["预案", "董事会决议", "论证分析", "可行性", "附条件生效",
                      "摊薄即期回报", "前次募集资金", "书面审核意见", "监事会决议"]),
]


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def http(url, data=None, headers=None, timeout=20):
    """统一的 HTTP 请求，返回文本。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    h = dict(UA)
    if headers:
        h.update(headers)
    body = urllib.parse.urlencode(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", "ignore")


# ---------------------------------------------------------------------------
# 数据源 1：东方财富公告
# ---------------------------------------------------------------------------
def fetch_eastmoney():
    out = []
    for page in range(1, FETCH_PAGES + 1):
        url = ("https://np-anotice-stock.eastmoney.com/api/security/ann"
               "?sr=-1&page_size=50&page_index=%d&ann_type=A"
               "&client_source=web&stock_list=%s" % (page, STOCK_CODE))
        try:
            raw = json.loads(http(url))
        except Exception as e:
            log("东方财富抓取失败(page=%d): %s" % (page, e))
            break
        lst = (raw.get("data") or {}).get("list") or []
        if not lst:
            break
        for it in lst:
            code = it.get("art_code") or ""
            out.append({
                "title": (it.get("title") or "").strip(),
                "date": (it.get("notice_date") or "")[:10],
                "url": "https://pdf.dfcfw.com/pdf/H2_%s_1.pdf" % code if code else "",
                "src": "东方财富",
            })
        time.sleep(0.3)
    return out


# ---------------------------------------------------------------------------
# 数据源 2：巨潮资讯网（法定披露网站，作为备份源）
# ---------------------------------------------------------------------------
def fetch_cninfo():
    out = []
    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
        "X-Requested-With": "XMLHttpRequest",
    }
    for page in range(1, FETCH_PAGES + 1):
        data = {
            "pageNum": page, "pageSize": 30, "column": "sse", "tabName": "fulltext",
            "plate": "", "stock": "%s,%s" % (STOCK_CODE, CNINFO_ORGID),
            "searchkey": "", "secid": "", "category": "", "trade": "",
            "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true",
        }
        try:
            raw = json.loads(http(url, data=data, headers=headers))
        except Exception as e:
            log("巨潮抓取失败(page=%d): %s" % (page, e))
            break
        anns = raw.get("announcements") or []
        if not anns:
            break
        for a in anns:
            ts = a.get("announcementTime")
            date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
            adj = a.get("adjunctUrl") or ""
            out.append({
                "title": re.sub(r"</?em>", "", a.get("announcementTitle") or "").strip(),
                "date": date,
                "url": "http://static.cninfo.com.cn/" + adj if adj else "",
                "src": "巨潮资讯",
            })
        time.sleep(0.3)
    return out


# ---------------------------------------------------------------------------
# 过滤与归类
# ---------------------------------------------------------------------------
def norm(t):
    return re.sub(r"[\s:：·（）()【】\[\]“”\"'‘’]+", "", t)


def clean_title(t):
    """去掉东方财富/巨潮加的股票名前缀，让推送标题更干净。"""
    return re.sub(r"^%s\s*[:：]\s*" % STOCK_NAME, "", t.strip())


def dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["date"], reverse=True):
        k = norm(it["title"])
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def within_lookback(date_str):
    if not date_str or len(date_str) < 10:
        return False
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except Exception:
        return False
    return (datetime.now() - d).days <= LOOKBACK_DAYS


def matched(title):
    t = norm(title)
    if any(norm(x) in t for x in EXCLUDE):
        return False
    return [k for k in KEYWORDS if norm(k) in t]


def stage_of(title):
    t = norm(title)
    for stage, kws in STAGES:
        if any(norm(k) in t for k in kws):
            return stage
    return "· 定增相关"


# ---------------------------------------------------------------------------
# 推送通道（多通道，填哪个用哪个）
#
#   pushplus : PUSHPLUS_TOKEN                —— 注意：2024-08 起未实名用户发不出消息(错误码905)
#   wecom    : WECOM_WEBHOOK                 —— 企业微信群机器人，免费无限、无需实名
#   bark     : BARK_KEY                      —— iOS 原生推送，免费开源、无需实名
#   wxpusher : WXPUSHER_TOKEN + WXPUSHER_UID —— 微信公众号推送，免费
#   email    : EMAIL_USER + EMAIL_PASS       —— 邮件，免费；配 QQ邮箱微信提醒可变相推到微信
# ---------------------------------------------------------------------------
def _post_json(url, payload, timeout=20):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": UA["User-Agent"],
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _push_pushplus(token, title, html, plain):
    r = _post_json("https://www.pushplus.plus/send", {
        "token": token, "title": title, "content": html,
        "template": "html", "channel": "wechat",
    })
    ok = r.get("code") == 200
    hint = ""
    if r.get("code") == 905:
        hint = "（905 = PushPlus 账号未实名，微信渠道额度为 0，需换通道或实名）"
    return ok, json.dumps(r, ensure_ascii=False) + hint


def _push_wecom(webhook, title, html, plain):
    # 企业微信机器人 markdown 上限 4096 字节，超了就截断
    md = "### %s\n%s" % (title, plain)
    if len(md.encode("utf-8")) > 3800:
        md = md.encode("utf-8")[:3800].decode("utf-8", "ignore") + "\n…(已截断)"
    r = _post_json(webhook, {"msgtype": "markdown", "markdown": {"content": md}})
    return r.get("errcode") == 0, json.dumps(r, ensure_ascii=False)


def _push_bark(key, title, html, plain):
    r = _post_json("https://api.day.app/%s" % key, {
        "title": title, "body": plain, "group": STOCK_NAME, "isArchive": 1,
    })
    return r.get("code") == 200, json.dumps(r, ensure_ascii=False)


def _push_wxpusher(token, uid, title, html, plain):
    r = _post_json("https://wxpusher.zjiecode.com/api/send/message", {
        "appToken": token, "content": html, "summary": title[:60],
        "contentType": 2, "uids": [uid],
    })
    # WxPusher 成功码是 1000
    return r.get("code") == 1000, json.dumps(r, ensure_ascii=False)


def mask_addr(addr):
    """日志里打码邮箱，避免 Secrets 里的地址出现在 GitHub Actions 日志中。"""
    try:
        name, _, domain = addr.partition("@")
    except Exception:
        return "***"
    if not domain:
        return addr
    head = name[:1] + "***" + name[-1:] if len(name) > 2 else "***"
    return "%s@%s" % (head, domain)


def _push_email(title, html, plain):
    # GitHub Secrets 未填时环境变量会是空字符串，所以要用 or 兜底，不能用 get 的默认值
    host = os.environ.get("EMAIL_HOST", "").strip() or "smtp.qq.com"
    try:
        port = int(os.environ.get("EMAIL_PORT", "").strip() or 465)
    except ValueError:
        port = 465
    user = os.environ.get("EMAIL_USER", "").strip()
    pwd = os.environ.get("EMAIL_PASS", "").strip()
    to = os.environ.get("EMAIL_TO", "").strip() or user
    rcpts = [x.strip() for x in to.replace(";", ",").split(",") if x.strip()]
    if not user or not pwd:
        return False, "EMAIL_USER / EMAIL_PASS 未配置完整"
    if not rcpts:
        return False, "EMAIL_TO 为空且 EMAIL_USER 也不是合法邮箱"

    # multipart/alternative：同时给纯文本和 HTML，邮件客户端自选；
    # 只发 HTML 容易被判为垃圾邮件，这是邮件通道必须的一步
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = formataddr((str(Header("京能电力公告监控", "utf-8")), user))
    msg["To"] = ", ".join(rcpts)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.attach(MIMEText(plain or "（无正文）", "plain", "utf-8"))
    msg.attach(MIMEText(html or plain or "（无正文）", "html", "utf-8"))

    shown = ", ".join(mask_addr(x) for x in rcpts)
    srv = None
    try:
        if port == 465:
            srv = smtplib.SMTP_SSL(host, port, timeout=25)
        else:
            srv = smtplib.SMTP(host, port, timeout=25)
            srv.starttls()
        srv.login(user, pwd)
        srv.sendmail(user, rcpts, msg.as_string())
        return True, "邮件已发送至 %s（SMTP %s:%d）" % (shown, host, port)
    except smtplib.SMTPAuthenticationError as e:
        return False, ("SMTP 认证失败：%s。注意 EMAIL_PASS 要填「授权码」不是邮箱登录密码"
                       "（QQ邮箱：设置→账户→开启 SMTP 服务→生成 16 位授权码）" % e)
    except Exception as e:
        return False, "SMTP 发送失败（%s:%d）：%s" % (host, port, e)
    finally:
        if srv:
            try:
                srv.quit()
            except Exception:
                pass


def pick_channel():
    """决定用哪个通道：优先 PUSH_CHANNEL 显式指定，否则按已填的凭据自动探测。"""
    forced = os.environ.get("PUSH_CHANNEL", "").strip().lower()
    candidates = {
        "wecom": os.environ.get("WECOM_WEBHOOK", "").strip(),
        "bark": os.environ.get("BARK_KEY", "").strip(),
        "wxpusher": (os.environ.get("WXPUSHER_TOKEN", "").strip()
                     + os.environ.get("WXPUSHER_UID", "").strip()),
        "email": (os.environ.get("EMAIL_USER", "").strip()
                  + os.environ.get("EMAIL_PASS", "").strip()),
        "pushplus": os.environ.get("PUSHPLUS_TOKEN", "").strip(),
    }
    env = candidates
    if forced:
        return forced, env.get(forced, "")
    # 邮件排第一：公司里最稳、免费、无实名要求，且配了邮箱微信提醒就能回到微信
    for name in ("email", "wecom", "bark", "wxpusher", "pushplus"):
        if env.get(name):
            return name, env[name]
    return "", ""


def send(title, html, plain):
    """统一推送入口，返回 (是否成功, 说明)。"""
    ch, cred = pick_channel()
    if not ch:
        return False, ("未配置任何推送通道。请在仓库 Secrets 里配置："
                       "EMAIL_USER + EMAIL_PASS（推荐），或 WECOM_WEBHOOK / BARK_KEY / "
                       "WXPUSHER_TOKEN+WXPUSHER_UID / PUSHPLUS_TOKEN")
    try:
        if ch == "wecom":
            return _push_wecom(cred, title, html, plain)
        if ch == "bark":
            return _push_bark(cred, title, html, plain)
        if ch == "wxpusher":
            return _push_wxpusher(os.environ.get("WXPUSHER_TOKEN", "").strip(),
                                  os.environ.get("WXPUSHER_UID", "").strip(),
                                  title, html, plain)
        if ch == "email":
            return _push_email(title, html, plain)
        if ch == "pushplus":
            return _push_pushplus(cred, title, html, plain)
        return False, "未知通道: %s" % ch
    except Exception as e:
        return False, "通道 %s 调用异常: %s" % (ch, e)


def build_content(news):
    rows = []
    for n in news:
        link = ('<a href="%s">查看 PDF 原文</a>' % n["url"]) if n["url"] else "（无原文链接）"
        rows.append(
            '<div style="margin:0 0 18px 0;padding:12px 14px;background:#f7f8fa;'
            'border-left:4px solid #c0392b;border-radius:6px;">'
            '<div style="font-size:12px;color:#8a8f99;margin-bottom:6px;">'
            '%s · %s · %s</div>'
            '<div style="font-size:16px;font-weight:600;color:#1f2329;'
            'line-height:1.5;margin-bottom:4px;">%s</div>'
            '<div style="font-size:14px;color:#c0392b;font-weight:600;'
            'margin-bottom:8px;">%s</div>'
            '<div style="font-size:13px;">%s</div>'
            '</div>' % (n["date"], STOCK_NAME, n["src"], n["title"], n["stage"], link)
        )
    return "".join(rows)


def build_plain(news):
    """纯文本版，给企业微信机器人 / Bark 这类不支持 HTML 的通道用。"""
    lines = []
    for n in news:
        lines.append("【%s】%s" % (n["date"], n["title"]))
        lines.append("阶段：%s" % n["stage"])
        if n["url"]:
            lines.append("原文：%s" % n["url"])
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# 状态读写
# ---------------------------------------------------------------------------
def load_state():
    if not os.path.exists(STATE_PATH):
        return {"seen": [], "last_check": None}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": [], "last_check": None}


def save_state(state):
    state["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["seen"] = state["seen"][-500:]
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_token():
    tok = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if tok:
        return tok
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return (json.load(f).get("pushplus_token") or "").strip()
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    do_init = "--init" in args
    do_test = "--test" in args
    do_dry = "--dry" in args
    do_all = "--all" in args

    log("=" * 60)
    log("开始检查 %s(%s) 公告" % (STOCK_NAME, STOCK_CODE))

    # 本地 config.json 里的配置注入环境变量（云端用 Secrets，本地用文件，两者兼容）
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    if isinstance(v, str) and not k.startswith("_"):
                        K = k.upper()
                        if not os.environ.get(K):
                            os.environ[K] = v.strip()
        except Exception as e:
            log("读取 config.json 失败: %s" % e)

    if not pick_channel()[0]:
        log("未配置任何推送通道")
        print("\n未配置推送通道。任选其一配置即可：\n"
              "  EMAIL_USER + EMAIL_PASS   邮件（推荐，免费、无需实名）\n"
              "  WECOM_WEBHOOK             企业微信群机器人（免费无限、无需实名）\n"
              "  BARK_KEY                  iPhone 推送（免费、无需实名）\n"
              "  WXPUSHER_TOKEN + WXPUSHER_UID   微信公众号推送（免费）\n"
              "  PUSHPLUS_TOKEN            注意：未实名账号额度为 0，发不出消息\n")
        sys.exit(2)
    log("使用推送通道: %s" % pick_channel()[0])

    if do_test:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = "【测试】京能电力公告监控已就绪"
        html = ('<div style="padding:20px;font-family:-apple-system,sans-serif;">'
                '<h3>配置成功</h3>'
                '<p>京能电力（600578.SH）定增/定向融资公告将推送到这里。</p>'
                '<p style="color:#8a8f99;">测试时间：%s</p></div>' % now)
        plain = "配置成功\n京能电力（600578.SH）定增/定向融资公告将推送到这里。\n测试时间：%s" % now
        ok, info = send(title, html, plain)
        log("测试推送返回: %s | 成功=%s" % (info, ok))
        print("推送结果:", info)
        sys.exit(0 if ok else 1)

    # 抓取 -> 统一标题 -> 去重（两源标题前缀不同，必须先清洗再去重）
    raw_items = fetch_eastmoney() + fetch_cninfo()
    for x in raw_items:
        x["title"] = clean_title(x["title"])
    items = dedupe(raw_items)
    if not items:
        log("两个数据源都没抓到公告，本次跳过（避免误报）")
        sys.exit(1)
    log("共抓取到 %d 条不重复公告" % len(items))

    # 首次运行自动建立基线，避免一次性刷屏历史公告
    first_run = not os.path.exists(STATE_PATH)
    if first_run:
        do_init = True
        log("首次运行：自动建立基线，不推送历史公告")

    recent = [x for x in items if within_lookback(x["date"])]
    if do_all:
        hits = recent
        for h in hits:
            h["stage"] = stage_of(h["title"])
    else:
        hits = []
        for x in recent:
            ks = matched(x["title"])
            if ks:
                x["stage"] = stage_of(x["title"])
                hits.append(x)

    state = load_state()
    seen = set(state.get("seen", []))
    news = [x for x in hits if norm(x["title"]) not in seen]
    news.sort(key=lambda x: x["date"], reverse=True)

    if do_init:
        for x in items:
            seen.add(norm(x["title"]))
        state["seen"] = sorted(seen)
        save_state(state)
        log("已建立基线：记录 %d 条历史公告，后续仅推送新增" % len(seen))
        print("\n基线建立完成，记录了 %d 条历史公告。" % len(seen))
        print("下次运行时起，只推送新增的定增相关公告。")
        if first_run and not do_dry:
            latest = [x for x in items if matched(x["title"])]
            latest.sort(key=lambda x: x["date"], reverse=True)
            tail = ""
            if latest:
                tail = ("<p style='font-size:14px;'>当前最新一条定增公告："
                        "<b>%s</b>（%s）</p>" % (latest[0]["title"], latest[0]["date"]))
            plain = ("监控已启动\n京能电力（600578.SH）定增/定向融资公告将自动推送到这里。\n"
                     "已记录 %d 条历史公告作为基线，此后仅推送新增公告。" % len(seen))
            if latest:
                plain += "\n当前最新一条定增公告：%s（%s）" % (latest[0]["title"], latest[0]["date"])
            ok, info = send("【%s】公告监控已启动" % STOCK_NAME,
                            '<div style="padding:20px;font-family:-apple-system,sans-serif;">'
                            '<h3>监控已启动</h3>'
                            '<p>京能电力（600578.SH）定增/定向融资公告将自动推送到这里。</p>'
                            '<p style="color:#8a8f99;">已记录 %d 条历史公告作为基线，'
                            '此后仅推送新增公告。</p>%s</div>' % (len(seen), tail),
                            plain)
            log("启动通知推送结果: %s | 成功=%s" % (info, ok))
            # 启动通知发不出去说明通道有问题，必须让任务失败，否则用户会一直蒙在鼓里
            if not ok:
                print("启动通知推送失败：%s" % info)
                sys.exit(1)
        sys.exit(0)

    if not news:
        log("本次检查无新增定增相关公告")
        # 心跳：默认开启（配 DAILY_HEARTBEAT=0 关闭）。每天一封「监控正常」，
        # 让你能确认任务真的在跑 —— 不然 GitHub Action 全绿你也并不知道有没有执行
        if (os.environ.get("DAILY_HEARTBEAT", "").strip() or "1") != "0":
            today = datetime.now().strftime("%Y-%m-%d")
            if state.get("last_heartbeat") != today:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                latest = max((x["date"] for x in items if x.get("date")), default="-")
                detail = ("已扫描 %d 条公告（近 %d 天），命中关键词 %d 条，均为历史已推送内容。"
                          % (len(items), LOOKBACK_DAYS, len(hits)))
                ok, info = send(
                    "【%s】监控正常 · %s" % (STOCK_NAME, today),
                    '<div style="padding:18px;font-family:-apple-system,sans-serif;">'
                    '<h3 style="margin:0 0 10px 0;">监控正常运行</h3>'
                    '<p>本次检查无新增定增相关公告。</p>'
                    '<p style="color:#8a8f99;font-size:13px;">'
                    '检查时间：%s<br>%s<br>库内最新公告日期：%s</p></div>' % (now, detail, latest),
                    "监控正常运行，本次检查无新增定增公告。\n检查时间：%s\n%s\n库内最新公告日期：%s"
                    % (now, detail, latest))
                log("心跳发送: %s | 成功=%s" % (info, ok))
                if not ok:
                    print("心跳发送失败：%s" % info)
                    sys.exit(1)
                state["last_heartbeat"] = today
        save_state(state)
        sys.exit(0)

    log("发现 %d 条新公告，准备推送" % len(news))
    html = build_content(news)
    plain = build_plain(news)
    title = "【%s】定增新公告 %d 条 · %s" % (STOCK_NAME, len(news), news[0]["stage"].strip("①②③④⑤⑥⑦ "))

    if do_dry:
        print("\n--- 将要推送 ---\n标题:", title)
        for n in news:
            print("  [%s] %s | %s" % (n["date"], n["stage"], n["title"]))
        sys.exit(0)

    for attempt in range(3):
        ok, info = send(title, html, plain)
        log("推送返回(第%d次): %s | 成功=%s" % (attempt + 1, info, ok))
        if ok:
            for x in news:
                seen.add(norm(x["title"]))
            state["seen"] = sorted(seen)
            save_state(state)
            log("推送成功，状态已更新")
            print("推送成功：%d 条公告已发出" % len(news))
            sys.exit(0)
        time.sleep(3)

    log("三次推送均失败，状态未更新，下次会重试")
    sys.exit(1)


if __name__ == "__main__":
    main()
