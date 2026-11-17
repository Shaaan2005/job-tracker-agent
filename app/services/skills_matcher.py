"""Pure-Python skills matcher – no LLM required.

Normalizes skill names, computes set intersection, and returns
matched / missing lists plus a 0-1 score.
"""

import re

# Simple synonym map – keys are alternate spellings, values the canonical name.
_SYNONYMS: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "react.js": "react",
    "reactjs": "react",
    "node.js": "nodejs",
    "node": "nodejs",
    "vue.js": "vue",
    "vuejs": "vue",
    "angular.js": "angular",
    "angularjs": "angular",
    "c++": "cpp",
    "c#": "csharp",
    "dot net": "dotnet",
    ".net": "dotnet",
    "mern": "mern stack",
    "mongo": "mongodb",
    "mongo db": "mongodb",
    "huggingface": "hugging face transformers",
    "hugging face": "hugging face transformers",
    "transformers": "hugging face transformers",
    "huggingface transformers": "hugging face transformers",
    "wav2vec": "wav2vec2",
    "wav2vec 2": "wav2vec2",
    "wav2vec 2.0": "wav2vec2",
    "speech to speech": "speech-to-speech",
    "speech-to-text": "speech recognition",
    "automatic speech recognition": "asr",
    "amazon web services": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    "tf": "tensorflow",
}


def normalize_skill(skill: str) -> str:
    """Lowercase, strip whitespace, remove punctuation/wrapper noise, and apply synonym mapping."""
    key = skill.lower().strip()
    # Remove parentheticals, e.g. "Python (Programming Language)" -> "python"
    key = re.sub(r"\(.*?\)", "", key).strip()
    # Remove common qualification prefixes
    for prefix in [
        "proficiency in ",
        "experience with ",
        "knowledge of ",
        "working with ",
        "familiarity with ",
        "strong ",
        "hands-on ",
    ]:
        if key.startswith(prefix):
            key = key[len(prefix):].strip()
    # Remove common activity suffixes
    for suffix in [" development", " programming", " coding"]:
        if key.endswith(suffix):
            key = key[:-len(suffix)].strip()
    return _SYNONYMS.get(key, key)


def match_skills(
    required_skills: list[str],
    user_skills: list[str],
) -> dict:
    """Compare required skills against the user's skill set.

    Returns:
        dict with keys ``matched``, ``missing``, and ``score`` (0.0–1.0).
    """
    if not required_skills:
        return {"matched": [], "missing": [], "score": 0.0}

    norm_user = {normalize_skill(s) for s in user_skills}
    norm_required = {normalize_skill(s): s for s in required_skills}

    matched: list[str] = []
    missing: list[str] = []

    for norm, original in norm_required.items():
        if norm in norm_user:
            matched.append(original)
        else:
            missing.append(original)

    score = len(matched) / len(norm_required) if norm_required else 0.0
    return {"matched": matched, "missing": missing, "score": round(score, 4)}
