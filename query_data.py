import argparse
from langchain_community.vectorstores import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain_community.llms.ollama import Ollama

from get_embedding_function import get_embedding_function

CHROMA_PATH = "chroma"

PROMPT_TEMPLATE = """
Answer the question based only on the following context:

{context}

---

Answer the question based on the above context: {question}
"""


def query_rag(question: str) -> str:
    # 准备数据库
    embedding_function = get_embedding_function()
    db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embedding_function)

    # 搜索相关文档
    results = db.similarity_search_with_score(question, k=3)

    # 准备上下文
    context_text = "\n\n---\n\n".join([doc.page_content for doc, _score in results])
    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的游戏规则解释助手。请仔细阅读以下游戏规则文档，并基于文档内容回答问题。如果文档中没有相关信息，请明确说明。\n\n{context}"),
        ("human", "{question}")
    ])

    # 生成回答
    chain = chat_prompt | Ollama(model="mistral")
    response = chain.invoke({"context": context_text, "question": question})
    return response  # 直接返回 response，因为它已经是字符串了


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("question", type=str, help="The question to ask")
    args = parser.parse_args()

    print(query_rag(args.question))
