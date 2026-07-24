# GitHub 仓库布局

建议新仓库使用以下结构。把本发布目录的内容整体作为仓库根目录上传，不要再套一层同名目录。

```text
meeting-audio-transcription-analysis/
├── .github/
│   └── workflows/
│       └── validate.yml
├── config/
│   └── local_backend.example.json
├── docs/
│   ├── BACKEND.zh-CN.md
│   ├── INSTALL.zh-CN.md
│   ├── REPOSITORY_LAYOUT.zh-CN.md
│   └── USAGE.zh-CN.md
├── scripts/
│   ├── build_package.ps1
│   ├── install.ps1
│   ├── uninstall.ps1
│   └── validate_release.py
├── skills/
│   └── meeting-audio-transcription-analysis/
│       ├── SKILL.md
│       ├── INSTALL.md
│       ├── LICENSE
│       ├── agents/
│       │   └── openai.yaml
│       ├── assets/
│       │   └── templates/
│       │       ├── meeting_analysis_template.md
│       │       └── meeting_timeline_template.md
│       ├── references/
│       │   ├── examples/
│       │   │   ├── general_meeting.md
│       │   │   └── optical_research_meeting.md
│       │   ├── backend.md
│       │   ├── input_contract.md
│       │   ├── meeting_analysis.schema.json
│       │   ├── meeting_source_index.schema.json
│       │   ├── output_schema.md
│       │   └── quality_rules.md
│       ├── scripts/
│       │   ├── analyze_transcript.py
│       │   ├── run_meeting_skill.py
│       │   └── validate_skill_outputs.py
│       └── tests/
│           ├── __init__.py
│           ├── test_analyze_transcript.py
│           ├── test_run_meeting_skill.py
│           └── test_validate_skill_outputs.py
├── .gitignore
├── LICENSE
├── README.md
└── VERSION
```

## 每类文件放在哪里

| 文件或目录 | GitHub 位置 | 用途 |
| --- | --- | --- |
| `README.md` | 仓库根目录 | 项目主页、安装入口、用法和风险 |
| `LICENSE` | 仓库根目录及 Skill 子目录 | MIT 许可文本；确保仓库和独立 Skill 包均携带许可 |
| `VERSION` | 仓库根目录 | 发布版本 |
| `.gitignore` | 仓库根目录 | 防止本地配置、录音、Job、日志、模型进入提交 |
| `validate.yml` | `.github/workflows/` | GitHub Actions 纯静态和单元测试 |
| `local_backend.example.json` | `config/` | 空值配置模板，不包含本机路径 |
| 中文文档 | `docs/` | 安装、使用、后端边界和文件地图 |
| 发布脚本 | 根目录 `scripts/` | 安装、卸载、验证和打包 |
| 完整 Skill | `skills/meeting-audio-transcription-analysis/` | Codex 可安装目录 |

## 不得上传

- 安装目录中的 `local_backend.json`
- `.env`、令牌、私钥和授权缓存
- `conda`、`.venv`、模型和下载缓存
- `app/jobs`、chunks、日志和流水线状态
- WAV、MP3、M4A、MP4 等用户录音
- 转录、分析、VTT、TXT 等任务产物
- `__pycache__`、`.pyc`
- `dist` 和本地生成的 ZIP

## GitHub 创建建议

建议在 `utopiabelmont` 账号下创建空仓库：

```text
utopiabelmont/meeting-audio-transcription-analysis
```

仓库已选择 MIT License。发布时必须保留根目录和 Skill 子目录中的 `LICENSE`。

创建空仓库后，把本发布目录中的所有文件上传到仓库根目录。若以后交给 Codex 直接推送，应明确提供这个仓库的 URL 或 `owner/repo`，避免误写入其他已有仓库。
