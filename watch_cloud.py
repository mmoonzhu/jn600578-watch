#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京能电力 (600578.SH) 定增公告监控 —— 无状态版（专为云端沙箱设计）

特点：
  * 不读写任何状态文件，跑完即走，沙箱销毁毫无影响
  * 用「发布日期窗口」代替历史记录判断新旧（数据源只精确到日期，无法做小时级窗口）
  * 仅依赖 Python 标准库，任何 Python 3 都能直接跑

用法：
  PUSHPLUS_TOKEN=你的token python3 watch_cloud.py
  PUSHPLUS_TOKEN=xxx WINDOW_DAYS=3 python3 watch_cloud.py   # 扩大回溯天数
  PUSHPLUS_TOKEN=xxx python3 watch_cloud.py --dry            # 只打印不推送
  PUSHPLUS_TOKEN=xxx python3 watch_cloud.py --test           # 发一条测试消息

已知取舍：由于公告时间只有日期粒度，本版本可能把同一份公告重复推送 1 次
（窗口内每天第一次命中都会推）。不漏优先于不重复。
若需严格不重复，请用有状态的 watch.py（配合 GitHub Actions 或本地 launchd）。
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

STOCK_CODE = "600578"
STOCK_NAME = "京能电力"
CNINFO_ORGID = "gssh0600578"
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "2"))  # 回溯几天（含今天）
FETCH_PAGES = 2

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

KEYWORDS = [
    "向特定对象发行", "向特定对象发行股票", "定向增发", "定增", "非公开发行",
    "发行A股", "发行股票", "发行股份", "证券发行", "发行注册",
    "审核问询", "问询函", "审核中心", "上市委", "审核通过", "审核结果",
    "同意注册", "注册批复", "予以注册", "注册生效", "批文",
    "预案", "论证分析", "可行性分析", "募集说明书", "发行方案",
    "摊薄即期回报", "填补措施", "前次募集资金",
    "临时股东会", "临时股东大会", "董事会决议", "监事会决议",
    "附条件生效", "股份认购", "认购协议", "资产购买协议",
    "发行结果", "发行情况报告书", "发行价格", "发行对象", "认购邀请书",
    "验资", "募集资金", "募集资金到位", "新增股份", "股份变动", "上市公告书",
    "关联交易暨", "豁免要约", "权益变动",
]

EXCLUDE = [
    "委托贷款", "日常关联交易", "担保额度", "风险评估报告",
    "发电量完成情况", "业绩说明会", "投资者关系活动记录",
    "利润分配预案", "权益分派", "分红", "股东回报规划",
    "年度股东会", "年度股东大会", "年度报告", "季度报告", "半年度报告",
    "独立董事辞职", "独立董事津贴", "独立董事述职", "独立董事候选人",
    "会计师事务所", "审计机构", "续聘", "薪酬", "考核", "责任书",
]

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
    print("[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def http(url, data=None, headers=None, timeout=20):
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


def norm(t):
    return re.sub(r"[\s:：·（）()【】\[\]“”\"'‘’]+", "", t)


def clean_title(t):
    return re.sub(r"^%s\s*[:：]\s*" % STOCK_NAME, "", t.strip())


def matched(title):
    t = norm(title)
    if any(norm(x) in t for x in EXCLUDE):
        return False
    return any(norm(k) in t for k in KEYWORDS)


def stage_of(title):
    t = norm(title)
    for stage, kws in STAGES:
        if any(norm(k) in t for k in kws):
            return stage
    return "· 定增相关"


def pushplus(token, title, content):
    payload = json.dumps({
        "token": token, "title": title, "content": content,
        "template": "html", "channel": "wechat",
    }).encode("utf-8")
    req = urllib.request.Request("https://www.pushplus.plus/send", data=payload,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": UA["User-Agent"]})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def build_content(news):
    rows = []
    for n in news:
        link = ('<a href="%s">查看 PDF 原文</a>' % n["url"]) if n["url"] else ""
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


def main():
    args = sys.argv[1:]
    do_test = "--test" in args
    do_dry = "--dry" in args

    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        log("未设置环境变量 PUSHPLUS_TOKEN")
        print("用法: PUSHPLUS_TOKEN=你的token python3 watch_cloud.py")
        sys.exit(2)

    if do_test:
        r = pushplus(token, "【测试】京能电力公告监控已就绪",
                     '<div style="padding:20px;font-family:-apple-system,sans-serif;">'
                     '<h3>配置成功</h3>'
                     '<p>京能电力（600578.SH）定增/定向融资公告将推送到这个微信。</p>'
                     '<p style="color:#8a8f99;">测试时间：%s</p></div>'
                     % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        log("测试推送返回: %s" % r)
        sys.exit(0 if r.get("code") == 200 else 1)

    raw = fetch_eastmoney() + fetch_cninfo()
    for x in raw:
        x["title"] = clean_title(x["title"])

    seen, items = set(), []
    for x in sorted(raw, key=lambda a: a["date"], reverse=True):
        k = norm(x["title"])
        if not k or k in seen:
            continue
        seen.add(k)
        items.append(x)

    if not items:
        log("两个数据源都没抓到公告，本次跳过")
        sys.exit(1)

    # 日期窗口：数据源只精确到日期，故按天回溯
    cutoff = (datetime.now() - timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
    hits = [x for x in items if x["date"] >= cutoff and matched(x["title"])]
    for h in hits:
        h["stage"] = stage_of(h["title"])
    hits.sort(key=lambda x: x["date"], reverse=True)

    log("共 %d 条公告，窗口(>=%s)内定增相关 %d 条" % (len(items), cutoff, len(hits)))

    if not hits:
        log("窗口内无定增相关公告，静默退出")
        sys.exit(0)

    title = "【%s】定增新公告 %d 条 · %s" % (
        STOCK_NAME, len(hits), hits[0]["stage"].strip("①②③④⑤⑥⑦ "))

    if do_dry:
        print("\n--- 将要推送 ---\n标题:", title)
        for n in hits:
            print("  [%s] %s | %s | %s" % (n["date"], n["stage"], n["title"], n["url"]))
        sys.exit(0)

    for attempt in range(3):
        try:
            r = pushplus(token, title, build_content(hits))
            log("推送返回: %s" % r)
            if r.get("code") == 200:
                log("推送成功：%d 条" % len(hits))
                sys.exit(0)
        except Exception as e:
            log("推送异常(第%d次): %s" % (attempt + 1, e))
        time.sleep(3)

    log("三次推送均失败")
    sys.exit(1)


if __name__ == "__main__":
    main()
