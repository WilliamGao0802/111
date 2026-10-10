# 推送到 GitHub 操作说明（WilliamGao0802/333）

> 目标：把本地完整项目推送覆盖到 `https://github.com/WilliamGao0802/333`，
> 同时清掉远端那 35 个不该进版本库的脏文件（`__pycache__/*.pyc`、`data/`）。
> **命令全部由你自己执行，凭据不经过我。**

---

## 一、当前仓库状态（已核实）

| 项目 | 情况 |
| --- | --- |
| 远端仓库 | `https://github.com/WilliamGao0802/333.git` |
| 远端默认分支 | `main`（提交 `d97de92 Add files via upload`） |
| 本地当前分支 | `master`（6 个提交，最新 `d7fa64d`） |
| 两条历史的关系 | **无共同祖先**（no merge base）——你网页上传的那 2 个提交和我本地这 6 个提交是两条完全独立的线 |
| 远端健康 | `core/` 在（36 个文件齐全）、`app.py`/`serve.py`/`launch.py` 在 |
| 🔴 远端致命缺失 | **`ui/` 目录完全没有** → 这就是 `ModuleNotFoundError: No module named 'ui'` 的根因 |
| 🔴 远端其他缺失 | `tests/`、`tools/`、`.streamlit/`、`.gitignore`、`.gitattributes` |
| 🔴 远端脏文件 | **35 个**：`__pycache__/*.pyc`（20 个）、`data/backups/*.json`（14 个）、`data/bgl.db`（1 个） |
| 本地健康 | 干净，`ui/`(14 文件)、`tests/`、`tools/`、`.streamlit/` 全在，脏文件全部未被追踪 |

**结论**：本地方案是唯一真相源，直接把本地推上去即可。因为两条历史无共同祖先，
不能用普通 `git push`（会被拒），也**不建议用 `--force` 覆盖**（会重写你已经存在的主分支）。
下面用 `--allow-unrelated-histories` 合并，历史都留着，最安全。

---

## 二、方案：合并远端历史 → 清理脏文件 → 推送（推荐）

### 步骤 1：切到 `main` 分支（与 GitHub 默认分支保持一致）

本地现在叫 `master`，GitHub 那边叫 `main`。直接推 `master` 会增加一个新分支、
GitHub 默认分支还指向旧的 `main`，Streamlit Cloud 也不会自动跟着变。所以先改名对齐：

```bash
cd "C:/Users/dw/WorkBuddy/2026-10-10-12-31-09/bgl-ai-learning"
git branch -m master main
```

### 步骤 2：合并远端已有的 2 个提交（保留你的历史，不覆盖）

```bash
git fetch origin
git merge origin/main --allow-unrelated-histories -m "merge: 合并 GitHub 网页上传的历史（保留，不覆盖）"
```

> **可能遇到冲突**：远端 `README.md` / `app.py` / `serve.py` 等与我本地版本内容不同，
> 可能提示冲突。若出现冲突，**全部保留本地版**（本地方案是完整且已修好 bug 的）：
>
> ```bash
> git checkout --ours .          # 冲突文件取本地版
> git add -A
> git merge --continue
> ```
>
> 如果只是想彻底简化（你的历史里没有需要保留的东西），也可以跳过合并，
> 直接走下面的 **方案 B**。

### 步骤 3：从版本库移除脏文件（本地文件保留，不会被删）

```bash
git rm -r --cached __pycache__ core/__pycache__ data 2>/dev/null
```

> `--cached` 的含义：**只从 Git 索引里移除，磁盘上的文件不动**。
> 如果 `__pycache__` 已经被 `.gitignore` 屏蔽、命令报 `did not match any files`，
> 那是正常的，说明它在合并后的树里已经是未追踪状态，可以忽略该行报错。

### 步骤 4：确认 `.gitignore` 生效，避免脏文件再进来

```bash
git check-ignore -v __pycache__/app.cpython-313.pyc data/bgl.db
```

应输出类似 `__.gitignore__:2:__pycache__/` 与 `.gitignore:10:data/`，说明规则已生效。

### 步骤 5：提交清理

```bash
git add -A
git commit -m "chore: 清理版本库脏文件（__pycache__ / data），补齐 ui/ tests/ tools/ .streamlit/ .gitignore 等缺失文件"
```

### 步骤 6：推送

```bash
git push -u origin main
```

**这一步会要求你输入 GitHub 凭据**（见第四节）。推送成功后，
GitHub 上 `main` 分支就 = 本地完整项目。

---

## 三、方案 B：简单粗暴但同样安全（历史不要了）

如果合并冲突太烦，且你不介意丢掉网页上传的那 2 个提交（内容本来就在本地），
可以用这个：**把本地方案作为一个全新提交接到远端历史后面，然后强推**——
注意这不是覆盖，而是用 `--force-with-lease` 保护性推送：

```bash
cd "C:/Users/dw/WorkBuddy/2026-10-10-12-31-09/bgl-ai-learning"

# 1. 本地改名为 main
git branch -m master main

# 2. 把远端历史接进来但丢弃其内容（用 -s ours 策略，保留历史节点、内容取本地）
git fetch origin
git merge origin/main --allow-unrelated-histories -s ours -m "merge: 接续 GitHub 历史，内容以本地完整版为准"

# 3. 清理脏文件
git rm -r --cached __pycache__ data 2>/dev/null
git add -A
git commit -m "chore: 清理版本库脏文件并补齐缺失文件"

# 4. 保护性强推（比 --force 安全：远端若被别人改过会拒绝）
git push --force-with-lease origin main
```

> `-s ours`（ours 策略）：合并时**完全采用本地内容**，远端那 2 个提交只作为历史节点保留。
> 不需要手工解冲突，一次搞定。

---

## 四、GitHub 授权方式（三选一，你自己操作）

`git push` 时会提示输入用户名密码。GitHub 从 2021 年起**不再接受账号密码**，
必须用下面任一种：

### 方式 1：Personal Access Token（推荐，最快）

1. 打开 https://github.com/settings/tokens → **Generate new token (classic)**
2. Note 填 `bgl-push`，Expiration 选 `90 days`，勾选 **`repo`** 权限
3. 生成后**复制那串 `ghp_...`**（只显示一次）
4. 推送时：
   - `Username:` 填 `WilliamGao0802`
   - `Password:` **粘贴那串 token**（不是账号密码）

Windows 上会被 Git Credential Manager 记住，下次不用再输。

### 方式 2：GitHub CLI（最省事，一次登录长期有效）

装好 GitHub CLI 后执行：

```bash
gh auth login      # 选 GitHub.com → HTTPS → Login with a web browser
git push -u origin main
```

浏览器里输一次验证码就完事，之后完全免密。

### 方式 3：SSH 密钥（长期最稳）

```bash
ssh-keygen -t ed25519 -C "WilliamGao0802"
# 把 ~/.ssh/id_ed25519.pub 内容贴到 https://github.com/settings/keys
git remote set-url origin git@github.com:WilliamGao0802/333.git
git push -u origin main
```

---

## 五、推送后必须做的一件事

推上去后，**Streamlit Cloud 需要重启应用**才会重新拉代码：

- 进入 https://share.streamlit.io → 找到你的 app → 右下角 **Manage app** → **Reboot**
- 没有自动更新时，也可以在 Manage app 里点 **Clear cache**

主入口配置保持不变：**`app.py`**（仓库根目录），
`app.py` 顶部已有 `sys.path` 兜底，无论入口在哪一层都能正确导入 `core/`、`ui/`。

---

## 六、推送后自检清单

| 检查项 | 期望结果 |
| --- | --- |
| GitHub 仓库根目录 | 能看到 `ui/`、`tests/`、`tools/`、`.streamlit/`、`.gitignore` |
| 仓库里还有没有 `__pycache__/` | 没有了 |
| 仓库里还有没有 `data/` | 没有了 |
| Streamlit Cloud 应用 | Reboot 后正常显示登录页，不再 `ModuleNotFoundError` |
| 用 `fangyuan` / `123456` 登录 | 能进仪表盘 |

本地也可以一键验证线上是否正常（需要项目里已装 playwright）：

```bash
cd "C:/Users/dw/WorkBuddy/2026-10-10-12-31-09/bgl-ai-learning"
export BGL_BASE="https://你的应用地址.streamlit.app"
node tools/live_verify.js
```

---

## 七、以后每次修改的固定流程

你已定的规矩：**每个修改都要走 Git 并推送到 GitHub**。标准三步：

```bash
cd "C:/Users/dw/WorkBuddy/2026-10-10-12-31-09/bgl-ai-learning"
git add -A
git commit -m "feat/fix/chore: 说明这次改了什么"
git push
```

项目里已有现成工具可复用：

- 改完代码先跑测试：`C:/Users/dw/.workbuddy/binaries/python/envs/default/Scripts/python.exe tools/run_tests.py`（应 62 项全绿）
- 发版本：`python tools/release.py --dry-run` 预演 → 正式执行会自动改 `version.py` + 打 tag
- 同步线上部署包：`python tools/deploy_sync.py --prune`

---

## 八、一句话总结

远端缺的是 **`ui/` 整个目录**（所以报 `No module named 'ui'`）；
本地是完整版。执行第二节步骤 1→6（或第三节方案 B）即可一次修好并清干净脏文件。
授权用 **PAT（方式 1）** 最省事。
