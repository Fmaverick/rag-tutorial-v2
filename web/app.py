from flask import Flask, render_template, request, jsonify, send_file
import os
from werkzeug.utils import secure_filename
from populate_database import add_to_chroma
from query_data import query_rag
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录
ROOT_DIR = os.path.dirname(current_dir)

app = Flask(__name__,
    template_folder=os.path.join(current_dir, 'templates'),  # 指定模板目录
    static_folder=os.path.join(current_dir, 'static')       # 指定静态文件目录
)

# 配置上传文件存储路径
UPLOAD_FOLDER = os.path.join(ROOT_DIR, 'data')
ALLOWED_EXTENSIONS = {'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Error loading template: {str(e)}")  # 添加调试信息
        return f"Error: {str(e)}"

@app.route('/test')
def test():
    return "Test Route Working!"

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({'error': '没有文件被上传'}), 400
        
        file = request.files['file']
        
        # 检查文件名是否为空
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件类型
        if not allowed_file(file.filename):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        # 安全地获取文件名并保存文件
        filename = secure_filename(file.filename)
        
        # 确保目录存在
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # 加载PDF文件并分割文本
        loader = PyPDFLoader(file_path)
        pages = loader.load()
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = text_splitter.split_documents(pages)
        
        # 将分割后的文档添加到向量数据库
        add_to_chroma(chunks)
        
        return jsonify({'message': '文件上传成功！'})
    except Exception as e:
        return jsonify({'error': f'处理文件时出错: {str(e)}'}), 500

@app.route('/query', methods=['POST'])
def query():
    try:
        data = request.get_json()
        question = data.get('question', '')
        if not question:
            return jsonify({'error': '问题不能为空'}), 400
            
        response = query_rag(question)
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': f'查询时出错: {str(e)}'}), 500

@app.route('/files', methods=['GET'])
def list_files():
    try:
        files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if filename.endswith('.pdf'):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_size = os.path.getsize(file_path)
                files.append({
                    'name': filename,
                    'size': file_size,
                    'uploadTime': os.path.getctime(file_path)
                })
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': f'获取文件列表失败: {str(e)}'}), 500

@app.route('/files/<filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        if not allowed_file(filename):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'message': '文件删除成功'})
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': f'删除文件失败: {str(e)}'}), 500

@app.route('/preview/<filename>')
def preview_file(filename):
    try:
        if not allowed_file(filename):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        # 使用正确的文件路径
        file_path = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
        print(f"Trying to access file: {file_path}")  # 添加调试信息
        
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
            
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': f'预览文件失败: {str(e)}'}), 500

if __name__ == '__main__':
    # 打印调试信息
    print(f"Template folder: {app.template_folder}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    
    # 确保必要的目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(app.template_folder, exist_ok=True)
    
    app.run(debug=True, port=8000) 