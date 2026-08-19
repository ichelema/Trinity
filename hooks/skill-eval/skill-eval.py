#!/usr/bin/env python3
"""Skill Evaluation Engine v3.0 — port Python di skill-eval.js.

Motore di attivazione skill basato su keyword, pattern, path e intent.
Stessa logica e stesso output del .js: usa `re` (regex compatibili con JS)
e `json` nativi.
"""

import json
import os
import re
import sys

RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skill-rules.json")
SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "skills")


def is_skill_disabled(skill_name):
    d = os.path.join(SKILLS_DIR, skill_name)
    return os.path.isdir(d) and not os.path.exists(os.path.join(d, "SKILL.md"))


def load_rules():
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load skill rules: {e}", file=sys.stderr)
        sys.exit(0)


def extract_file_paths(prompt):
    paths = set()

    extension_pattern = re.compile(
        r'(?:^|\s|["\'`])([\w\-./\\:]+\.(?:py|rb|sh|xlsx?|csv|excalidraw|md|json|lua|toml|cr|go|rs|png|svg|ya?ml|pdf|epub|docx|mobi|azw3?|rtf))\b',
        re.IGNORECASE,
    )
    for m in extension_pattern.finditer(prompt):
        paths.add(m.group(1))

    dir_pattern = re.compile(
        r'(?:^|\s|["\'`])((?:data|test|logs|script|sound|\.claude|\.github)[\\/][\w\-./\\]+)',
        re.IGNORECASE,
    )
    for m in dir_pattern.finditer(prompt):
        paths.add(m.group(1))

    quoted_pattern = re.compile(r'["\'`]([\w\-./\\:]+[/\\][\w\-./\\]+)["\'`]')
    for m in quoted_pattern.finditer(prompt):
        paths.add(m.group(1))

    return list(paths)


def matches_pattern(text, pattern, flags="i"):
    try:
        flag = re.IGNORECASE if "i" in flags else 0
        return re.search(pattern, text, flag) is not None
    except re.error:
        return False


def matches_glob(file_path, glob_pattern):
    normalized = file_path.replace("\\", "/")
    regex_pattern = glob_pattern
    regex_pattern = regex_pattern.replace(".", "\\.")
    regex_pattern = regex_pattern.replace("?", ".")
    regex_pattern = regex_pattern.replace("**/", "<<<DOUBLESTARSLASH>>>")
    regex_pattern = regex_pattern.replace("**", "<<<DOUBLESTAR>>>")
    regex_pattern = regex_pattern.replace("*", "[^/]*")
    regex_pattern = regex_pattern.replace("<<<DOUBLESTARSLASH>>>", "(.*/)?")
    regex_pattern = regex_pattern.replace("<<<DOUBLESTAR>>>", ".*")
    try:
        return re.search("^" + regex_pattern + "$", normalized, re.IGNORECASE) is not None
    except re.error:
        return False


def match_directory_mapping(file_path, mappings):
    normalized = file_path.replace("\\", "/")
    for dir_, skill_name in mappings.items():
        if normalized == dir_ or normalized.startswith(dir_ + "/"):
            return skill_name
    return None


def evaluate_skill(skill_name, skill, prompt, prompt_lower, file_paths, rules):
    triggers = skill.get("triggers", {})
    exclude_patterns = skill.get("excludePatterns", [])
    priority = skill.get("priority", 5)
    scoring = rules["scoring"]

    if is_skill_disabled(skill_name):
        return None

    score = 0
    reasons = []

    for ep in exclude_patterns:
        if matches_pattern(prompt_lower, ep):
            return None

    if triggers.get("keywords"):
        for kw in triggers["keywords"]:
            if kw.lower() in prompt_lower:
                score += scoring["keyword"]
                reasons.append(f'keyword "{kw}"')

    if triggers.get("keywordPatterns"):
        for pat in triggers["keywordPatterns"]:
            if matches_pattern(prompt_lower, pat):
                score += scoring["keywordPattern"]
                reasons.append(f"pattern /{pat}/")

    if triggers.get("intentPatterns"):
        for pat in triggers["intentPatterns"]:
            if matches_pattern(prompt_lower, pat):
                score += scoring["intentPattern"]
                reasons.append("intent detected")
                break

    if triggers.get("contextPatterns"):
        for pat in triggers["contextPatterns"]:
            if pat.lower() in prompt_lower:
                score += scoring["contextPattern"]
                reasons.append(f'context "{pat}"')

    if triggers.get("pathPatterns") and file_paths:
        for fp in file_paths:
            for pat in triggers["pathPatterns"]:
                if matches_glob(fp, pat):
                    score += scoring["pathPattern"]
                    reasons.append(f'path "{fp}"')
                    break

    if rules.get("directoryMappings") and file_paths:
        for fp in file_paths:
            mapped = match_directory_mapping(fp, rules["directoryMappings"])
            if mapped == skill_name:
                score += scoring["directoryMatch"]
                reasons.append("directory mapping")
                break

    if triggers.get("contentPatterns"):
        for pat in triggers["contentPatterns"]:
            if matches_pattern(prompt, pat):
                score += scoring["contentPattern"]
                reasons.append("code pattern detected")
                break

    if score > 0:
        return {
            "name": skill_name,
            "score": score,
            "reasons": list(dict.fromkeys(reasons)),
            "priority": priority,
        }

    return None


def get_related_skills(matches, skills):
    matched_names = {m["name"] for m in matches}
    related = set()
    for match in matches:
        skill = skills.get(match["name"], {})
        for rn in skill.get("relatedSkills", []):
            if rn not in matched_names and not is_skill_disabled(rn):
                related.add(rn)
    return list(related)


def format_confidence(score, min_score):
    if score >= min_score * 3:
        return "HIGH"
    if score >= min_score * 2:
        return "MEDIUM"
    return "LOW"


def evaluate(prompt):
    rules = load_rules()
    config = rules["config"]
    skills = rules["skills"]

    prompt_lower = prompt.lower()
    file_paths = extract_file_paths(prompt)

    matches = []
    for name, skill in skills.items():
        m = evaluate_skill(name, skill, prompt, prompt_lower, file_paths, rules)
        if m and m["score"] >= config["minConfidenceScore"]:
            matches.append(m)

    if not matches:
        return ""

    matches.sort(key=lambda m: (-m["score"], m["priority"]))
    top = matches[: config["maxSkillsToShow"]]
    related = get_related_skills(top, skills)

    context = "SKILL ACTIVATION REQUIRED\n\n"

    if file_paths:
        context += f'Detected file paths: {", ".join(file_paths)}\n\n'

    context += "Matched skills (ranked by relevance):\n"

    for i, m in enumerate(top):
        confidence = format_confidence(m["score"], config["minConfidenceScore"])
        context += f"{i + 1}. {m['name']} ({confidence} confidence)\n"
        if config.get("showMatchReasons") and m["reasons"]:
            context += f'   Matched: {", ".join(m["reasons"][:3])}\n'

    if related:
        context += f'\nRelated skills to consider: {", ".join(related)}\n'

    context += "\nBefore implementing, you MUST:\n"
    context += "1. EVALUATE: State YES/NO for each skill with brief reasoning\n"
    context += "2. ACTIVATE: Invoke the Skill tool for each YES skill\n"
    context += "3. IMPLEMENT: Only proceed after skill activation\n"
    context += "\nExample evaluation:\n"
    context += f"- {top[0]['name']}: YES - [your reasoning]\n"
    if len(top) > 1:
        context += f"- {top[1]['name']}: NO - [your reasoning]\n"
    context += "\nDO NOT skip this step. Invoke relevant skills NOW."

    return context


def main():
    input_data = sys.stdin.read()

    prompt = ""
    try:
        data = json.loads(input_data)
        prompt = data.get("prompt", "")
    except Exception:
        prompt = input_data

    if not prompt.strip():
        sys.exit(0)

    try:
        output = evaluate(prompt)
        if output:
            hook_output = json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": output,
                    }
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            sys.stdout.write(hook_output)
    except Exception as e:
        print(f"Skill evaluation failed: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
