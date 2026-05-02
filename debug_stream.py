"""
流式响应调试脚本
用于查看agent.stream返回的数据结构
"""
import os
import sys
import traceback

def debug_stream():
    """调试流式响应"""
    print("Debugging stream response...")
    
    try:
        # 设置环境变量
        os.environ["DASHSCOPE_API_KEY"] = "sk-8f2510cd696447d6a772674419e54a6e"
        
        # 导入并创建agent
        from agent.tools.react_agent import ReactAgent
        
        agent = ReactAgent()
        
        input_dict = {
            "messages": [
                {"role": "user", "content": "Hello"},
            ]
        }
        
        print("\n=== Raw stream output ===")
        for i, chunk in enumerate(agent.agent.stream(input_dict, stream_mode="messages")):
            print(f"\nChunk {i}:")
            print(f"Type: {type(chunk)}")
            print(f"Repr: {repr(chunk)[:500]}")
            
            # 检查各种属性
            if hasattr(chunk, '__dict__'):
                print(f"Dict: {chunk.__dict__}")
            
            if hasattr(chunk, 'content'):
                print(f"Content: {chunk.content}")
            
            if isinstance(chunk, dict):
                print(f"Keys: {list(chunk.keys())}")
        
        print("\n=== Testing execute method ===")
        response = agent.execute("Hello")
        print(f"Response length: {len(response)}")
        print(f"Response: {response}")
        
    except Exception as e:
        print("Error:", str(e))
        traceback.print_exc()

if __name__ == "__main__":
    debug_stream()