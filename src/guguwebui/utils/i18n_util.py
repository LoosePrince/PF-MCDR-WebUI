import re
from collections import OrderedDict


def consistent_type_update(original, updates, remove_missing=False):
    from ruamel.yaml.comments import CommentedSeq
    if remove_missing and isinstance(original, dict) and isinstance(updates, dict):
        keys_to_remove = [key for key in original if key not in updates]
        for key in keys_to_remove: del original[key]
    for key, value in updates.items():
        if key in original and original[key] is None and (not value or (isinstance(value,list) and not any(value))): continue
        elif isinstance(value, dict) and key in original and isinstance(original[key], dict): consistent_type_update(original[key], value, remove_missing)
        elif isinstance(value, list) and key in original:
            if isinstance(original[key], dict):
                original[key] = value
                continue
            original_ca = original[key].ca.items if isinstance(original[key], CommentedSeq) else None
            targe_type = list({type(item) for item in original[key] if item}) if original[key] else None
            temp_list = [(targe_type[0](item) if targe_type else item) if item else None for item in value]
            if original_ca:
                original[key] = CommentedSeq(temp_list)
                original[key].ca.items[len(original[key])-1] = original_ca[max(original_ca)]
            else: original[key] = temp_list
        elif key in original and original[key]:
            original_type = type(original[key])
            original[key] = original_type(value)
        else: original[key] = value

def _normalize_lang_code(raw_code: str) -> str:
    code = (raw_code or "").strip().strip("[] ")
    if not code: return "zh-CN"
    base = code.replace("_", "-")
    lower = base.lower()
    if lower in ("zh", "zh-cn", "zh_hans"): return "zh-CN"
    if lower in ("en", "en-us"): return "en-US"
    if "-" in base:
        parts = base.split("-", 1)
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return base

def _parse_inline_and_prev_comments(file_text: str):
    result = {}
    indent_stack = []
    last_plain_comment_by_indent = {}

    for raw in file_text.splitlines():
        line = raw.rstrip("\n\r")
        if not line.strip():
            last_plain_comment_by_indent.clear()
            continue

        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("#"):
            content = stripped[1:].strip()
            if content.startswith("[") and content.endswith("]"):
                last_plain_comment_by_indent.pop(indent, None)
                continue
            if "|" in content: continue
            last_plain_comment_by_indent[indent] = content
            continue

        logical = line.lstrip()
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*(#\s*(.*))?$", logical)
        if not m:
            last_plain_comment_by_indent.clear()
            continue

        key = m.group(1)
        inline_comment = (m.group(4) or "").strip()

        while indent_stack and indent_stack[-1][0] >= indent:
            indent_stack.pop()
        indent_stack.append((indent, key))

        full_key = ".".join(k for _, k in indent_stack)

        if inline_comment:
            result[full_key] = inline_comment
            last_plain_comment_by_indent.pop(indent, None)
        else:
            prev = last_plain_comment_by_indent.pop(indent, None)
            if prev: result[full_key] = prev.strip()

    return result

def _parse_language_blocks(file_text: str):
    lang_order = []
    lang_map = {}
    current_lang = None
    for raw in file_text.splitlines():
        line = raw.rstrip("\n\r")
        stripped = line.strip()
        if stripped.startswith("#"):
            content = stripped[1:].strip()
            if content.startswith("[") and content.endswith("]") and len(content) >= 3:
                current_lang = _normalize_lang_code(content)
                if current_lang not in lang_map:
                    lang_map[current_lang] = {}
                    lang_order.append(current_lang)
                continue
            if current_lang and "|" in content:
                try:
                    key_part, right = [i.strip() for i in content.split("|", 1)]
                    if not key_part: continue
                    if "::" in right:
                        name_part, desc_part = [i.strip() for i in right.split("::", 1)]
                        value = [name_part, desc_part]
                    else:
                        value = [right]
                    lang_map[current_lang][key_part] = value
                except Exception: continue
    return lang_order, lang_map

def _nest_translation_map(flat_map: dict) -> dict:
    nested = {}
    for full_key, meta in (flat_map or {}).items():
        if not isinstance(full_key, str): continue
        parts = [p for p in full_key.split(".") if p]
        if not parts: continue
        cur = nested
        for i, part in enumerate(parts):
            if part not in cur or not isinstance(cur.get(part), dict):
                cur[part] = {"name": None, "desc": None, "children": {}}
            if i == len(parts) - 1 and isinstance(meta, dict):
                if meta.get("name") is not None: cur[part]["name"] = meta.get("name")
                if "desc" in meta: cur[part]["desc"] = meta.get("desc")
            next_children = cur[part].get("children")
            if not isinstance(next_children, dict):
                cur[part]["children"] = {}
                next_children = cur[part]["children"]
            cur = next_children
    return nested

def build_yaml_i18n_translations(yaml_config: dict, file_text: str) -> dict:
    file_text = file_text or ""
    lang_order, lang_block_map = _parse_language_blocks(file_text)
    inline_map = _parse_inline_and_prev_comments(file_text)

    default_lang = None
    try:
        conf_lang = yaml_config.get("language") if isinstance(yaml_config, dict) else None
        if isinstance(conf_lang, str) and conf_lang.strip():
            default_lang = _normalize_lang_code(conf_lang)
    except Exception: pass
    if not default_lang:
        default_lang = lang_order[0] if lang_order else "zh-CN"

    translations = OrderedDict()
    for lang in lang_order:
        translations[lang] = {}
        for key, arr in lang_block_map.get(lang, {}).items():
            name = str(arr[0]) if isinstance(arr, list) and len(arr) >= 1 else (arr if isinstance(arr, str) else None)
            desc = str(arr[1]) if isinstance(arr, list) and len(arr) >= 2 else None
            if name is not None: translations[lang][key] = {"name": name, "desc": desc}

    zh_cn_key = "zh-CN"
    if zh_cn_key not in translations: translations[zh_cn_key] = {}
    for key, text in inline_map.items():
        if key not in translations[zh_cn_key]:
            if "::" in text:
                name_part, desc_part = [i.strip() for i in text.split("::", 1)]
                translations[zh_cn_key][key] = {"name": name_part, "desc": desc_part}
            else:
                translations[zh_cn_key][key] = {"name": text.strip(), "desc": None}

    for lang in list(translations.keys()):
        translations[lang] = _nest_translation_map(translations[lang])

    return {"default": default_lang, "translations": translations}

def build_json_i18n_translations(json_obj: dict) -> dict:
    if not isinstance(json_obj, dict): return {"default": "zh-CN", "translations": {}}

    def normalize_candidates(lang_code: str) -> list[str]:
        base = _normalize_lang_code(lang_code)
        a, b = (base.split('-', 1) + [""])[:2]
        return list({base, base.lower(), f"{a.lower()}_{b.lower()}", a.lower()})

    translations = OrderedDict()
    avail_keys = set(json_obj.keys())
    for target in ["zh-CN", "en-US"]:
        cands = normalize_candidates(target)
        picked = next((c for c in cands if c in json_obj), None)
        if picked and isinstance(json_obj[picked], dict):
            translations[target] = {}
            for k, v in json_obj[picked].items():
                if isinstance(v, list) and len(v) >= 1:
                    translations[target][k] = {"name": str(v[0]) if v[0] is not None else "", "desc": str(v[1]) if len(v) >= 2 and v[1] is not None else None}
                elif isinstance(v, dict):
                    translations[target][k] = {"name": str(v.get("name", "")), "desc": str(v.get("desc")) if v.get("desc") is not None else None}
                elif isinstance(v, str):
                    translations[target][k] = {"name": v, "desc": None}

    if not translations and avail_keys:
        any_key = next(iter(avail_keys))
        normalized = _normalize_lang_code(any_key)
        inner = json_obj.get(any_key, {})
        translations[normalized] = {}
        if isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, list) and len(v) >= 1:
                    translations[normalized][k] = {"name": str(v[0]) if v[0] is not None else "", "desc": str(v[1]) if len(v) >= 2 and v[1] is not None else None}
                elif isinstance(v, dict):
                    translations[normalized][k] = {"name": str(v.get("name", "")), "desc": str(v.get("desc")) if v.get("desc") is not None else None}
                elif isinstance(v, str):
                    translations[normalized][k] = {"name": v, "desc": None}

    for lang in list(translations.keys()):
        translations[lang] = _nest_translation_map(translations[lang])

    default_lang = "zh-CN" if "zh-CN" in translations else (next(iter(translations.keys())) if translations else "zh-CN")
    return {"default": default_lang, "translations": translations}

def extract_comment(comment_object) -> str:
    if not comment_object: return ""
    comment = next((c[0].value if isinstance(c, list) and c else c.value for c in comment_object if c), "")
    comment = comment.split("\n", 1)[0].replace("#", "").strip()
    return comment.split("::", 1) if "::" in comment else comment

def get_comment(config: dict) -> dict:
    name_map = {}
    for k, v in config.items():
        comment = extract_comment(config.ca.items.get(k))
        if comment: name_map[k] = comment
        if isinstance(v, dict): name_map.update(get_comment(v))
    return name_map
