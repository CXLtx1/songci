import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.songci_engine import SongCiEngine

if __name__ == "__main__":
    #1. 实例化引擎（载入你的 JSON 文件路径）
    engine = SongCiEngine(
        patterns_json_path="engine/词谱.json",
        rhymes_json_path="engine/韵书.json",
        cilin_json_path="engine/词林正韵.json"
    )
    
    # 2. 模拟一条 AI 生成的词
    ai_generated_ci = """孤鹤归飞，再过辽天，换尽旧人。念累累枯冢，茫茫梦境，王侯蝼蚁，毕竟成尘。载酒园林，寻花巷陌，当日何曾轻负春。流年改，叹围腰带剩，点鬓霜新。
交亲零落如云，又岂料如今馀此身。幸眼明身健，茶甘饭软，非惟我老，更有人贫。躲尽危机，消残壮志，短艇湖中闲采莼。吾何恨，有渔翁共醉，溪友为邻。"""
    
    # 3. 进行打分
    result = engine.evaluate(ai_generated_ci, "沁园春")
    
    # 4. 输出评估报告
    print(f"词牌：{result['patternName']}")
    print(f"最终得分：{result['score']} / 100")
    print(f"押韵情况：{result['rhymeGroupLabel']}")
    #print(f"匹配调式：{result['matchedVariant']['source']} - {result['matchedVariant']['mode']}")
    
    if result['score'] < 100:
        print("\n扣分详情：")
        for err in result['summary']:
            print(f"- {err}")