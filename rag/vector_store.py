from langchain_chroma import Chroma
from utils.config_handler import chroma_conf
from model.factory import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter

class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collectioin_name = chroma_conf("collection_name"),
            embedding_function = embed_model,
            persist_directory=chroma_conf("persist_directory"),
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size = chroma_conf("chunk_size"),
            chunk_overlap=chroma_conf("chunk_overlap"),
            separators=chroma_conf("separators"),
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})

    