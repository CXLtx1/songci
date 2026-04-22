import asyncio
import json
import sqlite3
import re
from openai import AsyncOpenAI

CONFIG = {
    "api_key": "NONE",    
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "model": "doubao-seed-2-0-pro-260215",                
    "batch_size": 3,
    "request_interval": 0.5,
    "max_concurrency": 20,
    "db_name": "database/c2.db",
}

EXTRACT_PROMPT = """你是一位精通宋词的中国古典文学专家。
我给你三首宋词，请你分别提取每首词的意象和种类。

【宋词1】
{content1}

【宋词2】
{content2}

【宋词3】
{content3}

【输出要求】
你必须严格输出且仅输出合法的 JSON 数组格式数据，不要包含任何额外的解释、问候或 markdown 标记。

【字段及约束说明】
1. "id": 词的编号（1、2、3）
2. "imagery" (数组): 提取词中使用的核心意象。必须是2-3个字的名词性短语（如："残月", "东风", "落花"），提取词中出现的所有意象，不能遗漏。
3. "category" (字符串): 词的种类。**必须且只能**从以下列表中选择最贴切的一个：["离别羁旅", "怀古咏史", "咏物寄托", "春怨秋悲", "山水田园", "豪情壮志", "闲适隐逸", "悼亡相思", "谈禅说理"]

【示例输出】
[
  {{"id": 1, "imagery": ["夜雨", "残酒", "海棠"], "category": "春怨秋悲"}},
  {{"id": 2, "imagery": ["明月", "西楼"], "category": "悼亡相思"}},
  {{"id": 3, "imagery": ["青山", "绿水"], "category": "山水田园"}}
]

现在，请开始分析。"""

def get_all_pending_poems(conn):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, cipai, title, content 
        FROM ci_data 
        WHERE (imagery IS NULL OR imagery = '') 
        AND (category IS NULL OR category = '')
        AND content IS NOT NULL 
        AND content != ''
    ''')
    return cursor.fetchall()

def update_poem_imagery(conn, poem_id, imagery, category):
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ci_data 
        SET imagery = ?, category = ? 
        WHERE id = ?
    ''', (json.dumps(imagery, ensure_ascii=False) if imagery else None, category, poem_id))
    conn.commit()

def get_pending_count(conn):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) 
        FROM ci_data 
        WHERE (imagery IS NULL OR imagery = '') 
        AND (category IS NULL OR category = '')
        AND content IS NOT NULL 
        AND content != ''
    ''')
    return cursor.fetchone()[0]

def parse_json_response(text):
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = re.sub(r'<think.*?</think.*?>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = text.strip()
    
    if text.startswith('[') and text.endswith(']'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    
    if text.startswith('{') and text.endswith('}'):
        try:
            return [json.loads(text)]
        except json.JSONDecodeError:
            pass
    
    bracket_count = 0
    start_idx = None
    for i, char in enumerate(text):
        if char == '[':
            if start_idx is None:
                start_idx = i
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0 and start_idx is not None:
                json_str = text[start_idx:i+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    start_idx = None
                    continue
    
    raise ValueError(f"无法从响应中提取有效JSON")

async def extract_batch_task(task_id, client, semaphore, db_conn, poems):
    async with semaphore:
        contents = [p[3] for p in poems]
        while len(contents) < 3:
            contents.append("无")
        
        prompt = EXTRACT_PROMPT.format(
            content1=contents[0],
            content2=contents[1],
            content3=contents[2]
        )
        
        try:
            response = await client.chat.completions.create(
                model=CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            
            raw_text = response.choices[0].message.content
            parsed_list = parse_json_response(raw_text)
            
            for i, poem in enumerate(poems):
                poem_id, cipai, title, content = poem
                
                result = None
                for item in parsed_list:
                    if isinstance(item, dict) and item.get("id") == i + 1:
                        result = item
                        break
                
                if result is None and i < len(parsed_list):
                    result = parsed_list[i]
                
                if result:
                    imagery = result.get("imagery", [])
                    category = result.get("category", "")
                    update_poem_imagery(db_conn, poem_id, imagery, category)
                    print(f"[Task {task_id}][ID:{poem_id}] 《{title}》({cipai}) - 意象:{len(imagery)}个, 种类:{category}")
                else:
                    print(f"[Task {task_id}][ID:{poem_id}] 《{title}》({cipai}) - 未找到解析结果")
            
        except Exception as e:
            for poem in poems:
                poem_id, cipai, title, content = poem
                print(f"[Task {task_id}][ID:{poem_id}] 提取失败: {str(e)}")

async def main():
    client = AsyncOpenAI(api_key=CONFIG["api_key"], base_url=CONFIG["base_url"])
    db_conn = sqlite3.connect(CONFIG["db_name"])
    
    print("="*60)
    print("[宋词意象与种类提取程序] 启动！")
    print("="*60)
    
    pending_count = get_pending_count(db_conn)
    print(f"\n待处理诗词: {pending_count} 首")
    
    all_poems = get_all_pending_poems(db_conn)
    
    if not all_poems:
        print("未获取到待处理诗词，退出")
        db_conn.close()
        return
    
    batch_count = (len(all_poems) + CONFIG["batch_size"] - 1) // CONFIG["batch_size"]
    print(f"共 {len(all_poems)} 首，分为 {batch_count} 个批次")
    print(f"每 {CONFIG['request_interval']} 秒发送一个请求，最大并发: {CONFIG['max_concurrency']}")
    
    semaphore = asyncio.Semaphore(CONFIG["max_concurrency"])
    tasks = []
    
    for i in range(0, len(all_poems), CONFIG["batch_size"]):
        batch_poems = all_poems[i:i + CONFIG["batch_size"]]
        task_id = i // CONFIG["batch_size"] + 1
        
        task = asyncio.create_task(
            extract_batch_task(task_id, client, semaphore, db_conn, batch_poems)
        )
        tasks.append(task)
        
        print(f"已调度批次 {task_id}/{batch_count}")
        
        if i + CONFIG["batch_size"] < len(all_poems):
            await asyncio.sleep(CONFIG["request_interval"])
    
    print(f"\n所有请求已发出，等待处理完成...")
    await asyncio.gather(*tasks)
    
    db_conn.close()
    print("\n程序执行完毕！")

if __name__ == "__main__":
    asyncio.run(main())
