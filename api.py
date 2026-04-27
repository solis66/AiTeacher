from flask import Flask, request, jsonify
from agent.tools.react_agent import ReactAgent
import time

app = Flask(__name__)

# 初始化ReactAgent
agent = ReactAgent()

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        # 调用ReactAgent的execute_stream方法
        response = ''
        for chunk in agent.execute_stream(message):
            response += chunk
        
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8501, debug=True)