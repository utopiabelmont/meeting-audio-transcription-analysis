# 本地后端契约

## 仓库定位

本仓库发布的是 Codex Skill 适配层。它不会重新实现 ASR、Forced Alignment、pyannote、说话人合并或字幕生成算法。

兼容后端必须提供：

- `app/run_pipeline_complete.py`
- `app/generate_vtt.py`
- `app/config/transcript_cleaning_base.json`
- 可选的 `app/config/glossaries/optical_edge_ml.json`
- `app/jobs` 输出根目录
- pyannote 环境 Python
- Qwen3-ASR 环境及其既有调用逻辑
- ffprobe

## 已验证的不变设置

Skill 包装器继续向后端传递：

| 设置 | 值 |
| --- | --- |
| language | `auto` |
| language strategy | `per-chunk` |
| chunk duration | `180` 秒 |
| chunk overlap | `12` 秒 |
| keep chunks | 启用 |
| speaker naming | 匿名 |
| text cleaning | 启用 |
| technical review | 启用 |

本发布工作没有修改模型、GPU、说话人合并或时间戳去重算法。

## 本机配置

安装目录可以包含不入库的 `local_backend.json`。最简单的配置只填写后端根目录：

```json
{
  "project_root": "请填写本机后端根目录"
}
```

也可分别配置：

```json
{
  "app_dir": "请填写本机app目录",
  "pyannote_python": "请填写pyannote环境的python.exe",
  "ffprobe": "请填写ffprobe.exe"
}
```

发布包中的 `config/local_backend.example.json` 保持空值，避免泄露或误用作者机器路径。推荐直接使用安装脚本生成有效配置，不要把上面的说明文字当作真实路径。

## 路径解析

优先级为：

1. `VTT_PLUS_APP_DIR`、`VTT_PLUS_PYANNOTE_PYTHON`、`VTT_PLUS_FFPROBE` 等专用环境变量；
2. `local_backend.json` 的对应字段；
3. 从 `VTT_PLUS_ANALYSIS_ROOT` 或配置中的 `project_root` 推导。

最终解析路径及来源会写入 `meeting_skill_run.json` 的 `backend_paths`，并记录在控制台日志中。

## 输出和隐私

Job 目录可能包含原始文件哈希、绝对输入路径、完整转录、会议上下文、说话人标签和日志。它们属于运行数据，不是 Skill 源码，不应发布到 GitHub。

## 兼容性边界

本仓库当前只验证了既有 Windows 本地后端。若后端目录结构、命令行参数或输出契约发生变化，应先更新兼容层和单元测试，再发布新版本。不要通过猜测路径或静默忽略缺失文件来“兼容”未知后端。
