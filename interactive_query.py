from query_data import query_rag

def main():
    print("欢迎使用RAG查询系统！")
    print("您可以询问关于大富翁和车票之旅游戏规则的问题。")
    print("输入 'quit' 退出程序。")
    
    while True:
        question = input("\n请输入您的问题: ")
        if question.lower() == 'quit':
            break
            
        try:
            response = query_rag(question)
            print("\n回答:", response)
        except Exception as e:
            print(f"\n发生错误: {str(e)}")

if __name__ == "__main__":
    main() 