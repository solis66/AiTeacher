from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import chroma_conf
from model.factory import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
from utils.file_handler import txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger
from utils.path_tool import get_abs_path


class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=chroma_conf["persist_directory"],
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})

    def search_with_scores(self, query: str, k: int = None, threshold: float = None,
                           where: dict = None) -> list:
        """
        检索并返回带相似度分数的片段。

        为什么需要它：`as_retriever()` 把相似度分数丢掉了，调用方无法做阈值过滤。
        而没有阈值就只能"检索到什么就用什么"，这正是此前 `filter_relevant_docs`
        要用字符重叠去凑相关性判断的原因——那个做法是无效的（见下方说明）。
        有了分数就不需要任何启发式补丁。

        参数：
            query:     查询文本
            k:         召回条数，默认取配置值
            threshold: 相似度下限，低于该值的片段丢弃；默认取配置的 score_threshold
            where:     metadata 过滤条件，用于按 owner / 学生 等维度隔离

        返回：
            [(Document, score), ...]，异常时返回空列表
        """
        query = (query or '').strip()
        if not query:
            return []
        try:
            kwargs = {'k': k or chroma_conf["k"]}
            if where:
                kwargs['filter'] = where
            raw = self.vector_store.similarity_search_with_relevance_scores(query, **kwargs)
        except Exception as e:
            logger.error(f"[向量检索]失败: {str(e)}")
            return []
        # 阈值来源：显式参数 → 配置的 consult.score_threshold → 兜底 0.20
        limit = threshold
        if limit is None:
            limit = float((chroma_conf.get('consult') or {}).get('score_threshold', 0.20))
        return [(doc, score) for doc, score in raw if score is not None and score >= limit]
    
    def load_document(self):
        """
        从数据文件夹内读取数据文件，转为向量存储到向量库

        去重与更新策略：**按文件路径先删后加**。
        此前只记录 md5 并判断"是否出现过"：文件更新后 md5 是新的，
        于是只新增分片而不删除旧分片，库里同一份文件会同时存在两代内容，
        检索时随机命中旧版，且看不出任何异常。

        状态文件格式为每行 `md5<TAB>相对路径`，既能判断内容是否变化，
        也能定位到该文件在库里的历史分片以便清理。

        :return: None
        """
        allowed_files_path: list[str] = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allowed_knowledge_file_type"]),
        )
        if not allowed_files_path:
            logger.info("[加载知识库]未找到符合类型的知识文件，跳过")
            return

        state_path = get_abs_path(chroma_conf["md5_hex_store"])

        def load_state() -> dict:
            if not os.path.exists(state_path):
                open(state_path, "w", encoding="utf-8").close()
                return {}
            state = {}
            with open(state_path, "r", encoding="utf-8") as f:
                for line in f.readlines():
                    line = line.strip()
                    if not line:
                        continue
                    # 兼容旧格式（仅一行 md5）：旧记录没有路径信息，无法定位分片，
                    # 视为"来源未知"，首次运行会重建一次索引。
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        state[parts[1]] = parts[0]
                    else:
                        state.setdefault("__legacy__", parts[0])
            return state

        def save_state(state: dict) -> None:
            with open(state_path, "w", encoding="utf-8") as f:
                for rel_path, md5_value in state.items():
                    if rel_path == "__legacy__":
                        continue
                    f.write(f"{md5_value}\t{rel_path}\n")

        def get_file_documents(read_path: str):
            if read_path.endswith("txt"):
                return txt_loader(read_path)
            if read_path.endswith("md"):
                return txt_loader(read_path)
            return []

        state = load_state()
        data_root = get_abs_path(chroma_conf["data_path"])
        seen_paths = set()

        for path in allowed_files_path:
            rel_path = os.path.relpath(path, data_root).replace("\\", "/")
            seen_paths.add(rel_path)

            # 获取文件的md5
            md5_hex = get_file_md5_hex(path)
            if not md5_hex:
                continue

            if state.get(rel_path) == md5_hex:
                logger.info(f"[加载知识库]{path}内容未变化，跳过")
                continue

            try:
                documents: list[Document] = get_file_documents(path)

                if not documents:
                    logger.warning(f"[加载知识库]{path}内没有有效文本，跳过")
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库]{path}分片后没有有效文本，跳过")
                    continue

                # 为分片打上来源标记，既支持按来源精确清理，也便于检索时回溯出处
                for doc in split_document:
                    doc.metadata["source"] = rel_path

                # 先删旧版，再写入当前内容：保证一个来源在库中只有一份
                self.vector_store.delete(where={"source": rel_path})
                self.vector_store.add_documents(split_document)

                state[rel_path] = md5_hex
                logger.info(f"[加载知识库]{path}内容加载成功（{len(split_document)}个分片）")

            except Exception as e:
                # exc_info=True会记录详细的报错堆栈，如果为false仅记录报错信息本身
                logger.error(f"[加载知识库]{path}加载失败：{str(e)}", exc_info=True)
                continue

        # 清理已从磁盘删除的文件在库中的残留分片
        for stale in [p for p in state if p not in seen_paths and p != "__legacy__"]:
            try:
                self.vector_store.delete(where={"source": stale})
                state.pop(stale, None)
                logger.info(f"[加载知识库]已清理不存在的来源：{stale}")
            except Exception as e:
                logger.error(f"[加载知识库]清理来源{stale}失败：{str(e)}")

        save_state(state)

# if __name__ == '__main__':
#     vs = VectorStoreService()
#
#     vs.load_document()
#
#     retriever = vs.get_retriever()
#
#     res = retriever.invoke("字数")
#
#     for r in res:
#         print(r.page_content)
#         print("-"*20)







    