# LLM-kit

LLM-Kit is a toolkit for processing text, generating question-answer pairs, quality control, and deduplication.

## Module Description

### 1. Text Parsing Module (text_parse)

- Supports parsing of multiple file formats
- Provides text to LaTeX conversion functionality

### 2. Question-Answer Generation Module (generate_qas)

- Generates high-quality question-answer pairs based on parsed text
- Supports various large language models

### 3. Quality Control Module (quality_control)

- Evaluates the quality of question-answer pairs
- Optimizes low-quality question-answer pairs

### 4. Deduplication Module (deduplication)

- Detects and removes duplicate question-answer pairs
- Supports deduplication strategies based on questions or answers

## Usage Instructions

For detailed API usage instructions, please refer to the `api.md` file.

## Configuration Instructions

Configuration files are located in the `hparams` directory:

- `config.yaml`: Basic configuration
- `dedup.yaml`: Deduplication configuration
