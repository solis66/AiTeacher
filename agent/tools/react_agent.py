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
from model.factory import chat_model, get_chat_model, is_model_initialized
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import rag_summarize, get_user_id
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
    
    def _init_agent(self):
        """
        延迟初始化Agent，确保模型已准备好
        
        处理流程：
            1. 检查初始化节流，避免频繁尝试
            2. 检查全局chat_model是否有效
            3. 如果无效，尝试重新初始化模型
            4. 创建LangChain Agent实例
            5. 标记初始化成功
            
        异常：
            EnvironmentError - 当模型无法初始化时抛出
        """
        global chat_model
        
        # 检查节流：5秒内不重复尝试初始化
        current_time = time.time()
        if current_time - self._last_init_attempt < 5:
            print("[ReactAgent] 节流保护：距离上次初始化尝试不足5秒")
            raise EnvironmentError("初始化过于频繁，请稍后重试")
        self._last_init_attempt = current_time
        
        # 检查模型是否有效
        if chat_model is None:
            print("[ReactAgent] 警告：chat_model为None，尝试重新初始化")
            try:
                chat_model = get_chat_model()
                print("[ReactAgent] 模型重新初始化成功")
            except Exception as e:
                print(f"[ReactAgent] 模型重新初始化失败: {str(e)}")
                raise EnvironmentError(f"AI代理服务未初始化，请检查API密钥配置: {str(e)}")
        
        # 验证模型是否有效
        if chat_model is None:
            print("[ReactAgent] 错误：模型初始化后仍为None")
            raise EnvironmentError("AI模型初始化失败，请联系管理员")
        
        try:
            print("[ReactAgent] 开始创建LangChain Agent实例...")
            self._agent = create_agent(
                model=chat_model,
                system_prompt=load_system_prompts(),
                tools=[rag_summarize, get_user_id],
                middleware=[monitor_tool, log_before_model],
            )
            self._initialized = True
            print("[ReactAgent] Agent初始化成功")
        except Exception as e:
            print(f"[ReactAgent] Agent初始化失败: {str(e)}")
            print(f"[ReactAgent] 详细错误: {traceback.format_exc()}")
            raise EnvironmentError(f"创建AI代理失败: {str(e)}")
    
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
    
    def execute_stream(self, query: str):
        """
        流式执行查询，返回AI生成的增量内容
        
        参数：
            query: string - 用户输入的查询内容
            
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
        
        input_dict = {
            "messages": [
                {"role": "user", "content": query},
            ]
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
                    yield f"抱歉，获取响应失败：{str(e2)}"
                    return
            
            for chunk in stream_iterator:
                chunk_count += 1
                
                # 安全检查：防止无限循环
                if chunk_count > max_chunks:
                    print("[ReactAgent] 警告：超过最大chunk数量限制")
                    break
                
                # 解析chunk内容
                new_content = self._parse_chunk(chunk)
                print(f"[ReactAgent] 解析第{chunk_count}个chunk，内容长度: {len(new_content)}")
                
                # 如果获取到内容
                if new_content:
                    total_content += new_content  # 直接累积内容
                    
                    # 如果与之前不同，计算增量
                    if new_content != previous_content:
                        # 计算增量（只返回新增的部分）
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
                        # 解析非流式响应
                        if isinstance(response, dict):
                            if "output" in response:
                                total_content = str(response["output"])
                            elif "content" in response:
                                total_content = str(response["content"])
                        elif hasattr(response, "content"):
                            total_content = str(response.content)
                        else:
                            total_content = str(response)
                        
                        if total_content and total_content.strip():
                            print(f"[ReactAgent] 非流式备用方式成功，内容长度: {len(total_content)}")
                            yield total_content
                        else:
                            yield "抱歉，AI服务暂时无法提供响应，请稍后重试。"
                    else:
                        yield "抱歉，AI服务暂时无法提供响应，请稍后重试。"
                except Exception as e:
                    print(f"[ReactAgent] 非流式备用方式失败: {str(e)}")
                    yield "抱歉，AI服务暂时无法提供响应，请稍后重试。"
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
        except Exception as e:
            # 其他未知错误
            print(f"[ReactAgent] 流式执行失败: {str(e)}")
            print(f"[ReactAgent] 详细错误: {traceback.format_exc()}")
            # 尝试使用直接模型调用作为最后的备用方案
            try:
                print("[ReactAgent] 尝试直接调用模型作为最终备用方案")
                global chat_model
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

    def execute(self, query: str) -> str:
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
        for chunk in self.execute_stream(query):
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