from flask import Flask, render_template, request, jsonify
import os
from werkzeug.utils import secure_filename
from populate_database import add_to_chroma
from query_data import query_rag

app = Flask(__name__)

# 配置上传文件存储路径
UPLOAD_FOLDER = 'data'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件被上传'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 处理上传的文件
        try:
            add_to_chroma([filepath])
            return jsonify({'message': '文件上传成功并已添加到知识库'})
        except Exception as e:
            return jsonify({'error': f'处理文件时出错: {str(e)}'}), 500
    
    return jsonify({'error': '不支持的文件类型'}), 400

@app.route('/query', methods=['POST'])
def query():
    data = request.json
    question = data.get('question')
    
    if not question:
        return jsonify({'error': '问题不能为空'}), 400
    
    try:
        answer = query_rag(question)
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': f'查询时出错: {str(e)}'}), 500

@app.route('/files', methods=['GET'])
def list_files():
    """列出所有上传的PDF文件"""
    try:
        # 确保上传文件夹存在
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        # 获取所有PDF文件
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        pdf_files = [f for f in files if f.endswith('.pdf')]
        
        # 为每个文件添加更多信息
        files_info = []
        for file in pdf_files:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file)
            file_info = {
                'name': file,
                'size': os.path.getsize(file_path) // 1024,  # 转换为KB
                'upload_time': os.path.getctime(file_path)  # 获取创建时间
            }
            files_info.append(file_info)
            
        return jsonify({'files': files_info})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001) 