from flask import Flask, render_template, request, jsonify, send_file
import os
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from populate_database import add_to_chroma
from query_data import query_rag

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录
ROOT_DIR = os.path.dirname(current_dir)

app = Flask(__name__,
    template_folder=os.path.join(current_dir, 'templates'),
    static_folder=os.path.join(current_dir, 'static')
)

# 配置上传文件存储路径
UPLOAD_FOLDER = os.path.join(ROOT_DIR, 'data')
ALLOWED_EXTENSIONS = {'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename_custom(filename):
    """自定义的文件名安全处理函数"""
    # 保留原始文件名中的中文字符和常见标点符号
    allowed_chars = ".-_() "  # 允许的特殊字符
    filename = filename.replace('/', '_').replace('\\', '_')
    # 过滤掉不允许的字符，但保留中文
    return ''.join(c for c in filename if c.isalnum() or c.isspace() or c in allowed_chars or '\u4e00' <= c <= '\u9fff')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test')
def test():
    return "Test Route Working!"

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有文件被上传'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        # 使用自定义的文件名处理函数
        filename = secure_filename_custom(file.filename)
        if not filename:
            return jsonify({'error': '文件名无效'}), 400
            
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # 将文件添加到向量数据库
        try:
            loader = PyPDFLoader(file_path)
            pages = loader.load()
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            chunks = text_splitter.split_documents(pages)
            add_to_chroma(chunks)
        except Exception as e:
            print(f"Warning: Failed to process file for database: {str(e)}")
            # 继续执行，不中断上传流程
        
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
        print(f"Listing files in: {app.config['UPLOAD_FOLDER']}")  # 添加调试信息
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if filename.endswith('.pdf'):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_size = os.path.getsize(file_path)
                print(f"Found file: {filename}")  # 添加调试信息
                files.append({
                    'name': filename,
                    'size': file_size,
                    'uploadTime': os.path.getctime(file_path)
                })
        return jsonify(files)
    except Exception as e:
        print(f"List files error: {str(e)}")  # 添加调试信息
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
        
        # 打印调试信息
        print(f"Requested filename: {filename}")
        print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
        print(f"Files in upload folder: {os.listdir(app.config['UPLOAD_FOLDER'])}")
        
        # 不进行文件名处理，直接使用原始文件名
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        print(f"Trying to access file: {file_path}")
        
        if not os.path.exists(file_path):
            return jsonify({'error': f'文件不存在: {file_path}'}), 404
            
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename
        )
    except Exception as e:
        print(f"Preview error: {str(e)}")  # 打印错误信息
        return jsonify({'error': f'预览文件失败: {str(e)}'}), 500

if __name__ == '__main__':
    # 确保上传目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    print(f"Template folder: {app.template_folder}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    app.run(debug=True, port=8000) 