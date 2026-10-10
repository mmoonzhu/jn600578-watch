# 京能电力（600578.SH）定增公告 → 微信自动提醒

一旦京能电力披露与**定向融资/向特定对象发行A股（定增）**相关的公告，自动推送到你的微信。

数据源：东方财富公告 + 巨潮资讯网（法定披露网站）双源交叉校验，任一源挂掉仍能工作。
去重：按公告标题去重，同一份公告只推一次；已推送的会记进 `state.json`，重启也不会重复推。

---

## 第 1 步：拿到 PushPlus token（2 分钟）

1. 手机或电脑打开 **https://www.pushplus.plus/**
2. 点「微信扫码登录」，用微信扫一下
3. 登录后首页会显示你的 **token**（32 位字符串），点复制
4. 页面下方点「关注公众号」→ 关注 **pushplus推送加** 这个公众号（**必须关注，否则收不到消息**）

> 免费版每天 200 条，这个场景一天最多几条，完全够用。

## 第 2 步：填 token

> **如果你要走上面的 GitHub Actions 云端方案，跳过这一步**，直接去仓库 Settings 里
> 配 `PUSHPLUS_TOKEN` Secret 即可，本地不需要建 config.json。
> 这一步是给**本地运行**（方案 B / C）用的。

在本目录下执行：

```bash
cd /Users/zhumingyue/WorkBuddy/2026-10-10-10-36-56/jn600578-watch
cp config.example.json config.json
```

然后编辑 `config.json`，把 token 粘进去：

```json
{
  "pushplus_token": "粘贴你的32位token"
}
```

（不想建文件也行：设置环境变量 `PUSHPLUS_TOKEN` 同样生效。）

## 第 3 步：验证能收到

```bash
python3 watch.py --test
```

返回 `"code":200` 且微信收到一条「配置成功」的测试消息，就说明通了。

## 第 4 步：正式启用

```bash
python3 watch.py        # 首次运行会自动建立基线并发一条「监控已启动」通知
```

之后每次运行只推送新增公告。

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

**A-2. 把 token 放进 Secrets（不要写进文件）**

仓库页面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

- Name：`PUSHPLUS_TOKEN`
- Secret：粘贴你的 PushPlus token

这是加密存储的，日志里会自动显示为 `***`，**比明文写进文件安全**。
这一步做完，本地根本不需要 `config.json`。

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
