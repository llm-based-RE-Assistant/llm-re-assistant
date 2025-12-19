# Modeling Strategy for UML Diagram Generation

## 1. Objective

The objective of this strategy is to integrate **LLM-assisted UML diagram generation** into the Requirements Engineering Assistant as a **drafting aid**, not as a fully autonomous modeling solution.  
The approach follows a **phased, iterative design** aligned with Design Science Research and empirical findings from recent studies on LLM-based UML modeling.

---

## 2. Phased Modeling Approach

### Phase 1: Automated Scaffolding (LLM-driven)

**Description**  
In the first phase, the assistant generates an initial UML diagram scaffold directly from natural-language requirements using a Large Language Model (LLM).

**Model Choice**
- **GPT-4-turbo**

**Rationale**
- Best structural scaffolding performance among evaluated models  
- Very low syntactic error rate (~0.9 errors on average)  
- Effective generation of PlantUML code (Paper [16])

**Output**
- UML represented as **PlantUML text**
- No visual rendering on the server side

**Role of the LLM**
- Extract entities and relationships  
- Propose initial UML structure  
- Ensure syntactic correctness

**Limitations**
- Semantic correctness is not guaranteed  
- Relationships may require human interpretation

---

### Phase 2: Interactive Refinement (Conversational)

**Description**  
After initial diagram generation, the assistant engages the user in a dialogue to clarify ambiguities and refine the UML model.

**Examples of refinement questions**
- “Should the relationship between Order and Payment be composition or association?”  
- “Can a User have multiple roles?”

**Purpose**
- Address semantic ambiguities  
- Improve completeness  
- Reduce incorrect assumptions

**Scientific Basis**
- Paper [17] shows that human-in-the-loop interaction significantly improves modeling quality  
- Aligns with iterative requirements engineering practices

---

### Phase 3: Human Validation (Mandatory)

**Description**  
The generated UML diagram must be reviewed and validated by a human stakeholder.

**Rationale**
- Paper [17] explicitly states that LLM-generated diagrams statistically underperform compared to human-created diagrams in semantic correctness  
- Particularly critical for:
  - Class diagrams  
  - Complex relationships  
  - Domain-specific semantics

**Positioning**
> The assistant supports modeling but does not replace the requirements engineer.

---

## 3. Priority and Roadmap Decisions

### Minimum Viable Product (MVP)

**Diagram Type:** Sequence Diagrams  

**Justification**
- Best LLM performance among UML types  
- Closest to human-created diagrams in quality  
- High completeness and correctness (Paper [17])  
- Directly aligned with interaction and process modeling

---

### Iteration Roadmap

| Iteration | Diagram Type | Justification |
|----------|--------------|---------------|
| MVP / Iteration 1 | Sequence Diagrams | Highest LLM accuracy |
| Iteration 2 | Deployment Diagrams | 100% completeness reported (Paper [17]) |
| Iteration 3+ | Class, Use Case Diagrams | Higher semantic complexity, requires human validation |

---

## 4. Quality Expectations

### Syntactic Quality
- **Target:** >95% syntactic correctness  
- Achievable through:
  - Structured prompt engineering  
  - PlantUML code generation  
  - Automated syntax validation

### Semantic Quality
- No fixed target metric  
- Requires human review  
- Known limitations:
  - Incorrect relationship types  
  - Missing domain constraints  
  - Ambiguous multiplicities

---

## 5. Scientific Positioning

This modeling strategy explicitly acknowledges current limitations of LLMs in UML modeling and aligns system capabilities with empirical evidence rather than overestimating automation potential.  
The strategy supports **knowledge generation** in line with Design Science Research objectives.

---

## 6. Summary

- LLMs are used for **initial UML scaffolding**
- Humans remain responsible for **semantic validation**
- Diagram complexity is introduced **incrementally**
- The strategy is **evidence-based and iteration-driven**
