"""Cheap NLP style statistics using spaCy and textstat."""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


def extract_style_stats(text: str) -> dict:
    """Run spaCy + textstat to extract mechanical style features."""
    import spacy
    import textstat

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        logger.warning("spaCy model not found. Run: python -m spacy download en_core_web_sm")
        nlp = None

    stats = {}

    # Textstat metrics
    stats["flesch_reading_ease"] = textstat.flesch_reading_ease(text)
    stats["flesch_kincaid_grade"] = textstat.flesch_kincaid_grade(text)
    stats["gunning_fog"] = textstat.gunning_fog(text)
    stats["avg_sentence_length"] = textstat.avg_sentence_length(text)
    stats["avg_word_length"] = textstat.avg_letter_per_word(text)
    stats["syllable_count"] = textstat.syllable_count(text)

    # Regex-based features
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    stats["sentence_count"] = len(sentences)
    stats["word_count"] = len(text.split())

    # Punctuation counts
    stats["exclamation_count"] = text.count("!")
    stats["question_count"] = text.count("?")
    stats["em_dash_count"] = text.count("—") + text.count("–")
    stats["ellipsis_count"] = text.count("...")
    stats["comma_density"] = text.count(",") / max(len(sentences), 1)

    # Number detection
    stats["number_count"] = len(re.findall(r"\b\d+\b", text))
    stats["percentage_count"] = len(re.findall(r"\d+%", text))
    stats["dollar_count"] = len(re.findall(r"\$[\d,.]+", text))

    # Pronoun ratios
    words = text.lower().split()
    total = max(len(words), 1)
    stats["i_ratio"] = words.count("i") / total
    stats["we_ratio"] = words.count("we") / total
    stats["you_ratio"] = words.count("you") / total
    stats["they_ratio"] = words.count("they") / total

    # spaCy features
    if nlp:
        doc = nlp(text[:100000])  # Limit to avoid memory issues
        pos_counts = {}
        for token in doc:
            pos_counts[token.pos_] = pos_counts.get(token.pos_, 0) + 1
        total_tokens = max(len(doc), 1)
        stats["noun_ratio"] = pos_counts.get("NOUN", 0) / total_tokens
        stats["verb_ratio"] = pos_counts.get("VERB", 0) / total_tokens
        stats["adj_ratio"] = pos_counts.get("ADJ", 0) / total_tokens
        stats["adv_ratio"] = pos_counts.get("ADV", 0) / total_tokens
        stats["entity_count"] = len(doc.ents)

    return stats
