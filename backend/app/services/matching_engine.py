"""
Enhanced matching engine with weighted scoring.
"""

import re
from typing import Any, Dict, List


class EnhancedMatchingEngine:
    """Deterministic matching engine with weighted scoring factors."""
    
    # Skill categories for weighting
    PRIMARY_SKILLS = {
        "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java",
        "C++", "C#", "Ruby", "PHP", "Swift", "Kotlin"
    }
    
    SECONDARY_SKILLS = {
        "Docker", "Kubernetes", "Git", "Linux", "Terraform",
        "AWS", "GCP", "Azure", "PostgreSQL", "MongoDB", "Redis"
    }
    
    HIGH_VALUE_SKILLS = {
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
        "Distributed Systems", "Microservices", "System Design"
    }
    
    @staticmethod
    def calculate_match(
        company: Dict[str, Any],
        candidate: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate comprehensive match score with multiple factors.
        
        Returns:
            Dict with overall_score, skill_score, experience_score,
            education_score, project_score, and breakdown details.
        """
        # Extract skills
        company_skills = {s.lower() for s in company.get("skills", [])}
        candidate_skills = {s.lower() for s in candidate.get("skills", [])}
        
        # Calculate overlap
        overlap = sorted(company_skills & candidate_skills)
        missing = sorted(company_skills - candidate_skills)
        
        # Calculate skill score (0-100)
        skill_score = EnhancedMatchingEngine._calculate_skill_score(
            overlap, company_skills, candidate_skills
        )
        
        # Calculate experience score (0-100)
        experience_score = EnhancedMatchingEngine._calculate_experience_score(
            candidate, company
        )
        
        # Calculate education score (0-100)
        education_score = EnhancedMatchingEngine._calculate_education_score(
            candidate, company
        )
        
        # Calculate project score (0-100)
        project_score = EnhancedMatchingEngine._calculate_project_score(
            candidate, company
        )
        
        # Calculate recommendation score (0-100)
        recommendation_score = EnhancedMatchingEngine._calculate_recommendation_score(
            skill_score, experience_score, education_score, project_score
        )
        
        # Calculate overall score (weighted average)
        overall_score = (
            skill_score * 0.4 +
            experience_score * 0.25 +
            education_score * 0.15 +
            project_score * 0.2
        )
        
        # Normalize to 70-98 range for compatibility
        normalized_score = 70 + (overall_score * 0.28)
        normalized_score = min(98, max(70, int(normalized_score)))
        
        return {
            "overall_score": normalized_score,
            "skill_score": int(skill_score),
            "experience_score": int(experience_score),
            "education_score": int(education_score),
            "project_score": int(project_score),
            "recommendation_score": int(recommendation_score),
            "overlap": overlap,
            "overlap_count": len(overlap),
            "missing_skills": missing,
            "missing_count": len(missing),
            "strengths": EnhancedMatchingEngine._identify_strengths(
                overlap, candidate
            ),
            "gaps": EnhancedMatchingEngine._identify_gaps(missing, company),
        }
    
    @staticmethod
    def _calculate_skill_score(
        overlap: List[str],
        company_skills: set,
        candidate_skills: set
    ) -> float:
        """Calculate skill overlap score with weighting."""
        if not company_skills:
            return 0.0
        
        overlap_count = len(overlap)
        total_needed = len(company_skills)
        
        # Base score from overlap percentage
        base_score = (overlap_count / total_needed) * 100
        
        # Weight adjustment for high-value skills
        weight_bonus = 0.0
        for skill in overlap:
            if skill in {s.lower() for s in EnhancedMatchingEngine.HIGH_VALUE_SKILLS}:
                weight_bonus += 5.0
            elif skill in {s.lower() for s in EnhancedMatchingEngine.PRIMARY_SKILLS}:
                weight_bonus += 2.0
        
        # Cap bonus
        weight_bonus = min(weight_bonus, 15.0)
        
        return min(100.0, base_score + weight_bonus)
    
    @staticmethod
    def _calculate_experience_score(
        candidate: Dict[str, Any],
        company: Dict[str, Any]
    ) -> float:
        """Calculate experience relevance score."""
        years_str = candidate.get("years_of_experience", "")
        if not years_str:
            return 50.0  # Neutral score if unknown
        
        # Parse years
        years_match = re.search(r"(\d+)", years_str)
        if not years_match:
            return 50.0
        
        years = int(years_match.group(1))
        
        # Score based on funding stage expectations
        funding_stage = company.get("funding_round", "").lower()
        
        if "seed" in funding_stage:
            # Seed stage values early career (0-3 years)
            if years <= 3:
                return 90.0
            elif years <= 5:
                return 80.0
            else:
                return 70.0
        elif "series a" in funding_stage:
            # Series A values mid career (2-5 years)
            if years >= 2 and years <= 5:
                return 90.0
            elif years >= 5:
                return 85.0
            else:
                return 60.0
        else:
            # Later stages value seniority (5+ years)
            if years >= 5:
                return 90.0
            elif years >= 3:
                return 75.0
            else:
                return 50.0
    
    @staticmethod
    def _calculate_education_score(
        candidate: Dict[str, Any],
        company: Dict[str, Any]
    ) -> float:
        """Calculate education relevance score."""
        education = candidate.get("education", [])
        if not education:
            return 50.0  # Neutral if unknown
        
        # Check for relevant degrees
        relevant_degrees = [
            "computer science", "software engineering", "data science",
            "machine learning", "artificial intelligence", "mathematics",
            "statistics", "physics", "electrical engineering"
        ]
        
        has_relevant = False
        for edu in education:
            degree = edu.get("degree", "").lower()
            institution = edu.get("institution", "").lower()
            
            # Check degree relevance
            for rel in relevant_degrees:
                if rel in degree:
                    has_relevant = True
                    break
            
            # Bonus for top-tier institutions
            top_tier = [
                "mit", "stanford", "carnegie mellon", "berkeley",
                "harvard", "princeton", "yale", "caltech", "oxford",
                "cambridge", "eth zurich", "iit"
            ]
            for tier in top_tier:
                if tier in institution:
                    return 95.0  # High score for top-tier relevant education
        
        if has_relevant:
            return 85.0
        
        return 60.0  # Neutral for other education
    
    @staticmethod
    def _calculate_project_score(
        candidate: Dict[str, Any],
        company: Dict[str, Any]
    ) -> float:
        """Calculate project relevance score."""
        projects = candidate.get("projects", [])
        experience = candidate.get("experience", [])
        
        if not projects and not experience:
            return 40.0
        
        # Check for relevant project/experience keywords
        company_industry = company.get("industry", "").lower()
        company_skills = {s.lower() for s in company.get("skills", [])}
        
        relevance_count = 0
        total_items = len(projects) + len(experience)
        
        for project in projects:
            proj_lower = project.lower()
            # Check if project mentions company-relevant skills
            for skill in company_skills:
                if skill in proj_lower:
                    relevance_count += 1
                    break
        
        for exp in experience:
            exp_lower = exp.get("description", "").lower()
            for skill in company_skills:
                if skill in exp_lower:
                    relevance_count += 1
                    break
        
        if total_items == 0:
            return 40.0
        
        score = (relevance_count / total_items) * 100
        return min(100.0, score + 50.0)  # Base 50, add relevance
    
    @staticmethod
    def _calculate_recommendation_score(
        skill_score: float,
        experience_score: float,
        education_score: float,
        project_score: float
    ) -> float:
        """Calculate overall recommendation score."""
        # Weighted average with emphasis on skills and experience
        return (
            skill_score * 0.45 +
            experience_score * 0.35 +
            education_score * 0.10 +
            project_score * 0.10
        )
    
    @staticmethod
    def _identify_strengths(
        overlap: List[str],
        candidate: Dict[str, Any]
    ) -> List[str]:
        """Identify and phrase candidate strengths."""
        strengths = []
        
        # Category-based phrasing
        for skill in overlap[:5]:
            if skill in {s.lower() for s in EnhancedMatchingEngine.PRIMARY_SKILLS}:
                strengths.append(f"Strong {skill} programming background")
            elif skill in {s.lower() for s in EnhancedMatchingEngine.SECONDARY_SKILLS}:
                strengths.append(f"Solid {skill} infrastructure experience")
            elif skill in {s.lower() for s in EnhancedMatchingEngine.HIGH_VALUE_SKILLS}:
                strengths.append(f"Advanced {skill} expertise")
            else:
                strengths.append(f"{skill} experience")
        
        # Add experience strength if available
        years_str = candidate.get("years_of_experience", "")
        if years_str and "year" in years_str:
            strengths.append(f"{years_str} of professional experience")
        
        return strengths[:6]
    
    @staticmethod
    def _identify_gaps(
        missing: List[str],
        company: Dict[str, Any]
    ) -> List[str]:
        """Identify and phrase skill gaps with learning recommendations."""
        gaps = []
        
        # Priority learning paths
        learning_paths = {
            "docker": "Containerization with Docker",
            "kubernetes": "Container orchestration with Kubernetes",
            "aws": "Cloud infrastructure on AWS",
            "gcp": "Cloud infrastructure on GCP",
            "azure": "Cloud infrastructure on Azure",
            "postgresql": "Relational databases (PostgreSQL)",
            "mongodb": "Document databases (MongoDB)",
            "redis": "In-memory data stores (Redis)",
            "machine learning": "Machine Learning fundamentals",
            "deep learning": "Deep Learning with PyTorch/TensorFlow",
            "nlp": "Natural Language Processing",
            "distributed systems": "Distributed Systems design",
        }
        
        for skill in missing[:5]:
            skill_lower = skill.lower()
            if skill_lower in learning_paths:
                gaps.append(learning_paths[skill_lower])
            else:
                gaps.append(f"Build experience with {skill}")
        
        return gaps
