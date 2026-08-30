import os
import re
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# 读取 API Key
# ============================================================

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not API_KEY:
    messagebox.showerror(
        "API Key 错误",
        "没有找到 DEEPSEEK_API_KEY。\n\n"
        "请检查项目文件夹里的 .env 文件。"
    )
    raise SystemExit


# ============================================================
# DeepSeek API
# ============================================================

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com"
)


# ============================================================
# 默认设置
# ============================================================

DEFAULT_MODEL = "deepseek-v4-flash"

DEFAULT_BATCH_SIZE = 50

DEFAULT_MAX_CHARS = 6000

DEFAULT_WORKERS = 3

DEFAULT_RETRIES = 3


# ============================================================
# 默认 Prompt
# ============================================================

DEFAULT_PROMPT = """你是一名专业的影视字幕翻译员。

请将英文对白翻译成自然、地道、口语化的中文。

翻译要求：

1. 每个 [编号] 都必须保留。
2. 不得修改、删除或增加编号。
3. 不得合并字幕。
4. 不得拆分字幕。
5. 保持字幕原来的顺序。
6. 只翻译字幕文字。
7. 不要翻译 [编号]。
8. 使用自然、符合中文母语者说话习惯的表达。
9. 避免机械直译和明显的翻译腔。
10. 根据上下文判断人物关系、语气和情绪。
11. 日常对白优先使用自然口语。
12. 保留原文的语气、情绪和表达强度。
13. 不要自行增加原文不存在的信息。
14. 不要解释翻译过程。
15. 不要输出任何额外说明。

严格按照下面格式输出：

[编号] 翻译后的字幕

例如：

输入：
[15] Are you serious?
[16] I don't know.

输出：
[15] 你认真的吗？
[16] 我不知道。

只输出翻译结果。"""


# ============================================================
# 全局状态
# ============================================================

stop_event = threading.Event()

processing = False

start_time = 0

completed_batches = 0

total_batches = 0

current_file = None


# ============================================================
# 工具函数
# ============================================================

def safe_int(value, default):

    try:
        return int(value)

    except Exception:

        return default


def format_time(seconds):

    if seconds is None or seconds < 0:
        return "--:--"

    seconds = int(seconds)

    hours = seconds // 3600

    minutes = (seconds % 3600) // 60

    seconds = seconds % 60

    if hours > 0:

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


# ============================================================
# GUI 更新
# ============================================================

def set_status(text):

    root.after(
        0,
        lambda: status_label.config(
            text=text
        )
    )


def set_log(text):

    def update():

        log_text.config(
            state="normal"
        )

        log_text.insert(
            tk.END,
            text + "\n"
        )

        log_text.see(
            tk.END
        )

        log_text.config(
            state="disabled"
        )

    root.after(
        0,
        update
    )


def update_progress(done, total):

    global completed_batches

    completed_batches = done

    if total <= 0:
        return

    percent = done / total * 100

    elapsed = time.time() - start_time

    if done > 0:

        estimated_total = (
            elapsed / done * total
        )

        remaining = (
            estimated_total - elapsed
        )

    else:

        remaining = None

    speed = (
        done / elapsed
        if elapsed > 0
        else 0
    )

    def update():

        progress["value"] = percent

        progress_label.config(
            text=(
                f"{done} / {total} 批    "
                f"{percent:.1f}%"
            )
        )

        time_label.config(
            text=(
                f"已用时间：{format_time(elapsed)}    "
                f"预计剩余：{format_time(remaining)}"
            )
        )

        speed_label.config(
            text=f"速度：{speed:.2f} 批/分钟"
        )

    root.after(
        0,
        update
    )


# ============================================================
# 选择文件
# ============================================================

def choose_file():

    file_path = filedialog.askopenfilename(

        title="选择文件",

        filetypes=[
            ("SRT 字幕", "*.srt"),
            ("TXT 文本", "*.txt"),
            ("所有文件", "*.*")
        ]
    )

    if file_path:

        file_entry.delete(
            0,
            tk.END
        )

        file_entry.insert(
            0,
            file_path
        )

        path = Path(file_path)

        file_info_label.config(
            text=(
                f"文件：{path.name}"
            )
        )


# ============================================================
# SRT 解析
# ============================================================

def parse_srt(text):

    text = text.replace(
        "\r\n",
        "\n"
    )

    text = text.replace(
        "\r",
        "\n"
    )

    blocks = re.split(
        r"\n\s*\n",
        text.strip()
    )

    subtitles = []

    for block in blocks:

        lines = block.split("\n")

        if len(lines) < 3:
            continue

        number = lines[0].strip()

        time_line = lines[1].strip()

        subtitle_text = "\n".join(
            lines[2:]
        ).strip()

        if not re.match(
            r"^\d+\s*$",
            number
        ):
            continue

        if not re.match(
            r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
            r"\d{2}:\d{2}:\d{2}[,.]\d{3}",
            time_line
        ):
            continue

        subtitles.append(
            {
                "number": number,
                "time": time_line,
                "text": subtitle_text
            }
        )

    return subtitles


# ============================================================
# 创建批次
# ============================================================

def create_batches(
    subtitles,
    batch_size,
    max_chars
):

    batches = []

    current = []

    current_chars = 0

    for subtitle in subtitles:

        text = subtitle["text"]

        # 每条字幕本身就超过字符限制
        # 仍然单独作为一批
        text_chars = len(text)

        should_split = (

            current

            and (

                len(current) >= batch_size

                or
                current_chars + text_chars
                > max_chars

            )
        )

        if should_split:

            batches.append(
                current
            )

            current = []

            current_chars = 0


        current.append(
            subtitle
        )

        current_chars += text_chars


    if current:

        batches.append(
            current
        )


    return batches


# ============================================================
# 构造 DeepSeek 请求
# ============================================================

def build_prompt(
    batch,
    user_prompt
):

    lines = []

    for item in batch:

        lines.append(
            f"[{item['number']}] {item['text']}"
        )

    source = "\n".join(
        lines
    )

    return f"""
{user_prompt}

本批字幕只包含以下内容：

{source}

再次强调：

只输出翻译结果。

每一条必须保持：

[原编号] 翻译后的字幕

不要输出时间轴。
不要输出 Markdown。
不要输出解释。
"""


# ============================================================
# 解析 DeepSeek 返回结果
# ============================================================

def parse_translation(
    result,
    batch
):

    translated = {}

    current_number = None

    current_lines = []


    lines = result.splitlines()


    for line in lines:

        line = line.strip()

        if not line:
            continue


        match = re.match(
            r"^\[(\d+)\]\s*(.*)$",
            line
        )


        if match:

            # 保存上一条
            if current_number is not None:

                translated[
                    current_number
                ] = "\n".join(
                    current_lines
                ).strip()


            current_number = match.group(
                1
            )

            current_lines = [
                match.group(2)
            ]


        else:

            if current_number is not None:

                current_lines.append(
                    line
                )


    # 最后一条
    if current_number is not None:

        translated[
            current_number
        ] = "\n".join(
            current_lines
        ).strip()


    expected = [
        item["number"]
        for item in batch
    ]


    missing = []

    for number in expected:

        if number not in translated:

            missing.append(
                number
            )


    if missing:

        raise ValueError(
            "返回结果缺少字幕编号："
            + ", ".join(missing)
        )


    result_list = []

    for item in batch:

        result_list.append(
            {
                "number": item["number"],

                "time": item["time"],

                "text": translated[
                    item["number"]
                ]
            }
        )


    return result_list


# ============================================================
# 单批翻译
# ============================================================

def translate_batch(
    batch,
    index,
    total,
    model,
    user_prompt,
    retries
):

    if stop_event.is_set():

        raise InterruptedError(
            "用户停止了任务"
        )


    prompt = build_prompt(
        batch,
        user_prompt
    )


    last_error = None


    for attempt in range(
        1,
        retries + 1
    ):

        if stop_event.is_set():

            raise InterruptedError(
                "用户停止了任务"
            )


        try:

            response = client.chat.completions.create(

                model=model,

                messages=[

                    {
                        "role": "system",
                        "content": (
                            "你是专业影视字幕翻译员。"
                            "严格遵守用户要求。"
                        )
                    },

                    {
                        "role": "user",
                        "content": prompt
                    }

                ],

                temperature=0.3

            )


            result = (
                response
                .choices[0]
                .message
                .content
                .strip()
            )


            parsed = parse_translation(
                result,
                batch
            )


            return parsed


        except Exception as e:

            last_error = e

            if attempt < retries:

                set_log(
                    f"第 {index} 批失败，"
                    f"{attempt}/{retries}，"
                    f"正在重试……"
                )

                time.sleep(
                    min(
                        2 * attempt,
                        10
                    )
                )


    raise RuntimeError(
        f"第 {index} 批最终失败："
        f"{last_error}"
    )


# ============================================================
# 生成 SRT
# ============================================================

def make_srt(results):

    blocks = []

    for item in results:

        block = (
            f"{item['number']}\n"
            f"{item['time']}\n"
            f"{item['text']}"
        )

        blocks.append(
            block
        )


    return (
        "\n\n".join(
            blocks
        )
        + "\n"
    )


# ============================================================
# 完整性检查
# ============================================================

def verify_results(
    original,
    translated
):

    if len(original) != len(translated):

        raise ValueError(
            f"字幕数量不一致。\n"
            f"原始：{len(original)}\n"
            f"结果：{len(translated)}"
        )


    for old, new in zip(
        original,
        translated
    ):

        if old["number"] != new["number"]:

            raise ValueError(
                f"字幕编号发生变化："
                f"{old['number']} → {new['number']}"
            )


        if old["time"] != new["time"]:

            raise ValueError(
                f"字幕时间轴发生变化："
                f"{old['number']}"
            )


        if not new["text"].strip():

            raise ValueError(
                f"字幕 {old['number']} "
                f"翻译结果为空。"
            )


# ============================================================
# SRT 翻译
# ============================================================

def translate_srt(
    file_path,
    model,
    batch_size,
    max_chars,
    workers,
    retries,
    user_prompt
):

    global total_batches
    global start_time


    path = Path(
        file_path
    )


    # --------------------------------------------------------
    # 读取
    # --------------------------------------------------------

    set_status(
        "正在读取 SRT……"
    )

    set_log(
        f"读取：{path.name}"
    )


    text = path.read_text(
        encoding="utf-8-sig"
    )


    subtitles = parse_srt(
        text
    )


    if not subtitles:

        raise ValueError(
            "没有识别到有效的 SRT 字幕。"
        )


    set_log(
        f"识别到 {len(subtitles)} 条字幕"
    )


    # --------------------------------------------------------
    # 分批
    # --------------------------------------------------------

    batches = create_batches(

        subtitles,

        batch_size,

        max_chars

    )


    total_batches = len(
        batches
    )


    set_log(
        f"共分成 {total_batches} 批"
    )


    set_status(
        "正在翻译……"
    )


    # --------------------------------------------------------
    # 开始计时
    # --------------------------------------------------------

    start_time = time.time()


    update_progress(
        0,
        total_batches
    )


    # --------------------------------------------------------
    # 保存结果
    # --------------------------------------------------------

    all_results = [
        None
    ] * total_batches


    completed = 0


    # --------------------------------------------------------
    # 并发
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:


        future_map = {

            executor.submit(

                translate_batch,

                batch,

                index + 1,

                total_batches,

                model,

                user_prompt,

                retries

            ): index

            for index, batch
            in enumerate(batches)

        }


        for future in as_completed(
            future_map
        ):

            if stop_event.is_set():

                for f in future_map:

                    f.cancel()

                raise InterruptedError(
                    "任务已停止。"
                )


            index = future_map[
                future
            ]


            try:

                result = future.result()

                all_results[
                    index
                ] = result


                completed += 1


                set_log(
                    f"第 {index + 1} / "
                    f"{total_batches} 批完成"
                )


                update_progress(
                    completed,
                    total_batches
                )


            except Exception as e:

                # 发生失败时取消剩余任务
                for f in future_map:

                    f.cancel()


                raise e


    # --------------------------------------------------------
    # 合并
    # --------------------------------------------------------

    set_status(
        "正在检查字幕完整性……"
    )


    final_results = []


    for batch_result in all_results:

        final_results.extend(
            batch_result
        )


    # --------------------------------------------------------
    # 检查
    # --------------------------------------------------------

    verify_results(
        subtitles,
        final_results
    )


    set_log(
        "编号检查通过"
    )

    set_log(
        "时间轴检查通过"
    )

    set_log(
        "字幕数量检查通过"
    )


    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------

    set_status(
        "正在保存文件……"
    )


    output_file = path.with_name(
        path.stem
        + "_DeepSeek结果"
        + path.suffix
    )


    final_text = make_srt(
        final_results
    )


    output_file.write_text(
        final_text,
        encoding="utf-8"
    )


    elapsed = time.time() - start_time


    set_log(
        f"完成，总耗时：{format_time(elapsed)}"
    )


    return output_file


# ============================================================
# TXT 处理
# ============================================================

def process_txt(
    file_path,
    model,
    user_prompt
):

    path = Path(
        file_path
    )


    set_status(
        "正在读取 TXT……"
    )


    text = path.read_text(
        encoding="utf-8-sig"
    )


    set_status(
        "DeepSeek 正在处理……"
    )


    response = client.chat.completions.create(

        model=model,

        messages=[

            {
                "role": "system",
                "content": (
                    "你是专业的文本处理助手。"
                )
            },

            {
                "role": "user",
                "content": (
                    user_prompt
                    + "\n\n原始文本：\n\n"
                    + text
                )
            }

        ],

        temperature=0.3
    )


    result = (
        response
        .choices[0]
        .message
        .content
    )


    output_file = path.with_name(
        path.stem
        + "_DeepSeek结果"
        + path.suffix
    )


    output_file.write_text(
        result,
        encoding="utf-8"
    )


    return output_file


# ============================================================
# 后台工作线程
# ============================================================

def worker():

    global processing


    try:

        file_path = file_entry.get().strip()


        model = model_entry.get().strip()


        batch_size = safe_int(
            batch_size_entry.get(),
            DEFAULT_BATCH_SIZE
        )


        max_chars = safe_int(
            max_chars_entry.get(),
            DEFAULT_MAX_CHARS
        )


        workers = safe_int(
            workers_entry.get(),
            DEFAULT_WORKERS
        )


        retries = safe_int(
            retries_entry.get(),
            DEFAULT_RETRIES
        )


        user_prompt = prompt_text.get(
            "1.0",
            tk.END
        ).strip()


        if not file_path:

            raise ValueError(
                "请先选择文件。"
            )


        if not Path(
            file_path
        ).exists():

            raise ValueError(
                "找不到所选择的文件。"
            )


        if not model:

            raise ValueError(
                "模型不能为空。"
            )


        if batch_size < 1:

            raise ValueError(
                "每批字幕数量必须大于 0。"
            )


        if max_chars < 100:

            raise ValueError(
                "每批最大字符数太小。"
            )


        if workers < 1 or workers > 10:

            raise ValueError(
                "并发数只能设置为 1～10。"
            )


        if retries < 1:

            raise ValueError(
                "重试次数必须至少为 1。"
            )


        suffix = Path(
            file_path
        ).suffix.lower()


        # ====================================================
        # SRT
        # ====================================================

        if suffix == ".srt":

            output_file = translate_srt(

                file_path,

                model,

                batch_size,

                max_chars,

                workers,

                retries,

                user_prompt

            )


        # ====================================================
        # TXT
        # ====================================================

        elif suffix == ".txt":

            output_file = process_txt(

                file_path,

                model,

                user_prompt

            )


        else:

            raise ValueError(
                "目前只支持 .srt 和 .txt 文件。"
            )


        set_status(
            "处理完成"
        )


        root.after(
            0,
            lambda: messagebox.showinfo(
                "完成",
                "处理完成！\n\n"
                f"结果文件：\n"
                f"{output_file}"
            )
        )


    except InterruptedError:

        set_status(
            "已停止"
        )

        set_log(
            "任务已停止。"
        )


        root.after(
            0,
            lambda: messagebox.showinfo(
                "已停止",
                "翻译任务已经停止。"
            )
        )


    except Exception as e:

        set_status(
            "处理失败"
        )


        set_log(
            f"错误：{e}"
        )


        root.after(
            0,
            lambda: messagebox.showerror(
                "处理失败",
                str(e)
            )
        )


    finally:

        processing = False


        root.after(
            0,
            lambda: process_button.config(
                state="normal"
            )
        )

        root.after(
            0,
            lambda: stop_button.config(
                state="disabled"
            )
        )


# ============================================================
# 开始
# ============================================================

def start_process():

    global processing

    if processing:

        return


    stop_event.clear()

    processing = True


    progress["value"] = 0


    progress_label.config(
        text="0 / 0 批    0%"
    )


    time_label.config(
        text="已用时间：00:00    预计剩余：--:--"
    )


    speed_label.config(
        text="速度：0.00 批/分钟"
    )


    log_text.config(
        state="normal"
    )

    log_text.delete(
        "1.0",
        tk.END
    )

    log_text.config(
        state="disabled"
    )


    process_button.config(
        state="disabled"
    )


    stop_button.config(
        state="normal"
    )


    thread = threading.Thread(
        target=worker,
        daemon=True
    )


    thread.start()


# ============================================================
# 停止
# ============================================================

def stop_process():

    if not processing:

        return


    stop_event.set()


    set_status(
        "正在停止……"
    )


    set_log(
        "正在停止任务，请等待当前请求结束……"
    )


    stop_button.config(
        state="disabled"
    )


# ============================================================
# 恢复默认 Prompt
# ============================================================

def reset_prompt():

    prompt_text.delete(
        "1.0",
        tk.END
    )

    prompt_text.insert(
        "1.0",
        DEFAULT_PROMPT
    )


# ============================================================
# 快速 Prompt
# ============================================================

def set_prompt_style(style):

    if style == "口语化":

        text = """你是一名专业的影视字幕翻译员。

请将英文对白翻译成自然、地道、口语化的中文。

要求：
1. 不要逐字直译。
2. 使用真实中文日常对话中的表达。
3. 根据上下文判断语气、关系和情绪。
4. 避免书面语和翻译腔。
5. 简短对白保持简洁。
6. 保留原文的情绪和表达强度。
7. 不添加原文不存在的信息。
8. 保留所有 [编号]。
9. 只输出 [编号] + 翻译结果。
10. 不要输出解释。"""


    elif style == "准确":

        text = """你是一名专业字幕翻译员。

请准确翻译英文字幕。

要求：
1. 准确传达原意。
2. 不添加原文不存在的信息。
3. 不删除原文信息。
4. 保持人物语气。
5. 中文自然，但以准确性优先。
6. 保留所有 [编号]。
7. 只输出 [编号] + 翻译结果。
8. 不要输出解释。"""


    else:

        text = DEFAULT_PROMPT


    prompt_text.delete(
        "1.0",
        tk.END
    )

    prompt_text.insert(
        "1.0",
        text
    )


# ============================================================
# GUI
# ============================================================

root = tk.Tk()

root.title(
    "DeepSeek 字幕助手"
)

root.geometry(
    "900x850"
)

root.minsize(
    800,
    700
)


# ============================================================
# 标题
# ============================================================

title_label = tk.Label(
    root,
    text="DeepSeek 字幕助手",
    font=(
        "Microsoft YaHei",
        20,
        "bold"
    )
)

title_label.pack(
    pady=(18, 12)
)


# ============================================================
# 文件区域
# ============================================================

file_frame = tk.LabelFrame(
    root,
    text="文件",
    padx=12,
    pady=12
)

file_frame.pack(
    fill="x",
    padx=25
)


file_entry = tk.Entry(
    file_frame,
    font=(
        "Microsoft YaHei",
        10
    )
)

file_entry.pack(
    side="left",
    fill="x",
    expand=True
)


file_button = tk.Button(
    file_frame,
    text="选择文件",
    width=12,
    command=choose_file
)

file_button.pack(
    side="left",
    padx=(10, 0)
)


file_info_label = tk.Label(
    file_frame,
    text="未选择文件",
    anchor="w"
)

file_info_label.pack(
    fill="x",
    pady=(8, 0)
)


# ============================================================
# 参数区域
# ============================================================

settings_frame = tk.LabelFrame(
    root,
    text="翻译设置",
    padx=12,
    pady=12
)

settings_frame.pack(
    fill="x",
    padx=25,
    pady=12
)


# 模型

tk.Label(
    settings_frame,
    text="模型："
).grid(
    row=0,
    column=0,
    sticky="w",
    padx=5,
    pady=5
)


model_entry = tk.Entry(
    settings_frame,
    width=30
)

model_entry.insert(
    0,
    DEFAULT_MODEL
)

model_entry.grid(
    row=0,
    column=1,
    sticky="w",
    padx=5
)


# 每批字幕

tk.Label(
    settings_frame,
    text="每批字幕："
).grid(
    row=0,
    column=2,
    sticky="w",
    padx=(25, 5)
)


batch_size_entry = tk.Entry(
    settings_frame,
    width=10
)

batch_size_entry.insert(
    0,
    str(DEFAULT_BATCH_SIZE)
)

batch_size_entry.grid(
    row=0,
    column=3,
    sticky="w",
    padx=5
)


# 最大字符

tk.Label(
    settings_frame,
    text="每批最大字符："
).grid(
    row=1,
    column=0,
    sticky="w",
    padx=5,
    pady=5
)


max_chars_entry = tk.Entry(
    settings_frame,
    width=15
)

max_chars_entry.insert(
    0,
    str(DEFAULT_MAX_CHARS)
)

max_chars_entry.grid(
    row=1,
    column=1,
    sticky="w",
    padx=5
)


# 并发

tk.Label(
    settings_frame,
    text="并发请求："
).grid(
    row=1,
    column=2,
    sticky="w",
    padx=(25, 5)
)


workers_entry = tk.Entry(
    settings_frame,
    width=10
)

workers_entry.insert(
    0,
    str(DEFAULT_WORKERS)
)

workers_entry.grid(
    row=1,
    column=3,
    sticky="w",
    padx=5
)


# 重试

tk.Label(
    settings_frame,
    text="失败重试："
).grid(
    row=2,
    column=0,
    sticky="w",
    padx=5,
    pady=5
)


retries_entry = tk.Entry(
    settings_frame,
    width=10
)

retries_entry.insert(
    0,
    str(DEFAULT_RETRIES)
)

retries_entry.grid(
    row=2,
    column=1,
    sticky="w",
    padx=5
)


# ============================================================
# Prompt 区域
# ============================================================

prompt_frame = tk.LabelFrame(
    root,
    text="翻译 Prompt",
    padx=12,
    pady=12
)

prompt_frame.pack(
    fill="both",
    expand=True,
    padx=25
)


# 快速按钮

prompt_buttons = tk.Frame(
    prompt_frame
)

prompt_buttons.pack(
    fill="x",
    pady=(0, 8)
)


tk.Button(
    prompt_buttons,
    text="自然口语化",
    command=lambda: set_prompt_style(
        "口语化"
    )
).pack(
    side="left",
    padx=3
)


tk.Button(
    prompt_buttons,
    text="准确翻译",
    command=lambda: set_prompt_style(
        "准确"
    )
).pack(
    side="left",
    padx=3
)


tk.Button(
    prompt_buttons,
    text="恢复默认",
    command=reset_prompt
).pack(
    side="left",
    padx=3
)


prompt_text = tk.Text(
    prompt_frame,
    height=12,
    wrap="word",
    font=(
        "Microsoft YaHei",
        10
    )
)

prompt_text.pack(
    fill="both",
    expand=True
)


prompt_text.insert(
    "1.0",
    DEFAULT_PROMPT
)


# ============================================================
# 操作按钮
# ============================================================

button_frame = tk.Frame(
    root
)

button_frame.pack(
    pady=12
)


process_button = tk.Button(
    button_frame,
    text="开始翻译",
    width=18,
    height=2,
    font=(
        "Microsoft YaHei",
        11
    ),
    command=start_process
)

process_button.pack(
    side="left",
    padx=8
)


stop_button = tk.Button(
    button_frame,
    text="停止",
    width=12,
    height=2,
    font=(
        "Microsoft YaHei",
        11
    ),
    state="disabled",
    command=stop_process
)

stop_button.pack(
    side="left",
    padx=8
)


# ============================================================
# 进度区域
# ============================================================

progress_frame = tk.LabelFrame(
    root,
    text="进度",
    padx=12,
    pady=12
)

progress_frame.pack(
    fill="x",
    padx=25
)


status_label = tk.Label(
    progress_frame,
    text="等待处理",
    anchor="w"
)

status_label.pack(
    fill="x"
)


progress = ttk.Progressbar(
    progress_frame,
    orient="horizontal",
    mode="determinate"
)

progress.pack(
    fill="x",
    pady=8
)


progress_label = tk.Label(
    progress_frame,
    text="0 / 0 批    0%"
)

progress_label.pack()


time_label = tk.Label(
    progress_frame,
    text="已用时间：00:00    预计剩余：--:--"
)

time_label.pack(
    pady=(5, 0)
)


speed_label = tk.Label(
    progress_frame,
    text="速度：0.00 批/分钟"
)

speed_label.pack(
    pady=(3, 0)
)


# ============================================================
# 日志
# ============================================================

log_frame = tk.LabelFrame(
    root,
    text="运行日志",
    padx=8,
    pady=8
)

log_frame.pack(
    fill="both",
    expand=True,
    padx=25,
    pady=(12, 20)
)


log_text = tk.Text(
    log_frame,
    height=7,
    state="disabled",
    wrap="word",
    font=(
        "Consolas",
        9
    )
)

log_text.pack(
    fill="both",
    expand=True
)


# ============================================================
# 启动
# ============================================================

root.mainloop()