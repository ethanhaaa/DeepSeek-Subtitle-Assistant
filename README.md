# DeepSeek 字幕助手

一个基于 DeepSeek API 的 Windows 字幕翻译工具。

## 功能

- SRT 字幕翻译
- 保留原始字幕编号
- 保留原始时间轴
- 自动分批处理
- 字符数量控制
- 多请求并发
- API 请求失败自动重试
- 翻译进度显示
- 已用时间和预计剩余时间
- 自定义翻译 Prompt
- 支持自定义 DeepSeek 模型
- 自动检查字幕数量
- 自动检查编号
- 自动检查时间轴
- 自动生成新的 SRT 文件

## 使用方式

运行：

`DeepSeek字幕助手.exe`

然后：

1. 选择 SRT 文件
2. 选择翻译风格
3. 检查模型和参数
4. 点击「开始翻译」
5. 等待翻译完成

翻译完成后，会在原字幕所在目录生成：

`原文件名_DeepSeek结果.srt`

## API Key 配置

程序使用 `.env` 文件保存 DeepSeek API Key。

格式：

`DEEPSEEK_API_KEY=你的API Key`

`.env` 不应该上传到 GitHub。

## 项目结构

```text
DeepSeek字幕助手
├── deepseek_tool.py
├── requirements.txt
├── README.md
├── .gitignore
└── DeepSeek字幕助手.exe