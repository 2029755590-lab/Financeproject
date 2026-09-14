import zipfile
from pathlib import Path

from docx import Document

from app.core.logger import node_log, step_log
from app.import_process.agent.state import ImportGraphState
from app.utils.task_utils import add_running_task
from app.core.logger import logger

IMAGES_DIR_NAME = "images"

# 校验docx路径与输出目录
@step_log("step_1_validate_docx")
def step_1_validate_docx(state):
    # 校验docx路径与输出目录
    docx_path = state["docx_path"]
    # 校验state变量是否为空
    if not docx_path:
        logger.error("docx_path 为空，请重新上传文件")
        raise ValueError("docx_path 为空，请重新上传文件")

    # 校验docx文件是否存在
    # Path 对象
    docx_obj = Path(docx_path)
    # exists() 方法检查文件是否存在
    if not docx_obj.exists():
        # 文件不存在
        raise FileNotFoundError(f"docx_path {docx_obj} 不存在")

    # 获取当前工作目录
    local_dir = state.get("local_dir")
    # 如果local_dir为空，则使用docx_obj的父目录作为工作目录,否则使用local_dir作为工作目录
    work_dir = Path(local_dir) if local_dir else docx_obj.parent
    # mkdir 方法创建目录
    # parents=True 表示创建所有父目录
    # exist_ok=True 表示如果目录已存在，则不抛出异常
    work_dir.mkdir(parents=True, exist_ok=True)
    return docx_obj,work_dir

# 提取图片
@step_log("step_2_extract_images")
def step_2_extract_images(docx_obj, work_dir):
    """
    从 docx（zip 结构）中抽取 word/media/ 下的图片到 images/ 目录。
    这样后续 node_md_img 才能扫描到图片并上传 MinIO。
    """

    # 提取图片目录路径
    # images_dir 是图片目录路径，用于存储抽取的图片
    images_dir = work_dir / IMAGES_DIR_NAME
    # mkdir 方法创建目录
    # parents=True 表示创建所有父目录
    # exist_ok=True 表示如果目录已存在，则不抛出异常
    images_dir.mkdir(parents=True, exist_ok=True)

    # 提取图片字典
    # extracted 是一个字典，键为图片名，值为图片路径
    extracted = {}

    try:
        # 读取 zip 文件，打开docx_obj文件
        # with 语句确保文件在使用后自动关闭
        with zipfile.ZipFile(docx_obj,"r") as z:
            # docx 本身就是 ZIP 压缩包：.docx 文件本质上是 Office Open XML (OOXML) 格式的 ZIP 归档
            # 遍历 zip 文件中的所有文件，将其赋值给 name
            # namelist() 是列出内部文件列表的地址
            for name in z.namelist():
                # 提取 word/media/ 下的图片
                if name.startswith("word/media/"):
                    # 提取文件名的最后一个部分，即文件名带后缀
                    file_name = Path(name).name
                    # 校验文件名是否为空
                    if not file_name :
                        continue
                    # 在 images_dir 目录下创建目标文件路径
                    target = images_dir / file_name
                    # z.read(name)：从 ZIP 包中读取名为 name 的文件内容，
                    # 返回 bytes 类型的数据（二进制）
                    # write_bytes() 方法将二进制数据写入文件,如果文件已存在则覆盖，不存在则创建
                    target.write_bytes(z.read(name))
                    # 记录抽取的图片路径
                    # 将 target 存储到 extracted 字典中，并以 file_name 作为索引
                    extracted[file_name] = target
        logger.info(f"从 {docx_obj.name} 抽取图片 {len(extracted)} 张")
    except zipfile.BadZipFile as e:
        logger.warning(f"docx 不是标准 zip 结构（可能是 .doc 老格式），跳过图片抽取：{e}")
    # images_dir 是图片目录路径，用于存储抽取的图片
    # extracted 是一个字典，键为图片名，值为图片路径
    return images_dir, extracted

# 转换为 md 格式
@step_log("step_3_docx_to_markdown")
def step_3_docx_to_markdown(docx_obj: Path):
    """
        用 python-docx 将 Word 转成 Markdown：
        - Heading 1/2/3 -> # / ## / ###
        - 普通段落 -> 正文
        - 表格 -> Markdown 表格
        注意：python-docx 无法定位图片在段落中的精确位置；
        这里在文末统一以 ![](images/xxx.png) 追加，node_md_img 会据此替换为 MinIO URL。
        """
    # 加载 docx 文件
    # Document(str(docx_obj))：将 docx_obj 转换为字符串，作为参数传递给 Document 类的构造函数
    doc = Document(str(docx_obj))
    lines = []

    # 遍历文档中的所有段落,paragraphs 是一个列表，包含文档中所有段落的实例对象
    for para in doc.paragraphs:
        # 提取段落文本内容,text 是段落文本内容， text.strip() 方法移除字符串首尾的空格
        text = para.text.strip()
        # 校验段落文本是否为空
        if not text:
            continue
        # 提取段落样式名称,style_name 是段落样式名称， lower() 方法将字符串转换为小写
        # 用于判断段落是否为标题段落
        # 例如：Heading 1 -> # / ## / ###
        style_name = (para.style.name or "").lower()
        # 如何判断段落是否为标题段落
        # 例如：Heading 1 -> # / ## / ###
        # 例如：Normal -> 正文
        if style_name.startswith("heading"):
            # 提取标题等级，例如：Heading 1 -> 1
            # 例如：Heading 2 -> 2
            # 例如：Heading 3 -> 3
            level_digits = "".join(ch for ch in style_name if ch.isdigit()) or "1"
            # 校验标题等级是否在 1-6 之间
            level = min(int(level_digits), 6)
            # 格式化标题段落，例如：# 1, ## 2, ### 3
            lines.append(f"{'#' * level} {text}")
        else:
            # 普通段落，直接添加到 lines 列表中
            lines.append(text)
        # 段落之间添加空行，用于分隔不同的段落
        lines.append("")

    # 表格转md
    # 遍历文档中的所有表格,tables 是一个列表，包含文档中所有表格的实例对象
    for table in doc.tables:
        # 遍历表格中的所有行,rows 是一个列表，包含表格中所有行的实例对象
        for row in table.rows:
            # 遍历行中的所有单元格,cells 是一个列表，包含行中所有单元格的实例对象
            # 提取单元格文本内容,text 是单元格文本内容， text.strip() 方法移除字符串首尾的空格
            # replace("\n", "")
            cells = [c.text.strip().replace("\n", "") for c in row.cells]
            # 格式化表格行，例如：| 1 | 2 | 3 |

            lines.append("| " + " | ".join(cells) + " |")
        # 表格之间添加空行，用于分隔不同的表格
        lines.append("")
    # 返回转换后的 md 文本，将 lines 列表中的所有行用换行符连接起来，并转换为字符串
    return "\n".join(lines)

# 保存为 md 文件
@step_log("step_4_append_images_and_save")
def step_4_append_images_and_save(work_dir, md_text, images_dir, stem):
    """把抽取到的图片以标准 Markdown 语法追加到文末，然后写出 md 文件"""
    # 遍历 images_dir 目录下的所有文件，只保留文件，不保留目录,返回一个列表，列表内容是图片路径对象
    image_files = sorted(
        # 过滤出文件，不保留目录
        [p for p in images_dir.iterdir() if p.is_file()],
        key=lambda p: p.stem,
    ) if images_dir.exists() else []

    if image_files:
        md_text += "\n\n## 附图\n\n"
        for img in image_files:
            # 相对路径 images/xxx.png，node_md_img 用文件名做正则匹配，能正确识别
            md_text += f"![{img.stem}]({IMAGES_DIR_NAME}/{img.name})\n\n"

    # 设置 md 文件路径，work_dir 是工作目录，stem 是文件名前缀
    md_path = work_dir / f"{stem}.md"
    # 写入 md 文件
    md_path.write_text(md_text, encoding="utf-8")
    # 返回 md 文件路径
    return str(md_path)





@node_log("node_docx_to_md")
def node_docx_to_md(state: ImportGraphState) -> ImportGraphState:
    """
    节点: docx_to_md (node_docx_to_md) —— 金融知识库版
    1. 接收 docx_path
    2. 转换为 md 格式
    3. 保存为 md 文件
    :param state: 包含 docx_path 的状态
    :return: 更新后的状态，包含 md_path
    """
    # 添加运行中的任务
    add_running_task(state["task_id"],"node_docx_to_md")

    # 验证 docx 文件
    # docx_obj 是文件路径，work_dir 是工作目录
    docx_obj,work_dir = step_1_validate_docx(state)

    # 提取图片
    images_dir, _ = step_2_extract_images(docx_obj, work_dir)

    # 转换为 md 格式，返回的是一个字符串
    md_text = step_3_docx_to_markdown(docx_obj)

    # 保存为 md 文件，work_dir 是工作目录，md_text 是 md 文本，images_dir 是图片目录路径，stem 是文件名前缀
    md_path = step_4_append_images_and_save(work_dir, md_text, images_dir, docx_obj.stem)





