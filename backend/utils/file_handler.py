import os, hashlib

from langchain_core.documents import Document

from utils.logger_handler import logger
from langchain_community.document_loaders import PyPDFLoader, TextLoader

# 获取文件的md5的十六进制字符串
def get_file_md5_hex(filepath: str):
    if not os.path.exists(filepath):
        logger.error(f"[md5计算]文件{filepath}不存在")
        return

    if not os.path.isfile(filepath):
        logger.error(f"[md5计算]路径{filepath}不是文件")
        return

    md5_obj = hashlib.md5()

    # 4kb分片，避免文件过大爆内存
    chunk_size = 4096

    try:
        with open(filepath, "rb") as f:  # 必须二进制读取
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)
            """
            chunk = f.read(chunk_size)
            while chunk:
                    
                md5_obj.update(chunk)
                chunk = f.read(chunk_size) 
            """
            md5_hex = md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件{filepath}失败,  {str(e)}")
        return None

# 返回文件夹内的文件列表（允许的文件后缀）
def listdir_with_allowed_type(path: str, allowed_types: tuple[str]):
    """
    递归列出目录下符合后缀的文件。

    使用 os.walk 而不是 os.listdir：此前只扫一层，放在子目录里的语料会被静默忽略
    （例如 knowledge/写作方法/*.md 永远进不了索引），且这种遗漏没有任何报错提示。
    """
    files = []

    if not os.path.isdir(path):
        logger.error(f"[listdir_with_allowed_type{path}不是文件夹]")
        return tuple()

    for root, _dirs, names in os.walk(path):
        for name in names:
            if name.endswith(allowed_types):
                files.append(os.path.join(root, name))
    return tuple(sorted(files))

# def pdf_loader(filepath:str, password=None) -> list[Document]:
#     return PyPDFLoader(filepath, password).load()

def txt_loader(filepath: str) -> list[Document]:
    return TextLoader(filepath, encoding="utf-8").load()