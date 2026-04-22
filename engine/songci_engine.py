import json
import re

class SongCiEngine:
    def __init__(self, patterns_json_path, rhymes_json_path, cilin_json_path):
        """
        初始化宋词格律校验引擎 (适配新版 Ci_Tunes.json 格式)
        """
        ci_tunes_path=patterns_json_path
        self.pattern_variants = {}
        self.rhyme_dict = {"平": [], "上": [], "去": [], "入":[]}
        self.rhyme_name_map = {}
        self.cilin_groups =[]
        
        self.RULE_LABEL = {"中": "可平可仄", "平": "须平", "仄": "须仄"}
        
        self._load_data(ci_tunes_path, rhymes_json_path, cilin_json_path)

    def _load_data(self, p_path, r_path, c_path):
        # 1. 加载新版结构化词谱 (Ci_Tunes.json)
        with open(p_path, 'r', encoding='utf-8') as f:
            patterns = json.load(f)
            for name, data in patterns.items():
                self.pattern_variants[name] = []
                for fmt in data.get("formats",[]):
                    self.pattern_variants[name].append({
                        "author": fmt.get("author", "未知"),
                        "sketch": fmt.get("sketch", "定格"),
                        "desc": fmt.get("desc", ""),
                        "tunes": fmt.get("tunes",[]) # 这是一个结构化的 List[Dict]
                    })
                
        # 2. 加载平水韵
        with open(r_path, 'r', encoding='utf-8') as f:
            rhymes = json.load(f)
            for key, chars in rhymes.items():
                tone = key[0] if key[0] in "平上去入" else None
                if not tone: continue
                
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
        results =[]
        for tone, groups in self.rhyme_dict.items():
            for group in groups:
                if char in group:
                    results.append((tone, group))
        return results

    def find_cilin_entry(self, char, tone):
        for entry in self.cilin_groups:
            if entry["tone"] == tone and char in entry["chars"]:
                return entry
        return None

    def get_yunmu_name(self, char, tone):
        for t, groups in self.rhyme_dict.items():
            if t != tone: continue
            for grp in groups:
                if char in grp:
                    for name, chars in self.rhyme_name_map.items():
                        if chars == grp:
                            return name
        for name, chars in self.rhyme_name_map.items():
            if char in chars:
                return name
        return "?"

    def pick_rhyme_reading(self, char, should_flat, slot):
        readings = self.lookup_rhyme_all(char)
        if not readings: return None, None, ""
        
        is_multi = len(readings) > 1
        def note(t): return f"（多音字，取{t}声读）" if is_multi else ""
        
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

    def validate_prosody(self, ci_text, tunes):
        """针对新版结构化 tunes (List[Dict]) 进行校验与打分"""
        
        # 使用正则提取所有的纯汉字（保留之前优化：过滤所有标点和非汉字字符）
        raw_chars = re.findall(r'[\u4e00-\u9fa5\u3007]', ci_text)
        
        req = len(tunes)
        actual = len(raw_chars)
        
        # 字数校验
        if actual != req:
            return {
                "valid": False, "score": 0, "totalChars": req,
                "errorCount": 1, "warnCount": 0, "rhymeGroupLabel": "",
                "summary":[f"字数不符：该变体要求 {req} 字，实际 {actual} 字，相差 {abs(req - actual)} 字"]
            }

        total_penalty = 0
        error_count = 0
        warn_count = 0
        summary_errors =[]
        
        # 将平韵和仄韵的槽位分开存储（为了兼容一首词中既有平韵又有仄韵的情况）
        # Key: True 表示平韵槽，False 表示仄韵槽
        rhyme_slots = {} 
        rhyme_group_label = ""
        
        sentences =[]
        current_sent = {"chars":[], "punct": ""}
        
        for char_idx, rule_item in enumerate(tunes):
            char = raw_chars[char_idx]
            
            # 解析结构化规则
            rule_tune = rule_item.get("tune", "中") # 平/仄/中
            is_rhyme = rule_item.get("rhythm") == "韵"
            is_ju = rule_item.get("rhythm") == "句"
            is_shift = str(rule_item.get("shift", "")).lower() == "true"
            
            all_readings = self.lookup_rhyme_all(char)
            is_multi_tone = len(all_readings) > 1
            
            # 1. 处理未收录字（保留优化：只警告，不扣分）
            if not all_readings:
                warn_count += 1
                # 不扣罚 total_penalty
                summary_errors.append(f"「{char}」未收录于平水韵（已跳过该字校验，不扣分）")
                current_sent["chars"].append({"char": char, "status": "unknown"})
            else:
                # 2. 校验非韵脚
                if not is_rhyme:
                    prefer_flat = True if rule_tune == "平" else (False if rule_tune == "仄" else None)
                    if prefer_flat is None or len(all_readings) == 1:
                        tone, _ = all_readings[0]
                    else:
                        matching = [r for r in all_readings if (r[0] == "平") == prefer_flat]
                        tone, _ = matching[0] if matching else all_readings[0]
                        
                    is_flat = (tone == "平")
                    multi_note = f"（多音字，取{tone}声读）" if is_multi_tone else ""
                    
                    if rule_tune == "平":
                        if not is_flat:
                            error_count += 1; total_penalty += 3
                            summary_errors.append(f"「{char}」{tone}声（仄）{multi_note}，此处须填平声字")
                    elif rule_tune == "仄":
                        if is_flat:
                            error_count += 1; total_penalty += 3
                            summary_errors.append(f"「{char}」{tone}声（平）{multi_note}，此处须填仄声字")
                            
                    current_sent["chars"].append({"char": char, "tone": tone})
                
                # 3. 校验韵脚
                else:
                    should_flat = (rule_tune == "平")
                    slot = rhyme_slots.get(should_flat)
                    
                    tone, rhyme_group, multi_note = self.pick_rhyme_reading(char, should_flat, slot)
                    is_flat = (tone == "平")
                    
                    if is_flat != should_flat:
                        error_count += 1; total_penalty += 4
                        exp = "平声" if should_flat else "仄声"
                        summary_errors.append(f"「{char}」{tone}声{multi_note}，此韵脚须{exp}")
                    else:
                        if not slot:
                            # 确立首韵
                            ynm = self.get_yunmu_name(char, tone)
                            rhyme_slots[should_flat] = {
                                "group": rhyme_group, "yunmuName": ynm,
                                "cilinEntry": None, "usedCilin": False
                            }
                            label_str = f"平水韵·{ynm}韵"
                            if not rhyme_group_label:
                                rhyme_group_label = label_str
                            elif label_str not in rhyme_group_label:
                                rhyme_group_label += f" | {label_str}" # 支持换韵展示
                        else:
                            # 校验通押
                            strict_reading = next((r for r in all_readings if (r[0] == "平") == should_flat and char in r[1]), None)
                            if strict_reading:
                                pass # 完全押韵
                            else:
                                if not slot["cilinEntry"]:
                                    anchor = next(iter(slot["group"])) if slot["group"] else char
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
                                        if "平水韵" in rhyme_group_label: # 拓宽显示为大韵部
                                            rhyme_group_label = char_cilin["label"]
                                        cilin_matched = True
                                        break
                                        
                                if not cilin_matched:
                                    error_count += 1; total_penalty += 5
                                    char_ym = self.get_yunmu_name(char, tone)
                                    summary_errors.append(f"「{char}」{multi_note}出韵：属{char_ym}韵，应押{slot['yunmuName']}韵")
                    
                    current_sent["chars"].append({"char": char, "tone": tone, "is_rhyme": True})

            # 4. 根据新格式的 rhythm 和 shift 智能断句（方便如果有可视化需求）
            if is_rhyme or is_ju or is_shift:
                if is_shift or is_rhyme:
                    current_sent["punct"] = "。"
                elif is_ju:
                    current_sent["punct"] = "，"
                    
                sentences.append(current_sent)
                current_sent = {"chars":[], "punct": ""}
                
        if current_sent["chars"]:
            sentences.append(current_sent)

        score = max(0, 100 - total_penalty * 4)
        return {
            "valid": score >= 60,
            "score": score,
            "totalChars": req,
            "errorCount": error_count,
            "warnCount": warn_count,
            "rhymeGroupLabel": rhyme_group_label,
            "summary": summary_errors,
            "sentences": sentences # 返回句子结构便于展示
        }
    def _get_candidate_patterns(self, target_name):
        """
        词牌家族智能路由：提取核心词牌名，自动关联其 令/引/近/慢/减字/摊破 等变体
        """
        candidates =[]
        
        # 提取核心词牌名（去掉长度/节奏修饰词）
        def get_core(name):
            # 去除前缀和后缀，例如 "减字木兰花" -> "木兰花", "浪淘沙慢" -> "浪淘沙"
            return re.sub(r'^(摊破|减字|偷声|促拍|添字)|(令|引|近|慢|犯)$', '', name)
            
        target_core = get_core(target_name)
        
        # 遍历 JSON 中所有的词牌名
        for k in self.pattern_variants.keys():
            # 1. 如果核心名完全一致（例如 浪淘沙 == 浪淘沙慢 的核心）
            # 2. 或者互相包含（例如 "水调歌" 包含在 "水调歌头" 中，防止修饰词没覆盖全）
            is_core_match = (get_core(k) == target_core)
            is_substring = (len(target_name) >= 2) and (target_name in k or k in target_name)
            
            if is_core_match or is_substring:
                if k not in candidates:
                    candidates.append(k)
                    
        # 确保用户精确查询的词牌名（如果有）排在最前面
        if target_name in candidates:
            candidates.remove(target_name)
            candidates.insert(0, target_name)
            
        return candidates

    def evaluate(self, ci_text, pattern_name):
        """
        对外主入口：自动匹配最佳变体调式，支持词牌家族模糊路由
        """
        raw_chars = re.findall(r'[\u4e00-\u9fa5\u3007]', ci_text)
        actual_len = len(raw_chars)
        
        # 调用智能路由，获取所有关联的词牌名
        candidate_keys = self._get_candidate_patterns(pattern_name)
        
        if not candidate_keys:
            return {"valid": False, "score": 0, "summary":[f"未找到词牌「{pattern_name}」及其相关变体的数据"]}
            
        best_result = None
        best_score = -1
        
        # 遍历所有被召回的关联词牌（例如同时遍历 浪淘沙 和 浪淘沙慢 的所有格式）
        for matched_key in candidate_keys:
            variants = self.pattern_variants.get(matched_key,[])
            for v in variants:
                tunes = v.get("tunes",[])
                if not tunes: continue
                
                result = self.validate_prosody(ci_text, tunes)
                
                is_better = False
                if not best_result:
                    is_better = True
                elif result["score"] > best_score:
                    is_better = True
                elif result["score"] == best_score:
                    current_diff = abs(result["totalChars"] - actual_len)
                    best_diff = abs(best_result["totalChars"] - actual_len)
                    
                    if current_diff < best_diff:
                        is_better = True
                    elif current_diff == best_diff and result["errorCount"] < best_result["errorCount"]:
                        is_better = True
                        
                if is_better:
                    best_score = result["score"]
                    best_result = result
                    best_result["matchedVariant"] = {
                        "actual_pattern": matched_key,  # <--- 记录它真实匹配到的词牌名
                        "author": v.get("author"),
                        "sketch": v.get("sketch"),
                        "desc": v.get("desc")
                    }
                
        if not best_result:
            return {"valid": False, "score": 0, "summary":["所有格律均无法校验"]}
            
        best_result["patternName"] = pattern_name
        
        # 🌟 核心高亮：如果真实匹配的词牌与 AI 宣称的不一致，给出智能提示
        actual_pat = best_result["matchedVariant"]["actual_pattern"]
        if actual_pat != pattern_name and best_result["score"] > 0:
            # 将提示信息插入到 summary 的最前面
            best_result["summary"].insert(0, f"💡 智能纠偏：该词字数/格律实际匹配的是「{actual_pat}」({best_result['totalChars']}字)，而非「{pattern_name}」")
            
        return best_result