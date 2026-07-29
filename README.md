# 森林火灾烟火误报二次判别系统（可交付版）

实习课题原型：**OpenCV 传统分析 + 误报规则 + 多模态大模型二次判别 + Web 演示**。

安全原则：**宁可转人工复核，避免漏报真实火情**。

**定稿准确率：100%（38/38）** — 见 `docs/验收材料/最终批量测试_20260724_152606.xlsx`

---

## 交付入口

先看：[`docs/00_交付清单.md`](docs/00_交付清单.md)（按六阶段对照）

| 文档 | 路径 |
|------|------|
| 误报分类表 | `docs/01_误报分类表.md` / `.xlsx` |
| 测试报告 | `docs/02_测试报告.md` |
| 实习总结 | `docs/03_实习总结报告.md` |
| Prompt 说明 | `docs/04_多模态Prompt说明.md` |
| 最终批量结果 | `docs/验收材料/最终批量测试_20260724_152606.xlsx` |
| 迭代节点 N1–N6 | `docs/验收材料/迭代节点/` |

---

## 快速启动

```bash
cd ~/Desktop/forest-fire-false-alarm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置多模态：复制 .env.example 为 .env 并填写 Key
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器：http://127.0.0.1:8000 （默认英文）  

- 英文：`/` 或 `/en`  
- 中文：`/zh`  
- 源文件：英文在 `english_web/`，中文在 `app/templates`

### 公网部署（Render，无需本机常开）

见详细步骤：[`docs/DEPLOY_RENDER.md`](docs/DEPLOY_RENDER.md)

概要：代码推到 GitHub → Render 创建 **Free Web Service（Docker）** → 填写环境变量 `LLM_API_KEY` → 获得 `https://xxx.onrender.com`。

---

## 代码与数据

| 路径 | 说明 |
|------|------|
| `app/` | FastAPI、OpenCV、规则、多模态、融合、前端 |
| `config/rules.json` | 误报规则库 |
| `config/few_shot.json` | 多模态 few-shot |
| `scripts/` | 样本整理、OpenCV 试跑、批量评估、VL 联调 |
| `data/samples/` | 38 条分类样本（图+视频） |
| `data/labels/` | 仅样本标注表 |
| `docs/` | 验收文档与定稿/迭代测试结果 |

运行时上传与可视化目录：`data/uploads/`、`data/results/`（交付包中为空，运行后自动生成）。
