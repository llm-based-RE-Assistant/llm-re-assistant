# UML Diagram Generation - Iteration 2

## Overview

This document describes the UML class diagram generation capability added in Iteration 2. The feature uses GPT-4-turbo to generate PlantUML code from software requirements, following Design Principles DP1 (Task-Specific Model Selection) and DP7 (Prompt Engineering).

## Scientific Justification

### Research Foundation

The implementation is based on findings from Papers [16] and [17], which evaluated LLMs for UML diagram generation:

- **GPT-4-turbo** achieves the best structural scaffolding for UML diagrams
- **Semantic correctness** requires human review (4.85 semantic errors vs 1.75 for human-created diagrams)
- LLMs excel at **Sequence Diagrams** (closest to human quality) and **Deployment Diagrams** (100% completeness)
- **Class Diagrams** show the most semantic challenges but are the most commonly used in Requirements Engineering

### Design Principle Alignment

**DP1 (Task-Specific Model Selection):**
- Uses GPT-4-turbo specifically for UML generation (not GPT-4, as the turbo variant is optimized for structured output)
- Separate from the elicitation engine which uses Ollama/Llama models

**DP7 (Prompt Engineering):**
- Implements few-shot learning with 2-3 high-quality examples
- Structured prompts guide the model to generate valid PlantUML syntax
- Examples demonstrate proper UML notation, relationships, and multiplicities

## Architecture

### Components

1. **ModelingAgent** (`src/agents/modeling_agent.py`)
   - Main agent for UML generation
   - Uses GPT-4-turbo via OpenAI API
   - Implements few-shot prompting pattern
   - Performs quality assessment

2. **PlantUMLValidator** (`src/utils/plantuml_validator.py`)
   - Validates PlantUML syntax
   - Checks for balanced braces, proper tags
   - Counts entities and relationships
   - Detects common syntax issues

3. **OpenAIClient** (`src/utils/openai_client.py`)
   - Wrapper for OpenAI API
   - Handles API key management
   - Implements fallback to GPT-3.5-turbo if GPT-4-turbo fails

4. **UML Prompts** (`src/templates/uml_prompts.json`)
   - Contains few-shot examples
   - System prompt for UML modeling
   - Generation instructions

### API Endpoint

**POST `/api/generate-uml`**

Input:
```json
{
  "requirements": "optional explicit requirements text"
}
```

If `requirements` is not provided, the system extracts requirements from the current conversation session.

Output:
```json
{
  "status": "success",
  "plantuml_code": "@startuml\nclass User {...}\n@enduml",
  "quality": {
    "completeness_ratio": 0.85,
    "entities_found": 6,
    "entities_expected": 7,
    "relationships_count": 5,
    "warnings": ["Relationship between Order and Payment unclear"]
  }
}
```

## Prompt Engineering Approach

### Few-Shot Learning Pattern

The system uses 2-3 examples in the prompt to guide GPT-4-turbo:

1. **Example 1**: Library Management System
   - Demonstrates basic class structure
   - Shows one-to-many relationships
   - Includes attributes and methods

2. **Example 2**: E-Commerce System
   - More complex relationships
   - Multiple entity types
   - Aggregation patterns

3. **Example 3**: University System
   - Enrollment relationships
   - Many-to-many patterns (via junction class)

### Prompt Structure

```
System Prompt: [UML modeling expertise description]

Few-Shot Examples:
Example 1: [Requirement] → [PlantUML code]
Example 2: [Requirement] → [PlantUML code]
Example 3: [Requirement] → [PlantUML code]

Generation Instructions:
- Include all entities mentioned
- Define relationships (association, aggregation, composition)
- Add multiplicities where clear from text
- Use proper UML notation
- Output ONLY PlantUML code, no explanations

Requirements: [User requirements]

Generate PlantUML code:
```

## Quality Assessment

### Completeness Ratio (CR)

The system calculates completeness ratio based on Paper [16]:

```
CR = entities_found / entities_expected
```

**Target:** CR > 0.8 (80% completeness)

**Extraction Method:**
- Expected entities: Extracted from requirements using pattern matching
  - Patterns: "system has X", "X has Y", "track X", "manage X"
  - Capitalized nouns (filtered for common words)
- Found entities: Extracted from generated PlantUML code using regex

### Constraint Satisfaction Checks

1. **Relationship Validation**
   - Checks if relationships are defined between entities
   - Warns if entities appear disconnected

2. **Multiplicity Validation**
   - Verifies multiplicities are present where relationships exist
   - Flags unclear relationship types

3. **Syntax Validation**
   - Validates @startuml/@enduml tags
   - Checks balanced braces
   - Detects empty classes

### Human Review Flags

The system flags diagrams for human review when:
- Completeness Ratio < 0.8
- No relationships defined (but multiple entities exist)
- Semantic errors suspected (unclear relationship types)
- Syntax validation warnings

## Usage Guide

### Generating UML from Conversation

1. Start a conversation about your software system
2. Discuss requirements with the assistant
3. Click **"Generate UML Diagram"** button
4. Review the generated PlantUML code
5. Check quality metrics
6. Click **"Visualize Online"** to see the diagram

### Generating UML from Explicit Requirements

You can also provide requirements directly via the API:

```python
import requests

response = requests.post('http://localhost:5000/api/generate-uml', 
    json={
        'requirements': 'A library system has books, members, and loans...'
    }
)
```

### Visualizing Diagrams

1. **Copy Code**: Click "Copy Code" to copy PlantUML code
2. **Visualize Online**: Click "Visualize Online" to open PlantUML online editor
   - Paste the code into the editor
   - Or use the encoded URL (if supported)

Alternative visualization options:
- Use PlantUML server: `https://www.plantuml.com/plantuml/uml/`
- Install PlantUML locally: `npm install -g node-plantuml`
- Use VS Code extension: "PlantUML"

## Limitations

### Known Limitations

1. **Semantic Errors**
   - GPT-4-turbo generates 4.85 semantic errors on average (vs 1.75 for humans)
   - **Human review is required** for production use
   - Relationship types may be incorrect (association vs aggregation vs composition)

2. **Completeness**
   - Entity extraction from requirements is heuristic-based
   - May miss entities mentioned implicitly
   - Completeness ratio is an approximation

3. **PlantUML Syntax**
   - Generated code may have minor syntax issues
   - Validator catches basic errors but not all edge cases
   - Complex UML features (stereotypes, notes) may be incomplete

4. **Context Understanding**
   - Model may misinterpret ambiguous requirements
   - Domain-specific knowledge may be limited
   - Multi-step reasoning for complex systems is challenging

### Recommendations

1. **Always Review Generated Diagrams**
   - Check entity completeness
   - Verify relationship types and multiplicities
   - Ensure attributes and methods are appropriate

2. **Iterative Refinement**
   - Generate initial diagram
   - Review and identify issues
   - Provide feedback or regenerate with more specific requirements

3. **Combine with Human Expertise**
   - Use generated diagrams as starting points
   - Refine based on domain knowledge
   - Validate against actual system architecture

## Evaluation

### Test Cases

The system should be evaluated with 5 sample requirement sets from papers or textbooks:

1. **Library Management System** (basic CRUD)
2. **E-Commerce Platform** (complex relationships)
3. **University Management** (many-to-many patterns)
4. **Hospital Management** (inheritance, composition)
5. **Banking System** (security, transactions)

### Metrics

For each test case, measure:

1. **Completeness Ratio (CR)**
   - Target: CR > 0.75 (acceptable threshold)
   - Ideal: CR > 0.8 (Paper [16] benchmark)

2. **Syntactic Correctness**
   - Valid PlantUML code
   - Target: < 1.0 syntactic errors (Paper [16])

3. **Semantic Correctness** (manual assessment)
   - Correct relationship types
   - Appropriate multiplicities
   - Complete attributes and methods

4. **Token Usage and Cost**
   - Track API calls
   - Monitor costs per generation

### Expected Results

Based on Paper [16] and [17]:
- **Completeness Ratio**: 0.75 - 0.90 (varies by complexity)
- **Syntactic Errors**: < 1.0 per diagram
- **Semantic Errors**: 3-6 per diagram (requires human review)
- **Generation Time**: 5-15 seconds (depends on API latency)

## Future Improvements

1. **Enhanced Entity Extraction**
   - Use NER (Named Entity Recognition) models
   - Improve pattern matching for requirements

2. **Semantic Validation**
   - Rule-based checks for relationship consistency
   - Domain-specific validation rules

3. **Interactive Refinement**
   - Allow users to provide feedback
   - Regenerate with corrections

4. **Multiple Diagram Types**
   - Sequence diagrams (LLMs excel at these)
   - Deployment diagrams (100% completeness)
   - Activity diagrams

5. **Integration with Elicitation**
   - Automatic UML generation during requirements elicitation
   - Real-time diagram updates

## References

- Paper [16]: Evaluation of LLMs for UML diagram generation
- Paper [17]: Comparative study of LLM capabilities for different UML diagram types
- Mohammad - Requirement Modeling - Synthesis Answers.txt: GPT-4-turbo performance metrics

## Code Structure

```
src/
├── agents/
│   └── modeling_agent.py          # Main UML generation agent
├── utils/
│   ├── openai_client.py           # OpenAI API client
│   └── plantuml_validator.py      # PlantUML syntax validator
└── templates/
    └── uml_prompts.json           # Few-shot examples and prompts

app.py                              # Flask app with /api/generate-uml endpoint
templates/index.html                # Frontend with UML generation UI
```

## Testing

See `tests/test_modeling_agent.py` and `tests/test_plantuml_validator.py` for unit tests.

Run tests:
```bash
pytest tests/test_modeling_agent.py -v
pytest tests/test_plantuml_validator.py -v
```

