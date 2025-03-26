from flask import Flask, render_template, request, jsonify, send_file
import os
import sys
import json

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# 导入其他模块
from populate_database import add_to_chroma
from query_data import query_rag
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain_community.llms import OpenAI
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

app = Flask(__name__,
    template_folder=os.path.join(current_dir, 'templates'),
    static_folder=os.path.join(current_dir, 'static')
)

# 配置上传文件存储路径
UPLOAD_FOLDER = os.path.join(root_dir, 'data')
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
        data = request.json
        question = data.get('question', '')
        
        # 检查是否有上传的文档
        if not has_uploaded_documents():
            return jsonify({
                'answer': '请先上传 PDF 文档，我才能帮助回答问题。'
            })
        
        # 获取答案和源文档
        result = qa_chain({"query": question})
        
        # 如果答案中包含"抱歉"或"找不到"等词，说明文档中没有相关信息
        if any(phrase in result['result'].lower() for phrase in ["抱歉", "找不到", "无法"]):
            return jsonify({
                'answer': '抱歉，我在当前上传的文档中找不到相关信息。请确保您的问题与文档内容相关。'
            })
            
        # 构造响应
        response = {
            'answer': result['result'],
            'source': '基于文档内容的回答'
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"查询处理出错: {str(e)}")
        return jsonify({
            'answer': '抱歉，处理您的问题时出现错误。请稍后再试。',
            'error': str(e)
        })

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

@app.route('/get_files', methods=['GET'])
def get_files():
    """获取文件列表的API端点"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        record_path = os.path.join(upload_folder, '.records.json')
        
        # 如果记录文件不存在，创建空记录
        if not os.path.exists(record_path):
            with open(record_path, 'w') as f:
                json.dump([], f)
            return jsonify({'files': []})
            
        # 读取并验证文件列表
        with open(record_path, 'r') as f:
            records = json.load(f)
            
        # 只保留实际存在的文件记录
        valid_records = []
        for record in records:
            file_path = os.path.join(upload_folder, record['filename'])
            if os.path.exists(file_path):
                valid_records.append(record)
        
        # 更新记录文件
        with open(record_path, 'w') as f:
            json.dump(valid_records, f)
            
        return jsonify({'files': valid_records})
    except Exception as e:
        print(f"获取文件列表时出错: {str(e)}")
        # 出错时返回空列表，避免前端报错
        return jsonify({'files': []})

@app.route('/delete_file', methods=['POST'])
def delete_file():
    """删除文件的API端点"""
    try:
        data = request.json
        filename = data.get('filename')
        
        upload_folder = app.config['UPLOAD_FOLDER']
        file_path = os.path.join(upload_folder, filename)
        record_path = os.path.join(upload_folder, '.records.json')
        
        # 删除物理文件（如果存在）
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # 更新记录文件
        if os.path.exists(record_path):
            with open(record_path, 'r') as f:
                records = json.load(f)
            # 过滤掉要删除的文件记录
            records = [r for r in records if r['filename'] != filename]
            with open(record_path, 'w') as f:
                json.dump(records, f)
        
        return jsonify({
            'success': True,
            'message': f'文件 {filename} 已删除',
            'files': records  # 返回更新后的文件列表
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'删除失败：{str(e)}'
        })

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

# 添加一个初始化函数来清理文件记录
def initialize_file_records():
    """初始化并清理文件记录"""
    upload_folder = app.config['UPLOAD_FOLDER']
    record_path = os.path.join(upload_folder, '.records.json')
    
    try:
        # 如果记录文件存在，删除它
        if os.path.exists(record_path):
            os.remove(record_path)
            
        # 创建新的空记录文件
        with open(record_path, 'w') as f:
            json.dump([], f)
            
        print("文件记录已重置")
    except Exception as e:
        print(f"重置文件记录时出错: {str(e)}")

@app.route('/reset_files', methods=['POST'])
def reset_files():
    """重置文件记录的API端点"""
    try:
        initialize_file_records()
        return jsonify({
            'success': True,
            'message': '文件记录已重置',
            'files': []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'重置失败：{str(e)}'
        })

# 修改 QA 系统配置
def setup_qa_system():
    # 1. 更严格的相似度阈值
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 3,  # 减少返回的文档数量
            "score_threshold": 0.7  # 提高相似度阈值
        }
    )
    
    # 2. 更明确的 prompt 模板
    prompt_template = """使用以下已知信息来回答问题。如果无法从提供的信息中找到答案，请直接说"抱歉，我在文档中找不到相关信息"。
    不要编造或推测任何文档中没有的信息。

    已知信息:
    {context}

    问题: {question}

    请只基于上述信息回答。如果信息不足，请直接说明。"""
    
    PROMPT = PromptTemplate(
        template=prompt_template, 
        input_variables=["context", "question"]
    )
    
    # 3. 配置 QA 链
    chain_type_kwargs = {
        "prompt": PROMPT,
        "verbose": True
    }
    
    qa_chain = RetrievalQA.from_chain_type(
        llm=OpenAI(temperature=0),  # 降低创造性，提高准确性
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs=chain_type_kwargs,
        return_source_documents=True  # 返回源文档信息
    )
    
    return qa_chain

if __name__ == '__main__':
    # 确保上传目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    print(f"Template folder: {app.template_folder}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    app.run(debug=True, port=8000) 