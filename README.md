# LLM-Kit

LLM-Kit is a powerful toolkit for text processing, QA pair generation, quality control, and deduplication. It provides a complete set of API interfaces accessible through the FastAPI framework.

## Features

- Support for text parsing in multiple file formats
- Automatic text to LaTeX conversion
- High-quality QA pair generation based on large language models
- Intelligent quality control and optimization system
- Efficient QA pair deduplication algorithm
- Complete REST API interface
- Detailed error logging system
- Support for asynchronous processing and parallel computing

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd LLM-Kit
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure MongoDB database:
- Ensure MongoDB service is running
- Default connection address: mongodb://localhost:27017
- Default database name: llm_kit

## Module Description

### 1. Text Parsing Module (text_parse)

- Supports parsing of multiple file formats (txt, pdf, etc.)
- Provides text to LaTeX conversion functionality
- Supports OCR functionality
- Automatically saves parsing records

### 2. QA Pair Generation Module (generate_qas)

- Generates high-quality QA pairs based on parsed text
- Supports multiple large language models (such as Ernie)
- Supports parallel processing for improved efficiency
- Supports custom domain QA generation

### 3. Quality Control Module (quality_control)

- Evaluates QA pair quality
- Optimizes low-quality QA pairs
- Supports customizable similarity and coverage thresholds
- Provides detailed quality assessment records

### 4. Deduplication Module (deduplication)

- Detects and removes duplicate QA pairs
- Supports deduplication strategies based on questions or answers
- Configurable deduplication thresholds
- Retains highest quality QA pairs

## Configuration Guide

Configuration files are located in the `hparams` directory:

### config.yaml
```yaml
file_path: Input file path
save_path: Results save path
AK: [API key list]
SK: [Corresponding secret keys]
model_name: Model name to use
parallel_num: Number of parallel processes
convert_to_tex: Whether to convert to LaTeX
similarity_rate: Similarity threshold
coverage_rate: Coverage threshold
max_attempts: Maximum retry attempts
domain: Domain setting
```

### dedup.yaml
- Contains deduplication-related configuration parameters
- Configurable deduplication strategy and thresholds

## API Interface

### Main Endpoints

1. Text Parsing Related
- POST `/parse/upload`: Upload file
- POST `/parse`: Parse file
- GET `/parse/files/all`: Get all uploaded files

2. LaTeX Conversion Related
- POST `/to_tex`: Convert to LaTeX format

3. QA Generation Related
- POST `/qa/generate_qa`: Generate QA pairs
- GET `/qa/generate_qa/history`: Get generation history

4. Quality Control Related
- POST `/quality`: Evaluate and optimize QA pairs
- GET `/quality/history`: Get quality control history

5. Deduplication Related
- POST `/dedup/deduplicate_qa`: Execute QA pair deduplication
- GET `/dedup/deduplicate_qa/history`: Get deduplication history

### Error Handling
- All interfaces have a unified error handling mechanism
- Error logs can be viewed via GET `/error-logs` endpoint
- Supports detailed error tracking and recording

## Development Guide

- Developed using FastAPI framework
- Supports asynchronous processing
- Includes comprehensive error handling and logging
- Modular design, easy to extend

## Usage Examples

For detailed API usage instructions and examples, please refer to the `api.md` file.

## Notes

1. Before using, please ensure:
- MongoDB service is properly started
- API keys are correctly set in the configuration file
- Sufficient disk space is available for storing generated files

2. Performance Optimization Suggestions:
- Set an appropriate number of parallel processes
- Adjust similarity and coverage thresholds according to actual needs
- Regularly clean up unnecessary historical records

