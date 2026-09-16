"""
ReactAgent - AI对话代理类
负责与AI模型交互，处理用户消息并返回流式响应

功能特性：
- 支持延迟初始化，在首次使用时检查模型状态
- 提供流式和非流式两种执行方式
- 支持多种chunk格式解析
- 完善的错误处理和空响应检查
- 支持自动重试和状态恢复
"""

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk
from model.factory import chat_model, get_chat_model, is_model_initialized
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import search_knowledge
from agent.tools.middleware import monitor_tool, log_before_model
from utils.error_handler import ServiceUnavailableError
import traceback
import time


class ReactAgent:
    """
    AI对话代理类
    负责与AI模型交互，处理用户消息并返回流式响应
    
    功能特性：
        1. 延迟初始化：在首次使用时检查模型状态
        2. 自动重试：模型不可用时尝试重新初始化
        3. 多格式支持：支持多种chunk格式解析
        4. 空响应处理：检测并处理AI返回空白的情况
        5. 完善的错误处理：提供明确的错误提示
        6. 状态管理：维护初始化状态，避免重复初始化
    """
    
    def __init__(self):
        """
        初始化ReactAgent
        
        设置：
            _agent: AI代理实例（延迟初始化）
            _initialized: 标记是否已成功初始化
            _last_init_attempt: 上次初始化尝试时间，用于节流
        """
        self._agent = None
        self._initialized = False
        self._last_init_attempt = 0  # 上次初始化尝试时间
    
    def _build_agent(self):
        """
        真正创建 LangChain Agent（不包含节流与模型状态检查）。
        供首次初始化、以及「底层执行器被关闭后重建」两处复用。

        异常：
            EnvironmentError - 当模型未就绪或创建失败时抛出
        """
        global chat_model

        # 检查模型是否有效
        if chat_model is None:
            print("[ReactAgent] 警告：chat_model为None，尝试重新初始化")
            try:
                chat_model = get_chat_model()
                print("[ReactAgent] 模型重新初始化成功")
            except Exception as e:
                print(f"[ReactAgent] 模型重新初始化失败: {str(e)}")
                raise EnvironmentError(f"AI代理服务未初始化，请检查API密钥配置: {str(e)}")

        if chat_model is None:
            print("[ReactAgent] 错误：模型初始化后仍为None")
            raise EnvironmentError("AI模型初始化失败，请联系管理员")

        try:
            print("[ReactAgent] 开始创建LangChain Agent实例...")
            # 工具列表（2026-09 调整）：
            #   只保留与「咨询」意图一致的检索工具。此前注册的 rag_summarize 返回的是
            #   整份批改 JSON，agent 会把一句提问当成作文去批改，产出"总分 XX"的假结果；
            #   get_user_id 返回的是随机假 ID，可能被当成学生的真实编号写进回答。
            #   两者都已从咨询 agent 摘除。
            #   学情数据与历史批改片段由 services/consult_context 以确定性方式注入
            #   prompt，不依赖模型"想不想查"，因此这里只留一个补充检索工具。
            self._agent = create_agent(
                model=chat_model,
                system_prompt=load_system_prompts(),
                tools=[search_knowledge],
                middleware=[monitor_tool, log_before_model],
            )
            self._initialized = True
            print("[ReactAgent] Agent初始化成功")
        except Exception as e:
            print(f"[ReactAgent] Agent初始化失败: {str(e)}")
            print(f"[ReactAgent] 详细错误: {traceback.format_exc()}")
            raise EnvironmentError(f"创建AI代理失败: {str(e)}")

    def _init_agent(self):
        """
        延迟初始化Agent，确保模型已准备好
        
        处理流程：
            1. 检查初始化节流，避免频繁尝试
            2. 创建LangChain Agent实例
            3. 标记初始化成功
            
        异常：
            EnvironmentError - 当模型无法初始化时抛出
        """
        # 检查节流：5秒内不重复尝试初始化
        current_time = time.time()
        if current_time - self._last_init_attempt < 5:
            print("[ReactAgent] 节流保护：距离上次初始化尝试不足5秒")
            raise EnvironmentError("初始化过于频繁，请稍后重试")
        self._last_init_attempt = current_time

        self._build_agent()

    def _rebuild_agent(self):
        """
        在底层执行器（线程池）被关闭后重建 Agent。
        
        触发场景：开发服务器热重载 / 进程回收期间，create_agent 返回的图内部
        ThreadPoolExecutor 会被关闭，此后复用 self._agent 去 stream() 会抛出
        RuntimeException("cannot schedule new futures after shutdown")。
        此时必须丢弃旧实例并重建一个，而不是把异常吞掉。
        """
        print("[ReactAgent] 检测到 Agent 底层执行器已关闭，正在重建...")
        self._agent = None
        self._initialized = False
        self._build_agent()
        print("[ReactAgent] Agent 重建成功")
    
    def _ensure_agent_ready(self):
        """
        确保Agent已准备好，如果未初始化则尝试初始化
        
        异常：
            ServiceUnavailableError - 当Agent无法初始化时抛出
        """
        # 如果已初始化且agent有效，直接返回
        if self._initialized and self._agent is not None:
            return
        
        # 尝试初始化
        if self._agent is None:
            try:
                self._init_agent()
            except EnvironmentError as e:
                print(f"[ReactAgent] _ensure_agent_ready 失败: {str(e)}")
                raise ServiceUnavailableError(str(e))
        
        # 再次检查初始化状态
        if self._agent is None:
            raise ServiceUnavailableError("AI代理服务未初始化，请联系管理员检查配置")
    
    def _parse_chunk(self, chunk):
        """
        解析流式响应的chunk，支持多种格式
        
        参数：
            chunk: Any - 来自AI模型的响应块
            
        返回：
            string - 解析后的内容
            
        支持的格式：
            1. 元组格式：(AIMessage, ...)
            2. 字典格式：{"content": "..."} 或 {"message": {"content": "..."}}
            3. 对象格式：具有content属性的对象
            4. BaseMessage格式：具有dict()方法的对象
            5. LangChain Agent格式：包含output、thought、actions等键
        """
        # 记录chunk类型用于调试
        chunk_type = type(chunk).__name__
        print(f"[ReactAgent] 解析chunk，类型: {chunk_type}")
        
        # 方式0：chunk是元组，第一个元素是AIMessage
        if isinstance(chunk, tuple) and len(chunk) > 0:
            print(f"[ReactAgent] chunk是元组，长度: {len(chunk)}")
            chunk = chunk[0]
            chunk_type = type(chunk).__name__
        
        # 尝试多种方式获取内容
        new_content = ""
        
        # 方式1：chunk是字典（支持多种嵌套结构）
        if isinstance(chunk, dict):
            print(f"[ReactAgent] chunk是字典，键: {list(chunk.keys())}")
            
            # 直接content键
            if "content" in chunk:
                new_content = chunk["content"]
                print(f"[ReactAgent] 从字典['content']获取内容，长度: {len(str(new_content))}")
            
            # message.content结构
            elif "message" in chunk and isinstance(chunk["message"], dict):
                new_content = chunk["message"].get("content", "")
                print(f"[ReactAgent] 从字典['message']['content']获取内容，长度: {len(new_content)}")
            
            # LangChain Agent流式响应格式
            elif "output" in chunk:
                output = chunk["output"]
                if isinstance(output, str):
                    new_content = output
                elif isinstance(output, dict) and "content" in output:
                    new_content = output["content"]
                print(f"[ReactAgent] 从字典['output']获取内容，长度: {len(str(new_content))}")
            
            # 检查generation相关字段
            elif "generations" in chunk:
                generations = chunk.get("generations", [])
                if generations and len(generations) > 0:
                    for gen in generations:
                        if isinstance(gen, dict) and "message" in gen:
                            msg = gen["message"]
                            if isinstance(msg, dict) and "content" in msg:
                                new_content += msg["content"]
                            elif hasattr(msg, "content"):
                                new_content += str(msg.content)
                print(f"[ReactAgent] 从字典['generations']获取内容，长度: {len(new_content)}")
            
            # 检查action和thought字段（Agent思考过程）
            elif "thought" in chunk:
                new_content = chunk["thought"]
                print(f"[ReactAgent] 从字典['thought']获取内容，长度: {len(new_content)}")
        
        # 方式2：chunk是对象，有content属性
        elif hasattr(chunk, "content"):
            print(f"[ReactAgent] chunk是对象，具有content属性")
            new_content = chunk.content
            print(f"[ReactAgent] 从content属性获取内容，长度: {len(str(new_content))}")
        
        # 方式3：chunk是BaseMessage对象
        elif hasattr(chunk, "dict"):
            print(f"[ReactAgent] chunk是BaseMessage对象，尝试调用dict()方法")
            try:
                chunk_dict = chunk.dict()
                new_content = chunk_dict.get("content", "")
                print(f"[ReactAgent] 从dict()获取内容，长度: {len(new_content)}")
            except Exception as e:
                print(f"[ReactAgent] 调用dict()失败: {str(e)}")
        
        # 方式4：尝试直接转换为字符串（最后的兜底）
        else:
            try:
                str_chunk = str(chunk)
                # 尝试从字符串中提取JSON内容
                import re
                json_match = re.search(r'"content"\s*:\s*["\']([^"\']+)["\']', str_chunk)
                if json_match:
                    new_content = json_match.group(1)
                    print(f"[ReactAgent] 从字符串中提取JSON内容，长度: {len(new_content)}")
                else:
                    # 如果是字符串类型且内容不为空，直接使用
                    if chunk_type == "str" and str_chunk.strip():
                        new_content = str_chunk
                        print(f"[ReactAgent] chunk是字符串，长度: {len(new_content)}")
                    else:
                        print(f"[ReactAgent] 无法解析chunk，类型: {chunk_type}，内容: {str_chunk[:100]}...")
            except Exception as e:
                print(f"[ReactAgent] 字符串解析失败: {str(e)}")
        
        return str(new_content) if new_content else ""
    
    def execute_stream(self, query: str, history=None, _retried: bool = False):
        """
        流式执行查询，返回AI生成的增量内容
        
        参数：
            query: string - 用户输入的查询内容
            
            history: list[dict] | None - 本会话此前的对话轮次
                     （[{'role': 'user'|'assistant', 'content': str}, ...]），
                     应经 utils.chat_memory.normalize_history 裁剪后传入。
                     作为真实的多轮消息前置，让模型能区分「学生说的」与
                     「老师此前回答过的」；为空则退化为原有的单轮问答。

        返回：
            Generator[str] - AI生成的增量内容块
            
        异常：
            ServiceUnavailableError - 当AI服务不可用时抛出
            
        处理流程：
            1. 确保Agent已准备好
            2. 构建输入消息
            3. 流式调用AI模型
            4. 解析每个chunk并计算增量
            5. 检查空响应并返回友好提示
            6. 处理各类异常，提供友好的错误提示
        """
        # 确保Agent已准备好
        try:
            self._ensure_agent_ready()
        except ServiceUnavailableError as e:
            print(f"[ReactAgent] Agent未就绪: {str(e)}")
            yield f"抱歉，服务暂时不可用：{str(e)}"
            return
        
        # 对话记忆：历史轮次在前、当前问题在后，构成完整消息序列。
        # 此前这里恒为单条消息，模型看不到任何上文，用户追问「刚才那个」时无从衔接。
        messages = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in (history or [])
        ]
        messages.append({"role": "user", "content": query})
        if history:
            print(f"[ReactAgent] 携带对话记忆 {len(history)} 条"
                  f"（{sum(len(t['content']) for t in history)} 字符）")

        input_dict = {
            "messages": messages
        }
        
        previous_content = ""
        total_content = ""
        chunk_count = 0
        max_chunks = 1000  # 防止无限循环
        
        try:
            # 验证agent是否有效
            if not self._agent:
                print("[ReactAgent] 错误：_agent为None")
                yield "抱歉，服务暂时不可用，请稍后重试。"
                return
            
            print(f"[ReactAgent] 开始流式执行查询，内容长度: {len(query)}")
            
            # 尝试获取流式响应
            stream_iterator = None
            try:
                stream_iterator = self._agent.stream(input_dict, stream_mode="messages")
                print("[ReactAgent] 成功获取流式迭代器")
            except Exception as e:
                print(f"[ReactAgent] 获取流式迭代器失败: {str(e)}")
                # 尝试不使用stream_mode参数
                try:
                    stream_iterator = self._agent.stream(input_dict)
                    print("[ReactAgent] 尝试不使用stream_mode参数成功")
                except Exception as e2:
                    print(f"[ReactAgent] 再次尝试获取流式迭代器失败: {str(e2)}")
                    # 若为「底层执行器已关闭」等可恢复错误，交由外层统一判断是否重建重试
                    raise
            
            for chunk in stream_iterator:
                chunk_count += 1
                
                # 安全检查：防止无限循环
                if chunk_count > max_chunks:
                    print("[ReactAgent] 警告：超过最大chunk数量限制")
                    break
                
                # stream_mode="messages" 下 chunk 是 (消息, 元数据) 元组：
                #   - AIMessageChunk：模型增量 token，本身就是增量，必须直接输出。
                #     （此前的 delta 裁剪按"累积全文"设计，用在增量 token 上会
                #     按 previous chunk 的长度随机丢字，导致回答文字错乱。）
                #   - 完整 AIMessage：模型不支持流式时 langgraph 整条补发，取全文。
                #   - ToolMessage / SystemMessage 等节点产物：工具返回值与系统消息，
                #     不是给用户看的正文，必须跳过，否则检索文本会混进回答。
                msg = chunk[0] if isinstance(chunk, tuple) and chunk else chunk
                content = getattr(msg, "content", None)
                emit_mode = None

                if isinstance(msg, AIMessageChunk):
                    if isinstance(content, str):
                        new_content = content
                    elif isinstance(content, list):
                        # 部分模型返回内容块列表，只取其中的文本块
                        new_content = "".join(
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        new_content = ""
                    emit_mode = "token"
                elif isinstance(msg, AIMessage):
                    new_content = content if isinstance(content, str) else ""
                    emit_mode = "full"
                elif not isinstance(chunk, tuple) and not hasattr(msg, "type"):
                    # 非 messages 流格式（dict 等旧格式兜底），沿用原解析
                    new_content = self._parse_chunk(chunk)
                    emit_mode = "legacy"
                else:
                    new_content = ""

                if new_content:
                    print(f"[ReactAgent] 解析第{chunk_count}个chunk，内容长度: {len(new_content)}")

                # 如果获取到内容
                if new_content:
                    total_content += new_content  # 直接累积内容

                    if emit_mode == "token":
                        # 增量 token 直接输出，不做任何裁剪
                        yield new_content
                    elif emit_mode == "full":
                        if new_content != previous_content:
                            print(f"[ReactAgent] 输出完整消息，长度: {len(new_content)}")
                            yield new_content
                            previous_content = new_content
                    else:
                        # 旧格式兜底路径：保留原有的去重/增量逻辑
                        if new_content != previous_content:
                            delta = new_content[len(previous_content):] if previous_content else new_content
                            if delta:
                                print(f"[ReactAgent] 输出增量内容，长度: {len(delta)}")
                                yield delta
                            previous_content = new_content
            
            # 检查是否返回了有效内容
            if not total_content or not total_content.strip():
                print("[ReactAgent] 警告：AI返回内容为空")
                # 尝试使用非流式方式作为备用
                try:
                    print("[ReactAgent] 尝试非流式执行作为备用")
                    response = self._agent.invoke(input_dict)
                    if response:
                        # invoke 返回的是最终状态：{"messages": [SystemMessage, ..., AIMessage]}
                        # 最终回答在最后一条 AIMessage 里
                        final_msg = None
                        if isinstance(response, dict):
                            msgs = response.get("messages") or []
                            for m in reversed(msgs):
                                if isinstance(m, AIMessage):
                                    final_msg = m
                                    break
                        elif isinstance(response, AIMessage):
                            final_msg = response

                        if final_msg is not None:
                            fc = final_msg.content
                            total_content = fc if isinstance(fc, str) else ""
                        elif isinstance(response, dict) and "output" in response:
                            total_content = str(response["output"])

                        if total_content and total_content.strip():
                            print(f"[ReactAgent] 非流式备用方式成功，内容长度: {len(total_content)}")
                            yield total_content
                        else:
                            yield "抱歉，AI服务暂时无法提供响应，请稍后重试。"
                    else:
                        yield "抱歉，AI服务暂时无法提供响应，请稍后重试。"
                except Exception as e:
                    print(f"[ReactAgent] 非流式备用方式失败: {str(e)}")
                    # 交由外层统一处理（可能是执行器已关闭，需重建重试）
                    raise
            else:
                print(f"[ReactAgent] 流式执行完成，总内容长度: {len(total_content)}")
                
        except ServiceUnavailableError as e:
            # 捕获服务不可用错误
            print(f"[ReactAgent] 服务不可用: {str(e)}")
            yield f"抱歉，服务暂时不可用：{str(e)}"
        except ValueError as e:
            # 配置错误或参数错误
            print(f"[ReactAgent] 配置错误: {str(e)}")
            yield f"抱歉，服务配置有误，请联系管理员：{str(e)}"
        except ConnectionError as e:
            # 网络连接错误
            print(f"[ReactAgent] 网络连接错误: {str(e)}")
            yield "抱歉，网络连接异常，请检查网络后重试。"
        except TimeoutError as e:
            # 超时错误
            print(f"[ReactAgent] 请求超时: {str(e)}")
            yield "抱歉，请求超时，请稍后重试。"
        except RuntimeError as e:
            # 底层执行器已被关闭（服务热重载/进程回收期间，create_agent 返回的图内部
            # ThreadPoolExecutor 被关闭），复用旧 agent 会抛 "cannot schedule new
            # futures after shutdown"。处理方式：丢弃旧实例，重建 Agent 后重试一次。
            msg = str(e) or ""
            if ("shutdown" in msg or "closed" in msg) and not _retried:
                print("[ReactAgent] Agent 底层执行器已关闭，重建后重试一次")
                try:
                    self._rebuild_agent()
                except Exception as re:
                    print(f"[ReactAgent] 重建Agent失败: {str(re)}")
                    yield "抱歉，服务暂时不可用，请稍后重试。"
                    return
                for chunk in self.execute_stream(query, history, _retried=True):
                    yield chunk
                return
            # 其他 RuntimeError：直接调用模型兜底
            print(f"[ReactAgent] 流式执行失败: {str(e)}")
            print(f"[ReactAgent] 详细错误: {traceback.format_exc()}")
            try:
                global chat_model
                if chat_model:
                    response = chat_model.invoke(query)
                    content = response.content if hasattr(response, 'content') else str(response)
                    if content and content.strip():
                        print(f"[ReactAgent] 直接调用模型成功，内容长度: {len(content)}")
                        yield content
                        return
                yield "抱歉，服务暂时不可用，请稍后重试。"
            except Exception as e2:
                print(f"[ReactAgent] 最终备用方案也失败: {str(e2)}")
                yield "抱歉，服务暂时不可用，请稍后重试。"
        except Exception as e:
            # 其他未知错误
            print(f"[ReactAgent] 流式执行失败: {str(e)}")
            print(f"[ReactAgent] 详细错误: {traceback.format_exc()}")
            # 尝试使用直接模型调用作为最后的备用方案
            try:
                print("[ReactAgent] 尝试直接调用模型作为最终备用方案")
                if chat_model:
                    response = chat_model.invoke(query)
                    content = response.content if hasattr(response, 'content') else str(response)
                    if content and content.strip():
                        print(f"[ReactAgent] 直接调用模型成功，内容长度: {len(content)}")
                        yield content
                    else:
                        yield "抱歉，AI服务暂时无法提供响应，请稍后重试。"
                else:
                    yield "抱歉，服务暂时不可用，请稍后重试。"
            except Exception as e2:
                print(f"[ReactAgent] 最终备用方案也失败: {str(e2)}")
                yield "抱歉，服务暂时不可用，请稍后重试。"

    def execute(self, query: str, history=None) -> str:
        """
        非流式执行查询，返回完整响应
        
        参数：
            query: string - 用户输入的查询内容
            
        返回：
            string - AI生成的完整响应
            
        异常：
            ServiceUnavailableError - 当AI服务不可用时抛出
        """
        response = ""
        for chunk in self.execute_stream(query, history):
            response += chunk
        return response
    
    def is_ready(self, auto_init: bool = False) -> bool:
        """
        检查Agent是否已准备好
        
        参数：
            auto_init: bool - 如果为True，当Agent未初始化时尝试自动初始化（默认False）
            
        返回：
            bool - True表示Agent已初始化且可用，False表示不可用
            
        说明：
            当auto_init为True时，此方法会尝试初始化Agent，但不会抛出异常，
            仅在初始化成功后返回True，失败则返回False。
        """
        # 如果已经初始化完成，直接返回True
        if self._initialized and self._agent is not None:
            return True
        
        # 如果需要自动初始化
        if auto_init:
            try:
                self._ensure_agent_ready()
                print("[ReactAgent] 自动初始化成功")
                return True
            except Exception as e:
                print(f"[ReactAgent] 自动初始化失败: {str(e)}")
                return False
        
        return False