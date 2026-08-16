# user_config/rag/ — RAG 数据目录

导入插件与 Agent 检索模块共享的数据目录（不入版本库，本 README 除外）。

| 路径 | 说明 | 写入方 | 读取方 |
|---|---|---|---|
| `vector_db/<向量数据库名>/` | 每个向量数据库一个独立 ChromaDB 目录（768 维，cosine），集合按库隔离 | 导入插件 | 插件 + Agent |
| `file_tracker.db` | SQLite 文件处理记录 | 导入插件 | 仅插件（Agent 不访问） |
| `models/embedding/` | Embedding 模型缓存（Xenova/bge-base-zh-v1.5） | 首次使用时自动下载 | 插件 + Agent |
| `models/rerank/` | 重排模型缓存（Xenova/bge-reranker-base） | 首次使用时自动下载 | Agent |

## 说明

- 配置：默认配置见 `plugins/builtin/rag_plugin/config/rag_config.json`（只读）；
  用户自定义覆盖写入 `user_config/user/rag_config.json`（优先读取，缺失回退默认）。
- 模型下载支持 HuggingFace 镜像（配置 `models.*.mirror`，默认 `https://hf-mirror.com`）。
- 导入插件：主界面「插件」面板中的 **RAG 知识库** Tab（`plugins/builtin/rag_plugin/`）。
- Agent 检索入口：`from rag_mcp_server.rag_client import RAGClient`（位于 `tools/mcp/server/rag-mcp-server/`）。
