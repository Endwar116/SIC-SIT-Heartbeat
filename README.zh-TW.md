# SIC-SIT-Heartbeat

**讓 agent 自己跳心跳跑一整晚。你回來，每一拍都能稽核、每次刪除都能回滾、而且看得出哪個檔案、哪條規則要改。**

適用 **Claude Code**（命令列、VS Code 擴充、桌面版）——走 `PreToolUse` 掛鉤；也適用任何**終端機排程器**（cron、launchd、systemd）——一支腳本。只用 Python 標準函式庫，不裝任何套件。英文說明在 [README.md](README.md)。

---

## 這在解什麼問題

一個自主 agent 凌晨三點醒來做事，沒人在看。現有工具很會**記錄**它做了什麼，[Gryph](https://github.com/safedep/gryph) 還能照政策在執行前擋（見[先前技術](docs/PRIOR_ART.md)）。我們找不到任何工具做這四件：

* 讓紀錄**防竄改**，讓 agent 沒辦法悄悄修掉自己的歷史
* 讓刪除**預設可回滾**
* 把**那一拍本身**當成治理單位
* 把昨晚出的事故，變成明天**會真的擋人的規則**

這個 repo 做這四件事，用的是一個下午就能讀完的標準函式庫 Python——另外自帶一道刪除閘，因為我們要閘的決定跟每一拍記在同一本帳上。

## 跑了一晚之後你拿到什麼

| 你想知道 | 答案在 | 指令 |
|---|---|---|
| 每一拍發生什麼 | `ledger/events.log` | `cat` |
| 有沒有人（包括 agent 自己）改過歷史 | 每一輪的雜湊鏈 | `python3 ledger/ledger.py verify` |
| 閘門擋了什麼、何時、為什麼 | `state/gate_decisions.jsonl` | `cat` |
| 刪了什麼、怎麼放回去 | `trash/*/TOMBSTONE.md` | `python3 rollback/tombstone.py restore <目錄>` |
| 哪些背景服務安靜地死了 | 機器判定，三個訊號 | `python3 heartbeat/health.py` |
| 以前出過什麼事、有沒有東西在執行那條教訓 | `laws/` | `python3 laws/legislate.py debts` |

## 那個循環

```
排程器 ─▶ 醒來閘 ─▶ 檢查 ─▶ （做事，動手前閘門先擋）─▶ 記一輪帳 ─▶ 離開碼 0/1
                                                                │
                                          出事了？──▶ 法條 ──▶ 閘門（或一筆記在帳上的欠債）
```

每一拍在 append-only 帳本上加一輪 **SIC-JS 4.0**，`雜湊 = sha256(前一輪雜湊 + 本輪正規化 JSON)`。
會漂移的欄位（輪次、上游雜湊、身分、時間）由程式從帳本本身推導；只有語義欄位由 agent 提供。
agent 可以宣稱任務「完成」——帳本照記，但會永久掛一個 `AI_SELF_CLOSED` 旗標。**完成是操作者蓋的章，不是 agent 說的話。**

完整說明：[架構](docs/ARCHITECTURE.md) · [帳本規格](docs/SPEC_LEDGER.md) · [閘門](docs/SPEC_GATES.md) · [事故→法條](docs/SPEC_INCIDENT_LAW.md) · [威脅模型](docs/THREAT_MODEL.md)

## 五分鐘上手

```bash
git clone https://github.com/Endwar116/SIC-SIT-Heartbeat && cd SIC-SIT-Heartbeat
./install/install.sh                 # Claude Code：先備份 ~/.claude/settings.json，加三個掛鉤
python3 ledger/ledger.py verify      # ✅ 鏈完整——0 輪
./heartbeat/tick.sh                  # 跳一拍 → 印出  ⚓ R1 · seq1 · <雜湊16碼>
python3 -m unittest discover -s tests
```

然後在 Claude Code 裡試著刪東西：

```
> rm -rf ./scratch
⛔ file-governance: hard delete detected (rm).
   規則：刪除 = 搬進 ~/.sic-sit-heartbeat/trash + 寫 TOMBSTONE.md（30 天內可還原）
   請用：python3 rollback/tombstone.py trash ./scratch --why "<一句理由>"
```

終端機與 VS Code 安裝：[install/INSTALL.md](install/INSTALL.md)。

## 四道閘（在工具執行**之前**跑）

| 閘 | 擋什麼 | 從哪個事故來 |
|---|---|---|
| `gates/file_governance.py` | `rm`、`shred`、`find -delete`、`git clean -f`、重導向清空——暫存區與回收區以外 | 維護者自己一再想硬刪 |
| `gates/monitor_dedup.py` | 掛一個跟登記簿裡活著的等價的監看 | **假設**鐘死了就重掛，結果三顆心跳同時跳 |
| `gates/prereg_gate.py` | 任何看起來像實驗、卻沒引用**已封緘**預註冊的東西 | 模板寫了五版、三輪實驗一份都沒封 |
| `gates/decision_card.py` | 要人裁的卡缺五要件任一；同時掛超過三張 | 操作者面對 21 張答不出來的卡 |

契約：stdin 進 JSON，**離開碼 2 擋下**（理由送回 agent），0 放行，閘門自己壞掉時放行並記錄。每個決定都追加到 `state/gate_decisions.jsonl`。

## 法條

`laws/examples/` 有十一條，全部來自真實運作的事故，去識別後保留機制：每條有可檢查的條件、有指名的執行者（或誠實標 `none-yet`）。先讀這兩條：

* **law-007** — 外圍訊號（離開碼、日誌不在、程序清單）只能**開啟**調查；只有當事人自己寫的紀錄能**結案**。判「死了」之前先排除「做完收工」。
* **law-008** — 用被授權的權力做決定之前，先找有沒有規則已經綁在那件事上（程式碼、既有命令、設計時寫的核准條件）。直覺三次全錯。

管線是工具不是文件：`python3 laws/legislate.py new --what ... --signal ... --cause ... --text ... --check ... --enforce gate --ref gates/x.py`。

## 先前技術，講實話

如果你要的是記錄八種 agent 的每一個檔案／工具／指令動作、或照政策在執行前擋，請用 [Gryph](https://github.com/safedep/gryph)——它兩件都做得比這個 repo 好。我們多出來的是：每一拍一輪的雜湊鏈帳本、可回滾的墓碑刪除、治理心跳本身、事故→法條→閘門管線。
這裡的架構是兩篇已發表設計的參考實作——動作改動目標系統前的外部治理檢查點（[AgentBound](https://arxiv.org/html/2606.30970)）、與雜湊鏈防竄改紀錄加驗證或停止（[Aegis](https://arxiv.org/html/2603.16938v1)）——再加上文獻沒涵蓋的兩件：治理自主**週期本身**，以及事故→法條→閘門管線。完整對照表：[docs/PRIOR_ART.md](docs/PRIOR_ART.md)。

## 跟誰一起用

[Gryph](https://github.com/safedep/gryph) 記錄你的 agent 做的每一件事；這個 repo 擋掉其中破壞性的那部分、並把每一拍串成雜湊鏈。
[halo-record](https://github.com/bkuan001/halo-record) 在「每次呼叫」的粒度做雜湊鏈；[heartbeat-agent-framework](https://github.com/muxueqingze/heartbeat-agent-framework) 的專案清單很適合當每一拍的工作來源。
怎麼拼在一起：[docs/INTEROP.md](docs/INTEROP.md)。安全回報：[SECURITY.md](SECURITY.md)。

## 致敬——我們站在誰的肩膀上

這個 repo 之所以小，是因為別人已經把大的部分做好了。列在這裡的不是對手，是這個 repo 設計上要「並排」的專案：

* **[Gryph](https://github.com/safedep/gryph)**（SafeDep，Apache-2.0）——我們所知最好的本機優先 coding-agent 稽核軌跡。今天只裝一樣東西的話，裝 Gryph。我們做「閘門＋帳本」這一層，正是**因為** Gryph 已經把「記錄一切」做走了——見 [INTEROP.md](docs/INTEROP.md)。
* **[halo-record](https://github.com/bkuan001/halo-record)**（Apache-2.0）——一行 Python 就能包住 agent 的 append-only 雜湊鏈紀錄，寫入前先塗黑敏感值。我們的帳本跟它是同一個完整性想法；它的塗黑紀律是我們該學的。
* **[heartbeat-agent-framework](https://github.com/muxueqingze/heartbeat-agent-framework)**（MIT）——把「排程醒來、推進工作」講得最清楚的設計樣式。
* **[AgentBound](https://arxiv.org/html/2606.30970)** 與 **[Aegis](https://arxiv.org/html/2603.16938v1)**——比我們更早把這套程式碼在執行的兩個不變式寫成正式論文。**[DEMM-Bench](https://arxiv.org/pdf/2606.20634)** 則是這類系統該怎麼被評量。
* **[Claude Code hooks](https://code.claude.com/docs/en/hooks)**——`PreToolUse` 契約（離開碼 2 擋下）讓閘門不需要包裝程序就能存在。

你的專案該在這張表上的話，開個 PR 加進來——附一行「兩邊怎麼拼」。

## 現況

`v0.2.0`。`v0.1.0` 在對抗審查發現刪除閘可繞過、帳本雜湊不足後撤回（見 CHANGELOG）。維護者在 macOS 上每天實際使用；Linux 路徑盡力支援；不支援 Windows。只用標準函式庫；測試跑在 Python 3.9–3.12。雜湊鏈是**可察覺竄改**，不是防竄改——依賴它之前先讀[威脅模型](docs/THREAT_MODEL.md)。

## 授權

MIT——見 [LICENSE](LICENSE)。
