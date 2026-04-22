import json
import re

def zh_to_int(zh_str):
    """将中文数字转换成阿拉伯数字（支持1-199，满足大部分词牌长度需求）"""
    num_dict = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100}
    total = 0
    current = 0
    for char in zh_str:
        if char not in num_dict: continue
        val = num_dict[char]
        if val >= 10:
            if current == 0: current = 1
            total += current * val
            current = 0
        else:
            current = val
    return total + current

def get_expected_len(item):
    """从调式或简介中提取规定的字数"""
    # 优先找调式，例如 "双调六十六字"
    match = re.search(r'([一二三四五六七八九十百]+)字', item.get("调式", ""))
    if match: return zh_to_int(match.group(1))
    
    # 如果没找到（比如定格），去简介里找
    match = re.search(r'([一二三四五六七八九十百]+)字', item.get("简介", ""))
    if match: return zh_to_int(match.group(1))
    
    return None

def get_actual_len(pattern_str):
    """计算格律的实际汉字坑位数量（剔除标点符号）"""
    return len(re.sub(r'[,.\`|*$]', '', pattern_str))

def main():
    input_file = "词谱.json"
    output_file = "词谱_fixed2.json"
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"找不到文件 {input_file}，请确保脚本与 json 在同一目录下。")
        return

    fix_count = 0
    error_count = 0
    
    # 遍历所有词牌
    for cipai, variants in data.items():
        for i, variant in enumerate(variants):
            expected_len = get_expected_len(variant)
            if not expected_len:
                continue  # 无法推断字数，跳过
                
            original_pattern = variant.get("格律", "")
            if not original_pattern:
                continue
                
            actual_len = get_actual_len(original_pattern)
            
            # 校验逻辑：匹配自身，或者匹配双调的长度 (有些单调词谱给的是上下阕双份的格律)
            if actual_len == expected_len or actual_len == expected_len * 2:
                continue  # 字数本来就是对的，跳过
                
            # 字数不对，尝试按照你的规则修复
            fixed_pattern = original_pattern.replace('24', '4').replace('13', '3')
            new_actual_len = get_actual_len(fixed_pattern)
            
            if new_actual_len == expected_len or new_actual_len == expected_len * 2:
                # 修复成功！字数对齐了
                variant["格律"] = fixed_pattern
                fix_count += 1
                print(f"[修复成功] {cipai} (预期 {expected_len} 字):")
                print(f"  原格律: {original_pattern}")
                print(f"  新格律: {fixed_pattern}\n")
            else:
                # 修复后字数依然不对！严重错误，不进行修改
                error_count += 1
                print(f"❌ [无法修复的错误] {cipai} (预期 {expected_len} 字):")
                print(f"  原格律实际长度为 {actual_len}。")
                print(f"  即使替换 24/13，新长度为 {new_actual_len}，仍不等于 {expected_len}。")
                print(f"  格律串: {original_pattern}\n")

    if fix_count > 0:
        # 将清洗后的数据输出为一个新文件，以防破坏原始数据
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ 处理完成！成功修复 {fix_count} 处 '24/13' 手误。安全起见，已保存为 {output_file}")
    else:
        print("✅ 处理完成！没有需要修复的格式。")
        
    if error_count > 0:
        print(f"⚠️ 注意：发现了 {error_count} 处【无法自动修复】的严重错误（见上方红叉提示）。建议手动对照书籍排查原 JSON。")

if __name__ == "__main__":
    main()