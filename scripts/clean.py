import json
import re

def merge_pingshui(file1_path, file2_path, output_path):
    # 1. 加载两个 JSON 文件
    try:
        with open(file1_path, 'r', encoding='utf-8') as f1:
            data1 = json.load(f1)
        with open(file2_path, 'r', encoding='utf-8') as f2:
            data2 = json.load(f2)
    except FileNotFoundError as e:
        print(f"错误：找不到文件 - {e}")
        return

    # 2. 获取所有韵部的并集
    all_keys = set(data1.keys()).union(set(data2.keys()))
    
    merged_result = {}

    # 定义一个内部函数用来合并字符串并去重，同时保持顺序
    def combine_and_unique(s1, s2):
        combined = s1 + s2
        seen = set()
        unique_chars = []
        for char in combined:
            # 只保留中文字符，并过滤掉重复项
            if '\u4e00' <= char <= '\u9fa5' and char not in seen:
                seen.add(char)
                unique_chars.append(char)
        return "".join(unique_chars)

    # 3. 遍历所有韵部进行合并
    for key in all_keys:
        str1 = data1.get(key, "")
        str2 = data2.get(key, "")
        
        # 合并内容
        merged_content = combine_and_unique(str1, str2)
        merged_result[key] = merged_content

    # 4. 排序：按照平水韵的常规顺序（平、上、去、入）对 Key 进行简单排序
    # 如果不需要排序，可以直接用 merged_result
    sorted_keys = sorted(merged_result.keys()) 
    final_data = {k: merged_result[k] for k in sorted_keys}

    # 5. 保存结果
    with open(output_path, 'w', encoding='utf-8') as f_out:
        json.dump(final_data, f_out, ensure_ascii=False, indent=4)
    
    print(f"合并完成！已生成：{output_path}")
    print(f"总韵部数量：{len(final_data)}")

# 执行合并
if __name__ == "__main__":
    # 请确保这两个文件名正确
    merge_pingshui('engine/韵书.json', 'engine/韵书(OLD).json', 'engine/merged_pingshui.json')