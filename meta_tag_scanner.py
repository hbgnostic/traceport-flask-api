#!/usr/bin/env python3

import csv
import re
import string
from collections import defaultdict
from typing import List, Dict, Tuple, Set
import os

class MetaTagEngine:
    """
    Intelligent meta tag scanning engine that uses the Traceport NTEE taxonomy
    to automatically assign relevant meta tags to nonprofit program descriptions.
    """

    def __init__(self, csv_path: str, max_tags: int = 3, min_confidence: float = 0.1):
        """
        Initialize the meta tag engine with CSV data.

        Args:
            csv_path: Path to the Traceport Crosswalk NTEE Groups CSV file
            max_tags: Maximum number of meta tags to return per program
            min_confidence: Minimum confidence score for including a meta tag
        """
        self.max_tags = max_tags
        self.min_confidence = min_confidence
        self.meta_tags = {}  # tag -> {category, keywords, definition}
        self.keyword_index = defaultdict(set)  # keyword -> set of meta tags

        # Load and process CSV data
        self._load_csv_data(csv_path)
        self._build_keyword_index()

        print(f"✅ MetaTagEngine loaded {len(self.meta_tags)} meta tags")

    def _load_csv_data(self, csv_path: str):
        """Load meta tag data from CSV file"""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Meta tag CSV file not found: {csv_path}")

        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            for row in reader:
                meta_tag = row.get('Traceport Meta Tag', '').strip()
                category = row.get('Traceport Meta Category', '').strip()
                definition = row.get('Definition', '').strip()
                pcs_term = row.get('PCS Term', '').strip()

                # Skip empty meta tags
                if not meta_tag:
                    continue

                # Store meta tag information
                self.meta_tags[meta_tag] = {
                    'category': category,
                    'definition': definition,
                    'pcs_term': pcs_term,
                    'keywords': set()
                }

    def _build_keyword_index(self):
        """Build searchable keyword index from meta tag data"""
        for meta_tag, data in self.meta_tags.items():
            keywords = set()

            # Extract keywords from meta tag name
            keywords.update(self._extract_keywords(meta_tag))

            # Extract keywords from definition
            if data['definition']:
                keywords.update(self._extract_keywords(data['definition']))

            # Extract keywords from PCS term
            if data['pcs_term']:
                keywords.update(self._extract_keywords(data['pcs_term']))

            # Store keywords for this meta tag
            data['keywords'] = keywords

            # Build reverse index: keyword -> meta tags
            for keyword in keywords:
                self.keyword_index[keyword].add(meta_tag)

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from text"""
        if not text:
            return set()

        # Convert to lowercase and remove punctuation
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))

        # Split into words
        words = text.split()

        # Filter out common stop words and short words
        stop_words = {
            'and', 'or', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were',
            'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'can', 'that',
            'which', 'who', 'what', 'where', 'when', 'why', 'how', 'this',
            'these', 'those', 'they', 'them', 'their', 'its', 'it', 'also',
            'other', 'such', 'more', 'most', 'some', 'any', 'all', 'not',
            'but', 'than', 'only', 'very', 'well', 'just', 'like', 'through',
            'between', 'into', 'during', 'before', 'after', 'above', 'below',
            'including', 'includes', 'include', 'provides', 'provide', 'services',
            'activities', 'programs', 'organizations', 'groups', 'support'
        }

        # Keep meaningful words (length >= 3, not stop words)
        keywords = {
            word for word in words
            if len(word) >= 3 and word not in stop_words and word.isalpha()
        }

        return keywords

    def _calculate_confidence(self, program_text: str, meta_tag: str) -> float:
        """Calculate confidence score for a meta tag match"""
        program_keywords = self._extract_keywords(program_text)
        meta_tag_keywords = self.meta_tags[meta_tag]['keywords']

        if not program_keywords or not meta_tag_keywords:
            return 0.0

        # Calculate keyword overlap
        common_keywords = program_keywords.intersection(meta_tag_keywords)
        if not common_keywords:
            return 0.0

        # Base score from keyword overlap ratio
        overlap_ratio = len(common_keywords) / len(meta_tag_keywords)

        # Boost score for exact meta tag name matches
        meta_tag_words = set(meta_tag.lower().split())
        if meta_tag_words.intersection(program_keywords):
            overlap_ratio += 0.3

        # Boost score for multiple keyword matches
        if len(common_keywords) > 1:
            overlap_ratio += 0.2

        # Boost score for longer keyword matches
        for keyword in common_keywords:
            if len(keyword) > 5:
                overlap_ratio += 0.1

        return min(overlap_ratio, 1.0)

    def scan_program(self, program_description: str) -> List[str]:
        """
        Scan a program description and return relevant meta tags.

        Args:
            program_description: Text description of the nonprofit program

        Returns:
            List of relevant meta tags, sorted by confidence score
        """
        if not program_description or not program_description.strip():
            return ["community"]  # Default fallback

        # Extract keywords from program description
        program_keywords = self._extract_keywords(program_description)

        if not program_keywords:
            return ["community"]  # Default fallback

        # Find candidate meta tags
        candidate_tags = set()
        for keyword in program_keywords:
            if keyword in self.keyword_index:
                candidate_tags.update(self.keyword_index[keyword])

        # Calculate confidence scores for candidates
        scored_tags = []
        for meta_tag in candidate_tags:
            confidence = self._calculate_confidence(program_description, meta_tag)
            if confidence >= self.min_confidence:
                scored_tags.append((meta_tag, confidence))

        # Sort by confidence score (highest first)
        scored_tags.sort(key=lambda x: x[1], reverse=True)

        # Return top meta tags
        result = [tag for tag, score in scored_tags[:self.max_tags]]

        # Fallback if no tags found
        if not result:
            # Try to find category-level matches
            fallback_tags = self._find_fallback_tags(program_description)
            if fallback_tags:
                result = fallback_tags[:self.max_tags]
            else:
                result = ["community"]  # Final fallback

        return result

    def _find_fallback_tags(self, program_description: str) -> List[str]:
        """Find fallback meta tags using broader matching"""
        text = program_description.lower()

        # Common program type patterns
        fallback_patterns = {
            'education': ['school', 'learn', 'teach', 'student', 'academic', 'curriculum'],
            'health': ['health', 'medical', 'wellness', 'clinic', 'hospital', 'mental'],
            'youth': ['youth', 'children', 'kids', 'teen', 'young', 'child'],
            'community': ['community', 'neighborhood', 'local', 'resident', 'civic'],
            'environment': ['environment', 'green', 'nature', 'conservation', 'climate'],
            'arts and culture': ['arts', 'culture', 'music', 'theater', 'creative', 'artist'],
            'food security': ['food', 'hunger', 'nutrition', 'meal', 'kitchen', 'pantry'],
            'housing': ['housing', 'shelter', 'homeless', 'affordable', 'home', 'rent']
        }

        matches = []
        for tag, patterns in fallback_patterns.items():
            if any(pattern in text for pattern in patterns):
                matches.append(tag)

        return matches

    def get_meta_tag_info(self, meta_tag: str) -> Dict:
        """Get detailed information about a specific meta tag"""
        return self.meta_tags.get(meta_tag, {})

    def get_available_tags(self) -> List[str]:
        """Get list of all available meta tags"""
        return list(self.meta_tags.keys())

    def get_tags_by_category(self, category: str) -> List[str]:
        """Get all meta tags in a specific category"""
        return [
            tag for tag, data in self.meta_tags.items()
            if data.get('category', '').lower() == category.lower()
        ]