import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from app.core.logger import logger
from app.import_process.agent.main_graph import kb_import_app
from app.import_process.agent.state import create_default_state
from app.utils.path_util import PROJECT_ROOT
from app.utils.task_utils import update_task_status, TASK_STATUS_PROCESSING, add_done_task, TASK_STATUS_COMPLETED, \
    TASK_STATUS_FAILED, add_running_task, get_task_status, get_running_task_list, get_done_task_list

app = FastAPI( title="金融知识库 · 导入服务",
    description="金融知识库：文档导入（PDF / Markdown / Word）",)

# 解决跨域问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 导航页（两个服务共用同一份） ====================
NAV_PAGE_PATH = PROJECT_ROOT / "app" / "nav" / "page" / "nav.html"


@app.get("/")
@app.get("/nav.html")
def nav_page():
    """根路径与 /nav.html 都返回导航页，作为系统统一入口"""
    if not NAV_PAGE_PATH.exists():
        raise HTTPException(status_code=404, detail="nav.html not found")
    return FileResponse(str(NAV_PAGE_PATH))


@app.get("/health")
def health():
    """健康检查：供导航页探测服务是否已启动"""
    return {"ok": True}


# ★改2：支持的文件类型白名单（必须与 node_entry 的判断保持一致）
ALLOWED_EXTENSIONS = {".pdf", ".md", ".doc", ".docx"}

@app.get("/import.html")
def import_file():
    # 获取import.html文件的路径
    import_file_path = PROJECT_ROOT / "app" / "import_process" / "page" / "import.html"
    # 判断import_file_path所对应的文件是否存在
    if not import_file_path.exists():
        raise HTTPException(status_code=404, detail="import.html not found")
    # 直接将import.html响应到浏览器
    return FileResponse(str(import_file_path))

# 创建后台任务，即执行LangGraph的图对象完成RAG的导入流程
def run_graph_task(task_id, local_file_path, local_dir):
    try:
        logger.info("导入流程开始")
        # 记录后台任务的执行状态为执行中
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        # 创建状态
        init_state = create_default_state(
            task_id=task_id,
            local_file_path=local_file_path,
            local_dir=local_dir,
        )
        # 流式执行图
        results = kb_import_app.stream(init_state)
        for result in results:
            for node_name, node_result in result.items():
                add_done_task(task_id, node_name)
        # 记录后台任务的执行状态为已完成
        logger.info("导入流程成功")
        update_task_status(task_id, TASK_STATUS_COMPLETED)
    except Exception as e:
        # 记录后台任务的执行状态为失败
        logger.error(f"导入流程失败，{e}")
        update_task_status(task_id, TASK_STATUS_FAILED)

@app.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    # 获取今天的日期，格式化为年月日格式的字符串
    today_str = datetime.now().strftime("%Y%m%d")
    # 设置today_str所对应的Path对象
    today_str_dir = PROJECT_ROOT / "output" / today_str
    # 创建存储每个上传文件所对应的task_id的列表
    task_ids = []
    # 遍历files，上传文件
    for file in files:

        # 新增 ★改2：先校验扩展名，避免上传后才发现不支持
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型：{file.filename}，仅支持 PDF / Markdown / Word（.pdf/.md/.doc/.docx）",
            )

        # 使用uuid获取随机序列作为task_id
        task_id = str(uuid.uuid4())
        # 存储task_id
        task_ids.append(task_id)
        # 记录当前任务的状态为进行中
        add_running_task(task_id, "upload_file")
        # 获取上传文件的位置
        upload_dir_path = today_str_dir / task_id
        upload_dir_path.mkdir(parents=True, exist_ok=True)
        upload_file_path = upload_dir_path / file.filename
        # with open(upload_file_path, "wb") as f:
        with upload_file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        # 记录当前任务的状态为已完成
        add_done_task(task_id, "upload_file")
        # 执行后台任务，即执行图
        background_tasks.add_task(
            run_graph_task,
            task_id,
            str(upload_file_path),
            str(upload_dir_path)
        )
    return {
        "code": 200,
        "message": "upload success",
        "task_ids": task_ids
    }

# 根据task_id查询当前任务的状态信息
@app.get("/status/{task_id}")
async def get_status(task_id: str):
    return {
        "code": 200,
        "task_id": task_id,
        "status": get_task_status(task_id),
        "running_list": get_running_task_list(task_id),
        "done_list": get_done_task_list(task_id)
    }

if __name__ == "__main__":
    uvicorn.run("file_import_service:app", host="127.0.0.1", port=8000, reload=True)