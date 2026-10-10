# 京能电力（600578.SH）定增公告 → 微信自动提醒

一旦京能电力披露与**定向融资/向特定对象发行A股（定增）**相关的公告，自动推送到你的微信。

数据源：东方财富公告 + 巨潮资讯网（法定披露网站）双源交叉校验，任一源挂掉仍能工作。
去重：按公告标题去重，同一份公告只推一次；已推送的会记进 `state.json`，重启也不会重复推。

---

## 第 1 步：选一个推送通道

> ⚠️ **不要用未实名的 PushPlus。** 官方自 2024-08 起规定：未实名认证用户无法调用发送接口
> （返回错误码 `905`），微信渠道日额度为 **0 次**。而实名要么单独付费，要么买会员。
> 所以 PushPlus 只适合你已经实名/买了会员的情况。
>
> 脚本已支持多通道，**填哪个用哪个**，切换不用改代码。

| 通道 | 免费 | 实名 | 消息落在哪 | 怎么拿凭据 |
|---|---|---|---|---|
| **企业微信群机器人**（推荐） | 是，无限量 | 不需要 | 企业微信 App | 企业微信里建个群（可以只有你自己）→ 群设置 → 群机器人 → 添加 → 复制 Webhook 地址 |
| **Bark** | 是，开源 | 不需要 | iPhone 通知栏 | App Store 装 Bark → 打开 App 复制 key（形如 `https://api.day.app/xxxxx` 的末段） |
| **WxPusher** | 是 | 不需要 | 微信 | wxpusher.zjiecode.com 微信扫码注册 → 创建应用拿 `AppToken` → 扫码关注拿 `UID` |
| PushPlus | 否（未实名发不出） | **需要付费** | 微信 | 未实名请跳过 |

> 企业微信不需要企业认证，个人注册即可，建个"只有自己"的群完全没问题。

## 第 2 步：填凭据

**走 GitHub Actions 云端**：仓库 **Settings → Secrets and variables → Actions → New repository secret**，
按通道填一个即可（`WECOM_WEBHOOK` / `BARK_KEY` / `WXPUSHER_TOKEN`+`WXPUSHER_UID`）。
加密存储，日志里显示 `***`。本地不需要建 config.json。

**本地运行**：

```bash
cd /Users/zhumingyue/WorkBuddy/2026-10-10-10-36-56/jn600578-watch
cp config.example.json config.json
```

编辑 `config.json`，把你选中的那一项填进去，其余删掉即可。
（不想建文件也行：设置同名环境变量同样生效。）

## 第 3 步：验证能收到

```bash
WECOM_WEBHOOK=你的地址 python3 watch.py --test     # 换成你选的通道
```

手机收到一条「配置成功」的测试消息，就说明通了。**没收到就一定是没配好**——
脚本会打印接口返回的原始错误，照着改就行。

## 第 4 步：正式启用

```bash
python3 watch.py        # 首次运行会自动建立基线并发一条「监控已启动」通知
```

之后每次运行只推送新增公告。

**推送失败会立刻暴露**：脚本在推送失败时以退出码 1 结束，GitHub Actions 那个 job 会变红，
GitHub 还会给你发邮件。不会再出现"显示成功但根本没发出去"的情况。
（可选：配 `DAILY_HEARTBEAT=1`，每天推一条「监控正常」，用来确认系统还活着。）

---

## 设置自动定时运行（三选一）

> ⚠️ **只选一个方案，不要同时开多个。** 两个地方同时写 `state.json` 会互相覆盖，
> 导致漏推或重复推。

### 方案 A：GitHub Actions —— 真·云端，电脑关机也照跑（推荐）

脚本跑在 GitHub 的服务器上，跟你电脑开不开机完全无关，7×24 生效。免费额度足够
（每月 2000 分钟，本方案每月约用掉 300~700 分钟）。

**A-1. 建一个私有仓库，把这个目录传上去**

在 GitHub 新建一个 **Private** 仓库（比如叫 `jn600578-watch`），然后在本目录执行：

```bash
cd /Users/zhumingyue/WorkBuddy/2026-10-10-10-36-56/jn600578-watch
git init
git remote add origin git@github.com:你的用户名/jn600578-watch.git
git add watch.py .github README.md
git commit -m "init: 京能电力定增公告监控"
git push -u origin main
```

> 目录里 `.github/workflows/ann-watch.yml` 已经写好了，**不用改**，
> 传上去后 GitHub 会自动识别并开始定时执行。

**A-2. 把推送凭据放进 Secrets（不要写进文件）**

仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

按你在第 1 步选的通道填（至少填一个，别用未实名的 PushPlus）：

| 通道 | Secret 名 |
|---|---|
| 企业微信机器人 | `WECOM_WEBHOOK` |
| Bark | `BARK_KEY` |
| WxPusher | `WXPUSHER_TOKEN` 和 `WXPUSHER_UID`（两个都要） |

加密存储，日志里显示为 `***`，比明文写进文件安全。配好之后本地不需要 `config.json`。

想每天收到一条「监控正常」的保活消息，再加一个 `DAILY_HEARTBEAT` = `1`（不加也行）。

**A-3. 验证**

仓库页面 → **Actions** 标签 → 左侧选「京能电力定增公告监控」→ 右上角 **Run workflow**
手动跑一次。跑完你应该在微信收到「监控已启动」的消息。

之后每 30 分钟自动检查一次。

**检查频率**：北京时间 **09:07 和 21:07** 各一次（UTC 01:07 / 13:07，刻意避开整点，
因为 GitHub 在整点负载高会推迟）。分别覆盖盘前和盘后两个公告披露高峰。

因为有 `state.json` 做去重，**即使某次被跳过也不会漏**——下次运行时未推送过的公告仍在
30 天回溯窗口内，会补推。这是它优于无状态方案的关键。

改频率：编辑 `.github/workflows/ann-watch.yml` 里的 `cron`（注意是 UTC 时间，北京时间减 8）。

**已知局限**：GitHub 在负载高峰时，定时任务可能延迟几分钟到几十分钟。
定增公告不是抢秒级的行情，晚几十分钟无妨；如果你要求分钟级，就用方案 B。

---

### 方案 B：macOS 原生定时器 —— 本地常驻，最及时

```bash
cp com.jndl.annwatch.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.jndl.annwatch.plist
```

- 默认 **每小时** 检查一次，开机自动启动，无需登录操作
- 查看是否在跑：`launchctl list | grep jndl`
- 停止：`launchctl unload ~/Library/LaunchAgents/com.jndl.annwatch.plist`
- 改频率：编辑 plist 里的 `StartInterval`（单位秒，3600 = 1 小时）

**前提：电脑要开机**（合盖睡眠时会暂停）。适合你电脑基本常开的情况。
此时 token 放在本地 `config.json` 里，只存在你自己的磁盘上。

---

### 方案 C：WorkBuddy 定时任务（已暂停，不推荐）

WorkBuddy 里那个自动化任务已经**设为暂停**，因为它和方案 A 会同时写 `state.json` 造成冲突。

它本身的局限：绑定的是你**本地**的这个工作目录，脚本和 `state.json` 都在本地磁盘。
WorkBuddy 若改用**云端沙箱**执行，读不到本地文件，且沙箱在任务结束后销毁、`state.json`
无法留存 —— 结果是每次都从头建基线，永远推不出新公告。

如果以后想启用它，请先停掉方案 A 的 GitHub Actions。

---

### 附：无状态版 `watch_cloud.py`（备用，不写任何文件）

`watch_cloud.py` 是给「跑完即销毁」的云端沙箱准备的版本，**完全不读写 `state.json`**，
改用「回溯最近 N 天的发布日期」判断新旧。

```bash
PUSHPLUS_TOKEN=你的token python3 watch_cloud.py            # 默认回溯 2 天
PUSHPLUS_TOKEN=xxx WINDOW_DAYS=3 python3 watch_cloud.py    # 扩大窗口
PUSHPLUS_TOKEN=xxx python3 watch_cloud.py --dry            # 只打印不推送
```

**为什么它不是默认方案**：实测两个数据源的公告时间都只精确到**日期**（巨潮的时间戳统一是
`00:00:00`），做不了「最近几小时」的精细窗口。没有状态就无法既保证不漏又保证不重复——
每天跑 2 次的话，同一份公告会重复推 1 次；想少重复就要缩小窗口，代价是某次被跳过就漏。

结论：**能存状态就存状态**（方案 A/B），无状态版只在确实无处可存时才用。

---

## 常用命令

| 命令 | 作用 |
|---|---|
| `python3 watch.py` | 正常检查，有新增就推微信 |
| `python3 watch.py --test` | 发测试消息，验证 token |
| `python3 watch.py --dry` | 只打印要推什么，不推送、不改状态（调试用） |
| `python3 watch.py --all` | 忽略关键词，检查全部公告 |
| `python3 watch.py --init` | 重建基线（换主题/误清状态时用） |

运行日志在 `watch.log`。

---

## 调整监控范围

打开 `watch.py` 顶部的两个列表即可：

- `KEYWORDS` — 命中任一即推送。默认覆盖定增全流程：预案、论证分析、问询回复、审核通过、同意注册、发行结果、上市公告书等。
- `EXCLUDE` — 命中任一则丢弃。已排除利润分配、年报、委托贷款、独立董事变动等日常噪音。

如果你也想盯**债券融资**（京能电力今年同时发了科创债），在 `KEYWORDS` 里加上：
`"公司债券", "债务融资工具", "科技创新债券", "票面利率", "簿记建档"`

---

## 定增流程对照（推送消息里的 ①~⑦ 就是这些阶段）

```
① 董事会审议 / 预案披露      ← 2026-07-17 已完成
② 股东会审议通过            ← 2026-08-05 已完成
③ 上交所审核（问询 / 回复）   ← 当前大概率在这一步
④ 上交所审核通过
⑤ 证监会同意注册
⑥ 发行实施（认购、缴款、验资）
⑦ 新增股份上市
```

京能电力本次方案：募资不超 50 亿元，发行价 5.38 元/股，不超 20.08 亿股，
控股股东京能集团认购 10~25 亿元。募投涿州热电扩建、乌兰察布风光火储基地、收购十堰热电 40% 股权。

---

## 常见问题

**收不到消息？**
1. 确认关注了「pushplus推送加」公众号
2. `python3 watch.py --test` 看返回 code 是否为 200
3. 看 `watch.log` 有没有报错

**会不会重复推？**
不会。每份公告推一次后记入 `state.json`，后续运行自动跳过。

**误报/漏报？**
改 `KEYWORDS` / `EXCLUDE` 即可，改完立刻生效，不用重启定时器。
