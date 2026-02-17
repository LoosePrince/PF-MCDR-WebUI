import os
from pathlib import Path

from guguwebui.constant import CSS_FILE, JS_FILE
from guguwebui.structures import BusinessException


class FileService:
    def __init__(self, server):
        self.server = server

    def load_custom_file(self, file_type: str):
        """加载 overall.js 或 overall.css"""
        file_path = CSS_FILE if file_type == "css" else JS_FILE
        path = Path(file_path)

        if not path.exists():
            return ""

        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            self.server.logger.error(f"读取文件 {file_type} 失败: {e}")
            raise BusinessException(f"读取文件失败: {str(e)}")

    def save_custom_file(self, file_type: str, content: str):
        """保存 overall.js 或 overall.css"""
        file_path = CSS_FILE if file_type == "css" else JS_FILE
        path = Path(file_path)

        try:
            # 确保目录存在
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"status": "success", "message": f"{file_type} 保存成功"}
        except Exception as e:
            self.server.logger.error(f"保存文件 {file_type} 失败: {e}")
            raise BusinessException(f"保存文件失败: {str(e)}")

    def get_icp_records(self, config_service):
        """获取 ICP 备案信息"""
        config = config_service.get_config()
        return {"status": "success", "icp_records": config.get("icp_records", [])}
