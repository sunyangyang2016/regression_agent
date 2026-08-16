# RAG 知识库插件（`plugins/builtin/rag_plugin/`）

把本地文档（PDF / Word / TXT / Markdown / 代码）解析、分块、向量化后写入本地
知识库，供 Agent 对话中的 `rag_search` 工具检索。

## 结构（MVC，与 video_plugin 一致）

```
rag_plugin/
├── main.py                  # RagPlugin(BasePlugin) — 生命周期
├── bridge/rag_bridge.py     # RagBridge(QObject) — QWebChannel 控制器（JS ⇄ Python）
├── model/rag_service.py     # RagService — 业务逻辑（包装 rag/ 纯逻辑库）
├── config/rag_config.json   # 插件默认配置（只读；用户覆盖存 user_config/user/rag_config.json）
├── index.html               # 前端界面（body 片段，由 BasePlugin.get_config_ui 注入）
└── view/
    ├── css/rag.css          # 前端样式
    └── js/rag.js            # 前端逻辑（window.ragApp）
```

前端通过 `window.rag_bridge` 调用后端（app.js 中映射）；后端后台线程
（导入/统计/检索/下载）结果经 `execute_js` 推送 `window.ragApp.*` 回调。

## 使用

1. 启动主程序，打开「插件」面板 → **RAG 知识库** Tab。
2. 填写/选择文档目录（递归扫描）、集合名称、拆分方式，勾选跳过已处理/检测变更/
   代码结构化解析。
3. 点击 **开始导入**。首次导入自动下载 embedding 模型（约 100MB，走
   `hf-mirror.com` 镜像），日志会提示进度；可随时 **停止**。
4. 完成后可在「已处理文件记录」查看状态、重试失败项、导出 CSV、清空记录（清空会**同时删除全部向量库数据**，需确认）。
5. 「检索预览」可直接测试知识库检索效果。

## 数据目录（`user_config/rag/`）

| 路径 | 内容 |
| --- | --- |
| `vector_db/<向量数据库名>/` | 每个向量数据库一个独立 ChromaDB 目录 |
| `file_tracker.db` | SQLite 文件处理记录（去重/变更检测/失败重试） |
| `models/embedding/` | bge-base-zh-v1.5 ONNX 模型（768 维） |
| `models/rerank/` | bge-reranker-base ONNX 模型 |

## 与 Agent 集成

对话中使用 `rag_search` 内置工具查询知识库。导入插件与 Agent 共享同一数据目录
（`user_config/rag/`），导入的文档 Agent 立即可检索。

> 模型下载失败时：检查网络，或手动设置 `HF_ENDPOINT` 环境变量指向可用镜像，
> 在插件里点「补下载模型」即可重试下载（断点续传）。
