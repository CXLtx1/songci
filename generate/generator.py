import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import sqlite3
import re
import random
from openai import AsyncOpenAI
from engine.songci_engine import SongCiEngine
import prompts

ENGINE_CONFIG = {
    "patterns_json_path": "engine/词谱.json",
    "rhymes_json_path": "engine/韵书.json",
    "cilin_json_path": "engine/词林正韵.json",
}

TASKS_FILE = "generate/tasks.json"

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    providers = config.get("providers", {})
    tasks = config.get("tasks", [])
    for task in tasks:
        provider_name = task.get("provider")
        if provider_name and provider_name in providers:
            provider = providers[provider_name]
            task["api_key"] = provider["api_key"]
            task["base_url"] = provider["base_url"]
    return tasks

def get_prompt(prompt_name, cipai_pool=None, theme=None):
    prompt_template = getattr(prompts, prompt_name, prompts.type_c)
    if "{cipai_name}" in prompt_template and cipai_pool:
        prompt_template = prompt_template.replace("{cipai_name}", random.choice(cipai_pool))
    if "{theme}" in prompt_template and theme:
        prompt_template = prompt_template.replace("{theme}", theme)
    return prompt_template

def init_db(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ci_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cipai TEXT,
            title TEXT,
            content TEXT,
            imagery TEXT,
            category TEXT,
            model_name TEXT,
            rhythm_score REAL,
            rhythm_errors TEXT,
            raw_response TEXT
        )
    ''')
    conn.commit()
    return conn

def insert_to_db(conn, data, raw_response, model_name, score, errors):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ci_data (cipai, title, content, imagery, category, model_name, rhythm_score, rhythm_errors, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get("cipai", ""), data.get("title", ""), data.get("content", ""),
        None, None, model_name, score,
        json.dumps(errors, ensure_ascii=False), raw_response
    ))
    conn.commit()

def parse_json_response(text):
    text = re.sub(r'<think.*?</think.*?>', '', text, flags=re.DOTALL | re.IGNORECASE)
    json_match = re.search(r'\{.*\}', text, flags=re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    return json.loads(text)

async def generate_single_task(task_id, client, engine, semaphore, db_conn, task_config):
    async with semaphore:
        prompt = get_prompt(
            task_config["prompt_name"], 
            task_config.get("cipai_pool"),
            task_config.get("theme")
        )
        
        try:
            response = await client.chat.completions.create(
                model=task_config["model"],
                messages=[{"role": "user", "content": prompt}],
                #extra_body={"enable_thinking": True}
            )
            raw_text = response.choices[0].message.content
            parsed_data = parse_json_response(raw_text)
            
            content = parsed_data.get("content", "")
            eval_result = engine.evaluate(content, parsed_data.get('cipai'))
            score = eval_result.get("score", 0)
            errors = eval_result.get("summary", [])
            
            insert_to_db(db_conn, parsed_data, raw_text, task_config["model"], score, errors)
            
            if score == 100:
                print(f"[{task_config['name']}][{task_id}] Perfect! 《{parsed_data.get('title')}》({parsed_data.get('cipai')}) score: 100")
            else:
                print(f"[{task_config['name']}][{task_id}] Saved! 《{parsed_data.get('title')}》({parsed_data.get('cipai')}) score: {score}, errors: {len(errors)}")
            
        except json.JSONDecodeError:
            print(f"[{task_config['name']}][{task_id}] JSON parse failed, skipped.")
        except Exception as e:
            print(f"[{task_config['name']}][{task_id}] Error: {str(e)}")

async def run_task(task_config, engine):
    print(f"\n{'='*60}")
    print(f"Starting task: {task_config['name']}")
    print(f"Model: {task_config['model']}")
    print(f"Prompt: {task_config['prompt_name']}")
    print(f"Database: {task_config['db_name']}")
    print(f"Requests: {task_config['total_requests']}")
    print(f"{'='*60}\n")
    
    client = AsyncOpenAI(api_key=task_config["api_key"], base_url=task_config["base_url"])
    db_conn = init_db(task_config["db_name"])
    semaphore = asyncio.Semaphore(task_config["max_concurrency"])
    
    tasks = []
    for i in range(task_config["total_requests"]):
        task = asyncio.create_task(
            generate_single_task(i+1, client, engine, semaphore, db_conn, task_config)
        )
        tasks.append(task)
        
        print(f"[{task_config['name']}] Scheduled request {i+1}/{task_config['total_requests']}")
        
        if i < task_config["total_requests"] - 1:
            await asyncio.sleep(task_config["request_interval"])
    
    print(f"\n[{task_config['name']}] All requests sent, waiting for completion...")
    await asyncio.gather(*tasks)
    
    db_conn.close()
    print(f"\n[{task_config['name']}] Task completed!")

async def main():
    print("Loading rhythm dictionaries...")
    engine = SongCiEngine(
        patterns_json_path=ENGINE_CONFIG["patterns_json_path"],
        rhymes_json_path=ENGINE_CONFIG["rhymes_json_path"],
        cilin_json_path=ENGINE_CONFIG["cilin_json_path"]
    )
    print("Rhythm dictionaries loaded!\n")
    
    tasks = load_tasks()
    print(f"Found {len(tasks)} tasks in tasks.json\n")
    
    for i, task_config in enumerate(tasks):
        print(f"\n>>> Task {i+1}/{len(tasks)}: {task_config['name']}")
        await run_task(task_config, engine)
    
    print("\n" + "="*60)
    print("ALL TASKS COMPLETED!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
