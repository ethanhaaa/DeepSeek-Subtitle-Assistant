import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from openai import OpenAI


# ============================================================
# 程序路径
# ============================================================

APP_DIR = Path.home() / "DeepSeek字幕助手"

APP_DIR.mkdir(
    parents=True,
    exist_ok=True
)

CONFIG_FILE = APP_DIR / "config.json"


# ============================================================
# 默认设置
# ============================================================

DEFAULT_MODEL = "deepseek-v4-flash"

DEFAULT_BATCH_SIZE = 50

DEFAULT_MAX_CHARS = 6000

DEFAULT_WORKERS = 3

DEFAULT_RETRIES = 3


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

client = None

processing = False

stop_event = threading.Event()

start_time = 0


# ============================================================
# 配置读取
# ============================================================

def load_config():

    if not CONFIG_FILE.exists():

        return {}

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {}


def save_config(api_key):

    data = {
        "api_key": api_key
    }

    with open(
        CONFIG_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def get_saved_api_key():

    config = load_config()

    return config.get(
        "api_key",
        ""
    )


# ============================================================
# DeepSeek 客户端
# ============================================================

def create_client(api_key):

    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )


# ============================================================
# API Key 测试
# ============================================================

def test_api_key(api_key):

    test_client = create_client(
        api_key
    )

    response = test_client.chat.completions.create(

        model=DEFAULT_MODEL,

        messages=[
            {
                "role": "user",
                "content": "Reply with OK."
            }
        ],

        max_tokens=10
    )

    return response


# ============================================================
# 首次设置 API Key
# ============================================================

def show_api_key_window(first_time=False):

    global client

    window = tk.Toplevel(root)

    window.title(
        "DeepSeek API Key"
    )

    window.geometry(
        "520x270"
    )

    window.resizable(
        False,
        False
    )

    window.transient(root)

    window.grab_set()


    title = tk.Label(

        window,

        text=(
            "首次使用，请设置 DeepSeek API Key"
            if first_time
            else
            "API Key 设置"
        ),

        font=(
            "Microsoft YaHei",
            15,
            "bold"
        )
    )

    title.pack(
        pady=(25, 10)
    )


    description = tk.Label(

        window,

        text=(
            "API Key 只保存在本机，不会上传到 GitHub。"
        ),

        font=(
            "Microsoft YaHei",
            9
        )
    )

    description.pack(
        pady=(0, 15)
    )


    frame = tk.Frame(
        window
    )

    frame.pack(
        padx=30,
        fill="x"
    )


    tk.Label(
        frame,
        text="API Key："
    ).pack(
        anchor="w"
    )


    key_entry = tk.Entry(
        frame,
        show="*",
        font=(
            "Consolas",
            10
        )
    )

    key_entry.pack(
        fill="x",
        pady=7
    )


    old_key = get_saved_api_key()

    if old_key:

        key_entry.insert(
            0,
            old_key
        )


    status = tk.Label(
        window,
        text="",
        anchor="w"
    )

    status.pack(
        padx=30,
        fill="x",
        pady=5
    )


    button_frame = tk.Frame(
        window
    )

    button_frame.pack(
        pady=12
    )


    def save():

        global client

        api_key = key_entry.get().strip()

        if not api_key:

            status.config(
                text="请输入 API Key。"
            )

            return


        status.config(
            text="正在测试 API Key……"
        )

        save_button.config(
            state="disabled"
        )


        def worker():

            global client

            try:

                test_api_key(
                    api_key
                )

                save_config(
                    api_key
                )

                client = create_client(
                    api_key
                )


                def success():

                    status.config(
                        text="连接成功，API Key 已保存。"
                    )

                    window.after(
                        800,
                        window.destroy
                    )


                window.after(
                    0,
                    success
                )


            except Exception as e:

                def fail():

                    status.config(
                        text=f"连接失败：{e}"
                    )

                    save_button.config(
                        state="normal"
                    )


                window.after(
                    0,
                    fail
                )


        threading.Thread(
            target=worker,
            daemon=True
        ).start()


    save_button = tk.Button(

        button_frame,

        text="测试并保存",

        width=14,

        command=save
    )

    save_button.pack(
        side="left",
        padx=5
    )


    def delete_key():

        global client

        if CONFIG_FILE.exists():

            CONFIG_FILE.unlink()

        client = None

        key_entry.delete(
            0,
            tk.END
        )

        status.config(
            text="API Key 已删除。"
        )


    delete_button = tk.Button(

        button_frame,

        text="删除 Key",

        width=10,

        command=delete_key
    )

    delete_button.pack(
        side="left",
        padx=5
    )


    window.protocol(
        "WM_DELETE_WINDOW",
        window.destroy
    )


# ============================================================
# 基础工具
# ============================================================

def format_time(seconds):

    if seconds is None or seconds < 0:

        return "--:--"

    seconds = int(seconds)

    hours = seconds // 3600

    minutes = (
        seconds % 3600
    ) // 60

    seconds = seconds % 60

    if hours:

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )

    return (
        f"{minutes:02d}:"
        f"{seconds:02d}"
    )


def safe_int(value, default):

    try:

        return int(value)

    except Exception:

        return default


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


def update_progress(
    done,
    total
):

    if total <= 0:

        return


    percent = (
        done / total * 100
    )


    elapsed = (
        time.time()
        - start_time
    )


    if done:

        total_estimated = (
            elapsed / done * total
        )

        remaining = (
            total_estimated
            - elapsed
        )

    else:

        remaining = None


    speed = (

        done / elapsed * 60

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
                f"已用时间："
                f"{format_time(elapsed)}    "
                f"预计剩余："
                f"{format_time(remaining)}"
            )
        )

        speed_label.config(
            text=(
                f"速度："
                f"{speed:.2f} 批/分钟"
            )
        )


    root.after(
        0,
        update
    )


# ============================================================
# 文件选择
# ============================================================

def choose_file():

    file_path = filedialog.askopenfilename(

        title="选择字幕文件",

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

        file_info_label.config(
            text=Path(
                file_path
            ).name
        )


# ============================================================
# SRT
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

        lines = block.split(
            "\n"
        )


        if len(lines) < 3:

            continue


        number = lines[0].strip()

        time_line = lines[1].strip()

        subtitle_text = "\n".join(
            lines[2:]
        ).strip()


        if not re.match(
            r"^\d+$",
            number
        ):

            continue


        if not re.match(
            r"\d{2}:\d{2}:\d{2}[,.]\d{3}"
            r"\s+-->\s+"
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
# 分批
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

        chars = len(
            subtitle["text"]
        )


        if current and (

            len(current)
            >= batch_size

            or

            current_chars
            + chars
            > max_chars

        ):

            batches.append(
                current
            )

            current = []

            current_chars = 0


        current.append(
            subtitle
        )

        current_chars += chars


    if current:

        batches.append(
            current
        )


    return batches


# ============================================================
# Prompt
# ============================================================

def build_prompt(
    batch,
    user_prompt
):

    lines = []

    for item in batch:

        lines.append(
            f"[{item['number']}] "
            f"{item['text']}"
        )


    source = "\n".join(
        lines
    )


    return f"""
{user_prompt}

本批字幕：

{source}

严格要求：

只输出翻译结果。

格式：

[原编号] 翻译后的字幕

不要输出时间轴。
不要输出 Markdown。
不要输出解释。
不要增加或删除字幕。
"""


# ============================================================
# 解析翻译
# ============================================================

def parse_translation(
    result,
    batch
):

    translated = {}

    current_number = None

    current_lines = []


    for line in result.splitlines():

        line = line.strip()


        if not line:

            continue


        match = re.match(
            r"^\[(\d+)\]\s*(.*)$",
            line
        )


        if match:

            if current_number is not None:

                translated[
                    current_number
                ] = "\n".join(
                    current_lines
                ).strip()


            current_number = (
                match.group(1)
            )

            current_lines = [
                match.group(2)
            ]


        elif current_number is not None:

            current_lines.append(
                line
            )


    if current_number is not None:

        translated[
            current_number
        ] = "\n".join(
            current_lines
        ).strip()


    result_list = []


    for item in batch:

        number = item["number"]


        if number not in translated:

            raise ValueError(
                f"缺少字幕编号：{number}"
            )


        result_list.append(
            {
                "number": number,
                "time": item["time"],
                "text": translated[number]
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
    prompt,
    retries
):

    global client


    if stop_event.is_set():

        raise InterruptedError()


    request_prompt = build_prompt(
        batch,
        prompt
    )


    last_error = None


    for attempt in range(
        1,
        retries + 1
    ):

        if stop_event.is_set():

            raise InterruptedError()


        try:

            response = client.chat.completions.create(

                model=model,

                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是专业影视字幕翻译员。"
                        )
                    },
                    {
                        "role": "user",
                        "content": request_prompt
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


            return parse_translation(
                result,
                batch
            )


        except Exception as e:

            last_error = e


            if attempt < retries:

                set_log(
                    f"第 {index} 批失败，"
                    f"正在重试 "
                    f"({attempt}/{retries})"
                )


                time.sleep(
                    min(
                        attempt * 2,
                        10
                    )
                )


    raise RuntimeError(
        f"第 {index} 批失败："
        f"{last_error}"
    )


# ============================================================
# SRT 生成
# ============================================================

def make_srt(results):

    blocks = []


    for item in results:

        blocks.append(

            f"{item['number']}\n"
            f"{item['time']}\n"
            f"{item['text']}"

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
            "字幕数量发生变化。"
        )


    for old, new in zip(
        original,
        translated
    ):

        if old["number"] != new["number"]:

            raise ValueError(
                f"编号错误："
                f"{old['number']}"
            )


        if old["time"] != new["time"]:

            raise ValueError(
                f"时间轴错误："
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
    prompt
):

    global start_time


    path = Path(
        file_path
    )


    text = path.read_text(
        encoding="utf-8-sig"
    )


    subtitles = parse_srt(
        text
    )


    if not subtitles:

        raise ValueError(
            "没有识别到有效字幕。"
        )


    set_log(
        f"识别到 {len(subtitles)} 条字幕"
    )


    batches = create_batches(

        subtitles,

        batch_size,

        max_chars
    )


    total = len(
        batches
    )


    set_log(
        f"共分成 {total} 批"
    )


    start_time = time.time()


    update_progress(
        0,
        total
    )


    results = [
        None
    ] * total


    completed = 0


    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:


        futures = {

            executor.submit(

                translate_batch,

                batch,

                i + 1,

                total,

                model,

                prompt,

                retries

            ): i

            for i, batch
            in enumerate(batches)

        }


        for future in as_completed(
            futures
        ):


            if stop_event.is_set():

                raise InterruptedError()


            index = futures[
                future
            ]


            result = future.result()


            results[
                index
            ] = result


            completed += 1


            set_log(
                f"第 {index + 1} / "
                f"{total} 批完成"
            )


            update_progress(
                completed,
                total
            )


    final_results = []


    for result in results:

        final_results.extend(
            result
        )


    verify_results(
        subtitles,
        final_results
    )


    output_file = path.with_name(

        path.stem
        + "_DeepSeek结果"
        + path.suffix

    )


    output_file.write_text(

        make_srt(
            final_results
        ),

        encoding="utf-8"

    )


    return output_file


# ============================================================
# 开始
# ============================================================

def start_process():

    global processing


    if processing:

        return


    global client


    if client is None:

        show_api_key_window(
            first_time=False
        )

        return


    file_path = file_entry.get().strip()


    if not file_path:

        messagebox.showwarning(
            "提示",
            "请先选择字幕文件。"
        )

        return


    if not Path(
        file_path
    ).exists():

        messagebox.showerror(
            "错误",
            "找不到文件。"
        )

        return


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


    prompt = prompt_text.get(
        "1.0",
        tk.END
    ).strip()


    if workers < 1 or workers > 10:

        messagebox.showerror(
            "错误",
            "并发请求必须为 1～10。"
        )

        return


    if batch_size < 1:

        messagebox.showerror(
            "错误",
            "每批字幕数量必须大于 0。"
        )

        return


    if max_chars < 100:

        messagebox.showerror(
            "错误",
            "最大字符数太小。"
        )

        return


    processing = True

    stop_event.clear()


    process_button.config(
        state="disabled"
    )

    stop_button.config(
        state="normal"
    )


    progress["value"] = 0


    progress_label.config(
        text="0 / 0 批    0%"
    )


    status_label.config(
        text="正在翻译……"
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


    def worker():

        global processing


        try:

            suffix = Path(
                file_path
            ).suffix.lower()


            if suffix != ".srt":

                raise ValueError(
                    "当前正式版主要用于 SRT 字幕。"
                )


            output_file = translate_srt(

                file_path,

                model,

                batch_size,

                max_chars,

                workers,

                retries,

                prompt

            )


            elapsed = (
                time.time()
                - start_time
            )


            set_status(
                "翻译完成"
            )


            set_log(
                "完整性检查通过"
            )


            set_log(
                f"总耗时："
                f"{format_time(elapsed)}"
            )


            root.after(

                0,

                lambda: messagebox.showinfo(

                    "完成",

                    "翻译完成！\n\n"
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
                lambda:
                process_button.config(
                    state="normal"
                )
            )


            root.after(
                0,
                lambda:
                stop_button.config(
                    state="disabled"
                )
            )


    threading.Thread(
        target=worker,
        daemon=True
    ).start()


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
        "正在停止，请等待当前请求结束……"
    )


    stop_button.config(
        state="disabled"
    )


# ============================================================
# Prompt
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
# GUI
# ============================================================

root = tk.Tk()

root.title(
    "DeepSeek 字幕助手 v1.1"
)

root.geometry(
    "900x850"
)

root.minsize(
    800,
    700
)


# ============================================================
# 菜单
# ============================================================

menu = tk.Menu(
    root
)

settings_menu = tk.Menu(
    menu,
    tearoff=0
)

settings_menu.add_command(
    label="API Key 设置",
    command=lambda:
    show_api_key_window(
        first_time=False
    )
)

menu.add_cascade(
    label="设置",
    menu=settings_menu
)

root.config(
    menu=menu
)


# ============================================================
# 标题
# ============================================================

tk.Label(

    root,

    text="DeepSeek 字幕助手",

    font=(
        "Microsoft YaHei",
        20,
        "bold"
    )

).pack(
    pady=(18, 12)
)


# ============================================================
# 文件
# ============================================================

file_frame = tk.LabelFrame(
    root,
    text="字幕文件",
    padx=12,
    pady=12
)

file_frame.pack(
    fill="x",
    padx=25
)


file_entry = tk.Entry(
    file_frame
)

file_entry.pack(
    side="left",
    fill="x",
    expand=True
)


tk.Button(
    file_frame,
    text="选择文件",
    width=12,
    command=choose_file
).pack(
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
# 设置
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
    column=3
)


tk.Label(
    settings_frame,
    text="最大字符："
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
    column=3
)


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
# Prompt
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
    command=lambda:
    set_prompt_style(
        "口语化"
    )
).pack(
    side="left",
    padx=3
)


tk.Button(
    prompt_buttons,
    text="准确翻译",
    command=lambda:
    set_prompt_style(
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
    state="disabled",
    command=stop_process
)

stop_button.pack(
    side="left",
    padx=8
)


# ============================================================
# 进度
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
    wrap="word"
)

log_text.pack(
    fill="both",
    expand=True
)


# ============================================================
# 启动
# ============================================================

saved_key = get_saved_api_key()


if saved_key:

    client = create_client(
        saved_key
    )

else:

    root.after(
        300,
        lambda:
        show_api_key_window(
            first_time=True
        )
    )


root.mainloop()