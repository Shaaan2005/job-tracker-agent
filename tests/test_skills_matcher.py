"""Tests for the pure-Python skills matcher."""

import pytest

from app.services.skills_matcher import match_skills, normalize_skill


class TestNormalizeSkill:
    def test_lowercase_and_strip(self):
        assert normalize_skill("  Python  ") == "python"

    def test_synonym_js(self):
        assert normalize_skill("JS") == "javascript"

    def test_synonym_py(self):
        assert normalize_skill("py") == "python"

    def test_synonym_ts(self):
        assert normalize_skill("ts") == "typescript"

    def test_synonym_k8s(self):
        assert normalize_skill("k8s") == "kubernetes"

    def test_synonym_node(self):
        assert normalize_skill("node") == "nodejs"

    def test_no_synonym(self):
        assert normalize_skill("Rust") == "rust"


class TestMatchSkills:
    def test_full_match(self):
        result = match_skills(["Python", "Docker"], ["python", "docker", "linux"])
        assert set(result["matched"]) == {"Python", "Docker"}
        assert result["missing"] == []
        assert result["score"] == 1.0

    def test_partial_match(self):
        result = match_skills(
            ["Python", "Go", "Docker"], ["python", "docker"]
        )
        assert "Python" in result["matched"]
        assert "Docker" in result["matched"]
        assert "Go" in result["missing"]
        assert abs(result["score"] - 2 / 3) < 0.01

    def test_no_match(self):
        result = match_skills(["Rust", "Haskell"], ["python", "javascript"])
        assert result["matched"] == []
        assert set(result["missing"]) == {"Rust", "Haskell"}
        assert result["score"] == 0.0

    def test_empty_required(self):
        result = match_skills([], ["python", "javascript"])
        assert result["matched"] == []
        assert result["missing"] == []
        assert result["score"] == 0.0

    def test_empty_user_skills(self):
        result = match_skills(["Python"], [])
        assert result["matched"] == []
        assert result["missing"] == ["Python"]
        assert result["score"] == 0.0

    def test_synonym_matching(self):
        result = match_skills(["JS", "py"], ["javascript", "python"])
        assert len(result["matched"]) == 2
        assert result["score"] == 1.0

    def test_case_insensitive(self):
        result = match_skills(["PYTHON", "Docker"], ["python", "docker"])
        assert result["score"] == 1.0
