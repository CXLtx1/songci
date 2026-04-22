import sqlite3
import json

# 导入你修复后的格律检测引擎
from songci_engine import SongCiEngine

# ==========================================
# 1. 配置区
# ==========================================
DB_NAME = "song_ci_research_B_2 Copy.db"

# 确保这三个文件路径正确
PATTERNS_PATH = "词谱.json"
RHYMES_PATH = "韵书.json"
CILIN_PATH = "词林正韵.json"

def main():
    print("⏳ 正在加载新版格律检测引擎...")
    try:
        engine = SongCiEngine(
            patterns_json_path=PATTERNS_PATH,
            rhymes_json_path=RHYMES_PATH,
            cilin_json_path=CILIN_PATH
        )
        print("✅ 引擎加载成功！")
    except Exception as e:
        print(f"❌ 引擎加载失败: {e}")
        return

    # 1. 连接数据库
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    # 2. 读取所有生成的词作
    # 我们只需要读取 id, cipai, content 这三个字段即可
    cursor.execute("SELECT id, cipai, title, content FROM ci_data WHERE content IS NOT NULL AND content != ''")
    records = cursor.fetchall()
    
    total = len(records)
    print(f"\n📦 共找到 {total} 条词作记录，开始重新评测...\n" + "="*50)

    success_count = 0
    error_count = 0

    # 3. 遍历重新打分并更新
    for idx, row in enumerate(records, 1):
        ci_id, cipai, title, content = row
        
        try:
            # 调用修复后引擎进行评估
            eval_result = engine.evaluate(content, cipai)
            new_score = eval_result.get("score", 0)
            new_errors = eval_result.get("summary",[])
            
            # 将新的错误列表转为 JSON 字符串
            errors_json = json.dumps(new_errors, ensure_ascii=False)
            
            # 执行 UPDATE 覆盖原有的 rhythm_score 和 rhythm_errors
            cursor.execute('''
                UPDATE ci_data 
                SET rhythm_score = ?, rhythm_errors = ?
                WHERE id = ?
            ''', (new_score, errors_json, ci_id))
            
            success_count += 1
            
            # 打印进度
            if new_score == 100:
                print(f"[{idx}/{total}] 🏆 ID:{ci_id} 《{title}》({cipai}) -> 完美 100 分！")
            else:
                print(f"[{idx}/{total}] 🔄 ID:{ci_id} 《{title}》({cipai}) -> 新得分: {new_score}，错误数: {len(new_errors)}")

        except Exception as e:
            error_count += 1
            print(f"[{idx}/{total}] ❌ ID:{ci_id} 评测出错: {e}")

    # 4. 提交事务并关闭连接
    print("\n" + "="*50)
    print("💾 正在将更新写入数据库...")
    conn.commit()
    conn.close()
    
    print(f"🎉 批量重新打分完成！成功更新 {success_count} 条，失败 {error_count} 条。")
    print("您可以打开 SQLite 查看最新的得分和错误详情了。")

if __name__ == "__main__":
    main()