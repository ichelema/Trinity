#!/usr/bin/env node
/**
 * Skill Evaluation Engine v2.0
 *
 * Intelligent skill activation based on:
 * - Keywords and patterns in prompts
 * - File paths mentioned or being edited
 * - Directory mappings
 * - Intent detection
 * - Content pattern matching
 *
 * Outputs a structured reminder with matched skills and reasons.
 */

const fs = require("fs");
const path = require("path");

const RULES_PATH = path.join(__dirname, "skill-rules.json");
const SKILLS_DIR = path.join(__dirname, "..", "skills");

/**
 * Una skill è disabilitata se la sua cartella esiste in skills/ ma non contiene
 * più un file SKILL.md (es. rinominato in SKILL.md.disabled). In quel caso
 * l'harness non la carica, quindi non va nemmeno proposta.
 * Se la cartella non esiste (skill definita altrove), non la consideriamo
 * disabilitata e manteniamo il comportamento precedente.
 */
function isSkillDisabled(skillName) {
  const dir = path.join(SKILLS_DIR, skillName);
  return fs.existsSync(dir) && !fs.existsSync(path.join(dir, "SKILL.md"));
}

/**
 * @typedef {Object} SkillMatch
 * @property {string} name
 * @property {number} score
 * @property {string[]} reasons
 * @property {number} priority
 */

function loadRules() {
  try {
    const content = fs.readFileSync(RULES_PATH, "utf-8");
    return JSON.parse(content);
  } catch (error) {
    console.error(`Failed to load skill rules: ${error.message}`);
    process.exit(0);
  }
}

function extractFilePaths(prompt) {
  const paths = new Set();

  // Match paths with extensions relevant to this project
  const extensionPattern =
    /(?:^|\s|["'`])([\w\-./\\:]+\.(?:py|rb|sh|xlsx?|csv|excalidraw|md|json|lua|toml|cr|go|rs|png|svg|ya?ml))\b/gi;
  let match;
  while ((match = extensionPattern.exec(prompt)) !== null) {
    paths.add(match[1]);
  }

  // Match paths starting with common directories for this project
  const dirPattern =
    /(?:^|\s|["'`])((?:data|test|logs|script|sound|\.claude|\.github)[\\/][\w\-./\\]+)/gi;
  while ((match = dirPattern.exec(prompt)) !== null) {
    paths.add(match[1]);
  }

  // Match quoted paths
  const quotedPattern = /["'`]([\w\-./\\:]+[/\\][\w\-./\\]+)["'`]/g;
  while ((match = quotedPattern.exec(prompt)) !== null) {
    paths.add(match[1]);
  }

  return Array.from(paths);
}

function matchesPattern(text, pattern, flags = "i") {
  try {
    const regex = new RegExp(pattern, flags);
    return regex.test(text);
  } catch {
    return false;
  }
}

function matchesGlob(filePath, globPattern) {
  const normalized = filePath.replace(/\\/g, "/");
  const regexPattern = globPattern
    .replace(/\./g, "\\.")
    // Converti il glob `?` PRIMA di introdurre i token regex: altrimenti questo
    // replace corromperebbe anche il `?` del gruppo `(.*\/)?` generato da `**/`.
    .replace(/\?/g, ".")
    .replace(/\*\*\//g, "<<<DOUBLESTARSLASH>>>")
    .replace(/\*\*/g, "<<<DOUBLESTAR>>>")
    .replace(/\*/g, "[^/]*")
    .replace(/<<<DOUBLESTARSLASH>>>/g, "(.*\\/)?")
    .replace(/<<<DOUBLESTAR>>>/g, ".*");

  try {
    const regex = new RegExp(`^${regexPattern}$`, "i");
    return regex.test(normalized);
  } catch {
    return false;
  }
}

function matchDirectoryMapping(filePath, mappings) {
  const normalized = filePath.replace(/\\/g, "/");
  for (const [dir, skillName] of Object.entries(mappings)) {
    if (normalized === dir || normalized.startsWith(dir + "/")) {
      return skillName;
    }
  }
  return null;
}

function evaluateSkill(
  skillName,
  skill,
  prompt,
  promptLower,
  filePaths,
  rules,
) {
  const { triggers = {}, excludePatterns = [], priority = 5 } = skill;
  const scoring = rules.scoring;

  if (isSkillDisabled(skillName)) {
    return null;
  }

  let score = 0;
  const reasons = [];

  for (const excludePattern of excludePatterns) {
    if (matchesPattern(promptLower, excludePattern)) {
      return null;
    }
  }

  if (triggers.keywords) {
    for (const keyword of triggers.keywords) {
      if (promptLower.includes(keyword.toLowerCase())) {
        score += scoring.keyword;
        reasons.push(`keyword "${keyword}"`);
      }
    }
  }

  if (triggers.keywordPatterns) {
    for (const pattern of triggers.keywordPatterns) {
      if (matchesPattern(promptLower, pattern)) {
        score += scoring.keywordPattern;
        reasons.push(`pattern /${pattern}/`);
      }
    }
  }

  if (triggers.intentPatterns) {
    for (const pattern of triggers.intentPatterns) {
      if (matchesPattern(promptLower, pattern)) {
        score += scoring.intentPattern;
        reasons.push(`intent detected`);
        break;
      }
    }
  }

  if (triggers.contextPatterns) {
    for (const pattern of triggers.contextPatterns) {
      if (promptLower.includes(pattern.toLowerCase())) {
        score += scoring.contextPattern;
        reasons.push(`context "${pattern}"`);
      }
    }
  }

  if (triggers.pathPatterns && filePaths.length > 0) {
    for (const filePath of filePaths) {
      for (const pattern of triggers.pathPatterns) {
        if (matchesGlob(filePath, pattern)) {
          score += scoring.pathPattern;
          reasons.push(`path "${filePath}"`);
          break;
        }
      }
    }
  }

  if (rules.directoryMappings && filePaths.length > 0) {
    for (const filePath of filePaths) {
      const mappedSkill = matchDirectoryMapping(
        filePath,
        rules.directoryMappings,
      );
      if (mappedSkill === skillName) {
        score += scoring.directoryMatch;
        reasons.push(`directory mapping`);
        break;
      }
    }
  }

  if (triggers.contentPatterns) {
    for (const pattern of triggers.contentPatterns) {
      if (matchesPattern(prompt, pattern)) {
        score += scoring.contentPattern;
        reasons.push(`code pattern detected`);
        break;
      }
    }
  }

  if (score > 0) {
    return { name: skillName, score, reasons: [...new Set(reasons)], priority };
  }

  return null;
}

function getRelatedSkills(matches, skills) {
  const matchedNames = new Set(matches.map((m) => m.name));
  const related = new Set();

  for (const match of matches) {
    const skill = skills[match.name];
    if (skill?.relatedSkills) {
      for (const relatedName of skill.relatedSkills) {
        if (!matchedNames.has(relatedName)) {
          related.add(relatedName);
        }
      }
    }
  }

  return Array.from(related);
}

function formatConfidence(score, minScore) {
  if (score >= minScore * 3) return "HIGH";
  if (score >= minScore * 2) return "MEDIUM";
  return "LOW";
}

function evaluate(prompt) {
  const rules = loadRules();
  const { config, skills } = rules;

  const promptLower = prompt.toLowerCase();
  const filePaths = extractFilePaths(prompt);

  const matches = [];
  for (const [name, skill] of Object.entries(skills)) {
    const match = evaluateSkill(
      name,
      skill,
      prompt,
      promptLower,
      filePaths,
      rules,
    );
    if (match && match.score >= config.minConfidenceScore) {
      matches.push(match);
    }
  }

  if (matches.length === 0) {
    return "";
  }

  matches.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return b.priority - a.priority;
  });

  const topMatches = matches.slice(0, config.maxSkillsToShow);
  const relatedSkills = getRelatedSkills(topMatches, skills);

  let context = "SKILL ACTIVATION REQUIRED\n\n";

  if (filePaths.length > 0) {
    context += `Detected file paths: ${filePaths.join(", ")}\n\n`;
  }

  context += "Matched skills (ranked by relevance):\n";

  for (let i = 0; i < topMatches.length; i++) {
    const match = topMatches[i];
    const confidence = formatConfidence(match.score, config.minConfidenceScore);

    context += `${i + 1}. ${match.name} (${confidence} confidence)\n`;

    if (config.showMatchReasons && match.reasons.length > 0) {
      context += `   Matched: ${match.reasons.slice(0, 3).join(", ")}\n`;
    }
  }

  if (relatedSkills.length > 0) {
    context += `\nRelated skills to consider: ${relatedSkills.join(", ")}\n`;
  }

  context += "\nBefore implementing, you MUST:\n";
  context += "1. EVALUATE: State YES/NO for each skill with brief reasoning\n";
  context += "2. ACTIVATE: Invoke the Skill tool for each YES skill\n";
  context += "3. IMPLEMENT: Only proceed after skill activation\n";
  context += "\nExample evaluation:\n";
  context += `- ${topMatches[0].name}: YES - [your reasoning]\n`;
  if (topMatches.length > 1) {
    context += `- ${topMatches[1].name}: NO - [your reasoning]\n`;
  }
  context += "\nDO NOT skip this step. Invoke relevant skills NOW.";

  return context;
}

function main() {
  let input = "";

  process.stdin.setEncoding("utf8");

  process.stdin.on("data", (chunk) => {
    input += chunk;
  });

  process.stdin.on("end", () => {
    let prompt = "";

    try {
      const data = JSON.parse(input);
      prompt = data.prompt || "";
    } catch {
      prompt = input;
    }

    if (!prompt.trim()) {
      process.exit(0);
    }

    try {
      const output = evaluate(prompt);
      if (output) {
        const hookOutput = JSON.stringify({
          hookSpecificOutput: {
            hookEventName: "UserPromptSubmit",
            additionalContext: output,
          },
        });
        process.stdout.write(hookOutput);
      }
    } catch (error) {
      console.error(`Skill evaluation failed: ${error.message}`);
    }

    process.exit(0);
  });
}

main();
