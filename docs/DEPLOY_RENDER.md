# 部署到 Render（公网访问，无需本机 Python）

别人打开链接即可使用本平台。托管可用 **Render Free**（一般 ¥0；闲置约 15 分钟后休眠，首次打开可能等 30–60 秒）。

---

## 你需要准备的

| 项目 | 说明 |
|------|------|
| GitHub 账号 | 已有即可 |
| Render 账号 | 已有即可，用 GitHub/Google 登录 |
| DashScope API Key | 本地 `.env` 里的 `LLM_API_KEY`（**不要**提交到 GitHub） |

---

## 第一步：把代码放到 GitHub

在本机项目目录执行（仓库名可改）：

```bash
cd ~/Desktop/forest-fire-false-alarm

# 若还没有正式 git 仓库：
rm -rf .git   # 仅当 .git 是残缺占位时需要
git init
git add .
git status    # 确认没有 .env
git commit -m "Deploy-ready ForestGuard with Render/Docker"

# 在 GitHub 网页新建空仓库 forest-fire-false-alarm（不要勾选 README）
# 然后（把 YOUR_GITHUB_USER 换成你的用户名）：
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USER/forest-fire-false-alarm.git
git push -u origin main
```

也可用 GitHub 网页：New repository → 按提示上传，但务必**不要**上传 `.env`。

---

## 第二步：在 Render 创建服务

1. 打开 [https://dashboard.render.com](https://dashboard.render.com)
2. **New +** → **Web Service**
3. **Connect** 你的 GitHub，选中 `forest-fire-false-alarm` 仓库  
   （首次需授权 Render 访问 GitHub）
4. 建议设置：
   - **Name**: `forestguard`（随意）
   - **Region**: `Singapore`（离国内/东南亚更近）
   - **Language / Runtime**: **Docker**
   - **Instance type**: **Free**
5. **Environment** 添加：

| Key | Value |
|-----|--------|
| `LLM_ENABLED` | `true` |
| `LLM_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | `qwen-vl-max` |
| `LLM_API_KEY` | 粘贴你的 Key（与本地 `.env` 相同） |

6. 点 **Create Web Service**，等待 Build / Deploy 变成 **Live**
7. 复制公网地址，例如：`https://forestguard-xxxx.onrender.com`

- 中文界面：`https://你的域名/`
- 英文界面：`https://你的域名/en`

---

## 第三步：发给别人试用

把链接发出去即可。你电脑关机不影响访问。

**演示建议**：优先上传**图片**；免费档内存约 512MB，大视频可能较慢或失败。

**冷启动**：若长时间没人访问，第一次打开可能要等将近一分钟，属正常现象。

---

## 可选：用 Blueprint 一键

若仓库里已有 `render.yaml`，也可在 Render 选 **New → Blueprint**，连接仓库后按提示填写 `LLM_API_KEY`。

---

## 安全注意

- `.env` 已在 `.gitignore` 中，**永远不要** push 到 GitHub
- API Key 只放在 Render 的 Environment Variables
- 若 Key 曾经泄露，到阿里云百炼控制台轮换新 Key

---

## 本地 Docker 自测（可选）

```bash
docker build -t forestguard .
docker run --rm -p 8000:8000 \
  -e LLM_ENABLED=true \
  -e LLM_API_KEY=你的密钥 \
  -e LLM_MODEL=qwen-vl-max \
  forestguard
```

浏览器打开 http://127.0.0.1:8000
