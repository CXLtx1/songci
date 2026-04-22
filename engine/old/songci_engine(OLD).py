import json
import re

class SongCiEngine:
    def __init__(self, patterns_json_path, rhymes_json_path, cilin_json_path):
        """
        初始化宋词格律校验引擎
        """
        self.pattern_variants = {}
        self.rhyme_dict = {"平": [], "上":[], "去": [], "入":[]}
        self.rhyme_name_map = {}
        self.cilin_groups =[]
        
        self.RULE_LABEL = {"0": "可平可仄", "1": "须平", "2": "须仄"}
        
        self._load_data(patterns_json_path, rhymes_json_path, cilin_json_path)

    def _load_data(self, p_path, r_path, c_path):
        # 1. 加载词谱
        with open(p_path, 'r', encoding='utf-8') as f:
            patterns = json.load(f)
            for name, var_list in patterns.items():
                self.pattern_variants[name] =[{
                    "source": v.get("所属词谱", ""),
                    "mode": v.get("调式", "定格"),
                    "pattern": v.get("格律", "")
                } for v in var_list]
                
        # 2. 加载平水韵
        with open(r_path, 'r', encoding='utf-8') as f:
            rhymes = json.load(f)
            for key, chars in rhymes.items():
                tone = key[0] if key[0] in "平上去入" else None
                if not tone: continue
                
                # 提取韵目名称，例如 "平声一东" -> "一东" 或 "东" (按原逻辑去除前缀)
                name_match = re.sub(r'^(平|上|去|入)声[一二三四五六七八九十百]+', '', key).strip()
                yunmu_name = name_match if name_match else key
                
                char_set = set(c for c in chars.strip() if c.strip())
                if not char_set: continue
                
                self.rhyme_dict[tone].append(char_set)
                self.rhyme_name_map[yunmu_name] = char_set

        # 3. 加载词林正韵表
        with open(c_path, 'r', encoding='utf-8') as f:
            cilin = json.load(f)
            tone_map = {"平声": "平", "上声": "上", "去声": "去", "入声": "入"}
            for row in cilin:
                label = row.get("韵部名称", "").strip()
                tone_zh = row.get("声调", "").strip()
                yunmu_raw = row.get("韵目", "").strip()
                tone = tone_map.get(tone_zh)
                if not tone: continue
                
                # 解析韵目，去除"（半）"和"韵"
                yunmus =[re.sub(r'（[^）]*）', '', s).replace('韵', '').strip() for s in yunmu_raw.split('、')]
                yunmus = [y for y in yunmus if y]
                
                merged = set()
                found =[]
                for ym in yunmus:
                    if ym in self.rhyme_name_map:
                        merged.update(self.rhyme_name_map[ym])
                        found.append(ym)
                        
                if merged:
                    self.cilin_groups.append({
                        "label": label, "tone": tone, "yunmus": found,
                        "chars": merged, "single": len(found) <= 1
                    })

    # ================= 基本查询逻辑 =================

    def lookup_rhyme_all(self, char):
        """返回该字在平水韵中的所有 (声调, 字符集) 组合"""
        results =[]
        for tone, groups in self.rhyme_dict.items():
            for group in groups:
                if char in group:
                    results.append((tone, group))
        return results

    def find_cilin_entry(self, char, tone):
        """查找字在词林正韵中的宽韵部"""
        for entry in self.cilin_groups:
            if entry["tone"] == tone and char in entry["chars"]:
                return entry
        return None

    def get_yunmu_name(self, char, tone):
        """获取窄韵（平水韵）韵目名称"""
        for t, groups in self.rhyme_dict.items():
            if t != tone: continue
            for grp in groups:
                if char in grp:
                    for name, chars in self.rhyme_name_map.items():
                        if chars == grp:
                            return name
        # 降级匹配
        for name, chars in self.rhyme_name_map.items():
            if char in chars:
                return name
        return "?"

    def pick_rhyme_reading(self, char, should_flat, slot):
        """为韵脚的多音字选择最合适的读音 (优先顺应格律和已有韵部)"""
        readings = self.lookup_rhyme_all(char)
        if not readings: return None, None, ""
        
        is_multi = len(readings) > 1
        def note(t): return f"（多音字，取{t}声读）" if is_multi else ""
        
        # 筛选符合格律平仄要求的读音
        tone_ok = [r for r in readings if (r[0] == "平") == should_flat]
        
        if not slot:
            pick = tone_ok[0] if tone_ok else readings[0]
            return pick[0], pick[1], note(pick[0])
            
        # 1. 尝试完全命中窄韵(平水韵)
        for r in tone_ok:
            if char in slot["group"]:
                return r[0], r[1], note(r[0])
                
        # 2. 尝试命中宽韵(词林正韵通押)
        for r in tone_ok:
            char_cilin = self.find_cilin_entry(char, r[0])
            anchor = next(iter(slot["group"])) if slot["group"] else char
            ref_cilin = self.find_cilin_entry(anchor, r[0])
            if char_cilin and ref_cilin and char_cilin["label"] == ref_cilin["label"]:
                return r[0], r[1], note(r[0])
                
        # 3. 降级：只要平仄符合即可
        if tone_ok:
            return tone_ok[0][0], tone_ok[0][1], note(tone_ok[0][0])
            
        return readings[0][0], readings[0][1], note(readings[0][0])

    # ================= 核心打分引擎 =================

    def validate_prosody(self, ci_text, pattern_str):
        """针对单一格律字符串进行校验与打分"""
        unmarked = re.sub(r'[,.\`|*$]', '', pattern_str)
        raw_chars = re.findall(r'[\u4e00-\u9fa5\u3007]', ci_text)
        req, actual = len(unmarked), len(raw_chars)
        
        # 长度强校验
        if actual != req:
            return {
                "valid": False, "score": 0, "totalChars": actual,
                "errorCount": 1, "warnCount": 0, "rhymeGroupLabel": "",
                "summary":[f"字数不符：词牌要求 {req} 字，实际 {actual} 字，相差 {abs(req - actual)} 字"]
            }
            
        # 解析断句规则
        sentences =[]
        cur_rules = []
        for pc in re.sub(r'[|*]', '', pattern_str):
            if pc in ",.`":
                sentences.append({"ruleChars": cur_rules, "punct": pc})
                cur_rules =[]
            else:
                cur_rules.append(pc)
        if cur_rules:
            sentences.append({"ruleChars": cur_rules, "punct": ""})

        total_penalty = 0
        error_count = 0
        warn_count = 0
        summary_errors =[]
        char_idx = 0
        
        rhyme_slots = {}
        rhyme_group_label = ""
        
        # 逐字校验
        for sent in sentences:
            for rule in sent["ruleChars"]:
                if char_idx >= len(raw_chars): break
                char = raw_chars[char_idx]
                char_idx += 1
                
                rule_int = int(rule)
                is_rhyme = rule_int >= 3
                
                all_readings = self.lookup_rhyme_all(char)
                is_multi_tone = len(all_readings) > 1
                
                if not all_readings:
                    warn_count += 1
                    #total_penalty += 2  # 生僻字/现代字扣分
                    summary_errors.append(f"「{char}」未收录于平水韵（已跳过该字校验，不扣分）")
                    continue
                
                # --- 非韵脚位置 ---
                if not is_rhyme:
                    prefer_flat = True if rule == "1" else (False if rule == "2" else None)
                    if prefer_flat is None or len(all_readings) == 1:
                        tone, _ = all_readings[0]
                    else:
                        matching =[r for r in all_readings if (r[0] == "平") == prefer_flat]
                        tone, _ = matching[0] if matching else all_readings[0]
                        
                    is_flat = (tone == "平")
                    multi_note = f"（多音字，取{tone}声读）" if is_multi_tone else ""
                    
                    if rule == "1":
                        if not is_flat:
                            error_count += 1; total_penalty += 3
                            summary_errors.append(f"「{char}」{tone}声（仄）{multi_note}，此处须填平声字")
                    elif rule == "2":
                        if is_flat:
                            error_count += 1; total_penalty += 3
                            summary_errors.append(f"「{char}」{tone}声（平）{multi_note}，此处须填仄声字")
                    continue
                
                # --- 韵脚位置 ---
                should_flat = (rule_int % 2 == 1)
                slot = rhyme_slots.get(rule_int)
                
                tone, rhyme_group, multi_note = self.pick_rhyme_reading(char, should_flat, slot)
                is_flat = (tone == "平")
                
                if is_flat != should_flat:
                    error_count += 1; total_penalty += 4
                    exp = "平声" if should_flat else "仄声"
                    summary_errors.append(f"「{char}」{tone}声{multi_note}，此韵脚须{exp}")
                    continue
                    
                if not slot:
                    # 确立首韵
                    ynm = self.get_yunmu_name(char, tone)
                    rhyme_slots[rule_int] = {
                        "group": rhyme_group, "yunmuName": ynm,
                        "cilinEntry": None, "usedCilin": False
                    }
                    if not rhyme_group_label:
                        rhyme_group_label = f"平水韵·{ynm}韵"
                else:
                    # 校验通押
                    strict_reading = next((r for r in all_readings if (r[0] == "平") == should_flat and char in r[1]), None)
                    if strict_reading:
                        pass # 完全押韵
                    else:
                        if not slot["cilinEntry"]:
                            anchor = next(iter(slot["group"])) if slot["group"] else char
                            # 优化了原前端硬编码“上”声找词林正韵的Bug，改为遍历查找原韵字所在的宽韵部
                            for t_test in (["平"] if should_flat else ["上", "去", "入"]):
                                slot["cilinEntry"] = self.find_cilin_entry(anchor, t_test)
                                if slot["cilinEntry"]: break
                                
                        cilin_matched = False
                        for r in all_readings:
                            if (r[0] == "平") != should_flat: continue
                            char_cilin = self.find_cilin_entry(char, r[0])
                            anchor = next(iter(slot["group"])) if slot["group"] else char
                            ref_cilin = slot["cilinEntry"] or self.find_cilin_entry(anchor, r[0])
                            
                            if char_cilin and ref_cilin and char_cilin["label"] == ref_cilin["label"]:
                                slot["usedCilin"] = True
                                slot["cilinEntry"] = char_cilin
                                if not rhyme_group_label or "平水韵" in rhyme_group_label:
                                    rhyme_group_label = char_cilin["label"]
                                cilin_matched = True
                                break
                                
                        if not cilin_matched:
                            error_count += 1; total_penalty += 5
                            char_ym = self.get_yunmu_name(char, tone)
                            summary_errors.append(f"「{char}」{multi_note}出韵：属{char_ym}韵，应押{slot['yunmuName']}韵")
                            
        score = max(0, 100 - total_penalty * 4)
        return {
            "valid": score >= 60,
            "score": score,
            "errorCount": error_count,
            "warnCount": warn_count,
            "rhymeGroupLabel": rhyme_group_label,
            "summary": summary_errors
        }

    def evaluate(self, ci_text, pattern_name):
        """
        对外主入口：自动匹配最佳变体调式并返回最高分
        """
        clean_text = re.sub(r'[\s\r\n]', '', ci_text)
        variants = self.pattern_variants.get(pattern_name,[])
        if not variants:
            return {"valid": False, "score": 0, "summary": ["未找到该词牌或无格律数据"]}
            
        best_result = None
        best_score = -1
        
        for v in variants:
            pat = v.get("pattern", "")
            if not pat: continue
            
            result = self.validate_prosody(clean_text, pat)
            
            # 贪心保留得分最高的调式结果
            if result["score"] > best_score or (result["score"] == best_score and best_result and result["errorCount"] < best_result["errorCount"]):
                best_score = result["score"]
                best_result = result
                best_result["matchedVariant"] = v
                
        if not best_result:
            return {"valid": False, "score": 0, "summary": ["所有格律均无法校验"]}
            
        best_result["patternName"] = pattern_name
        return best_result